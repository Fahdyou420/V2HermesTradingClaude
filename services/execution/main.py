import os
import sys
import json
import asyncio
import requests
import redis
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

# Ensure correct python path for shared modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Shared components
from services.shared.logger import get_logger
from services.shared import redis_channels
from services.shared.models import TradeSignal
from services.shared.error_bus import publish_error

# Execution modules
from services.execution.risk_gatekeeper import RiskGatekeeper
from services.execution.signal_generator import SignalGenerator
from services.execution.order_router import OrderRouter
from services.execution.chart_annotator import ChartAnnotator

logger = get_logger("execution")

app = FastAPI(title="Hermes Execution and Routing Server", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
logger.info(f"Connecting Execution Engine to Redis at {REDIS_URL}...")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Instantiate core modules
risk_gatekeeper = RiskGatekeeper()
order_router = OrderRouter()
chart_annotator = ChartAnnotator()

# Logging folders
LOGS_DIR = Path("/data/trades")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
APPROVED_LOG_FILE = LOGS_DIR / "approved_signals.jsonl"
REJECTED_LOG_FILE = LOGS_DIR / "rejected_signals.jsonl"


def append_signal_log(file_path: Path, payload: dict, extra: Optional[dict] = None):
    """Safely records a signal outcome line into flat files."""
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": int(datetime.utcnow().timestamp()),
                "signal": payload,
                "extra": extra or {}
            }) + "\n")
    except Exception as e:
        logger.error(f"Failed to append signal log metrics to {file_path}: {e}")


async def process_and_route_signal(signal: TradeSignal) -> dict:
    """
    Main pipeline to qualify raw Trade Signals.
    1. Grabs current account metadata from MT5 bridge.
    2. Determines open positions on active channel.
    3. Triggers Risk Gatekeeper checks.
    4. Routes/draws approved signals or publishes rejections.
    """
    mode = str(signal.mode or "paper").lower()
    instrument = signal.instrument
    logger.info(f"Processing candidate signal ID {signal.signal_id} ({instrument} {signal.direction}) | Mode: {mode}")

    # A. Fetch dynamic account metadata
    account_state = {
        "balance": 10000.0,
        "equity": 10000.0,
        "daily_dd_pct": 0.0,
        "weekly_dd_pct": 0.0
    }
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get("http://mt5_bridge:5558/account_state", timeout=3))
        if resp.status_code == 200:
            account_state.update(resp.json())
    except Exception as err:
        logger.warning(f"Unable to read live MT5 account balance: {err}. Safe fallback initialized.")

    # B. Fetch open positions list
    open_positions = []
    if mode == "live":
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.get("http://mt5_bridge:5558/positions", timeout=3))
            if resp.status_code == 200:
                open_positions = resp.json()
        except Exception as e:
            logger.warning(f"Error fetching live broker positions: {e}")
    else: # paper
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.get("http://paper_trader:5561/positions", timeout=3))
            if resp.status_code == 200:
                open_positions = resp.json()
        except Exception as e:
            logger.warning(f"Error fetching paper broker positions: {e}")

    # C. Fetch macroeconomic high-impact events
    calendar_events = []
    try:
        # Check if the document digest or news source published calendars
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get("http://mt5_bridge:5558/calendar", timeout=2))
        if resp.status_code == 200:
            calendar_events = resp.json()
    except Exception:
        pass # silently fallback to empty calendar logs

    # D. Gatekeeper verification
    is_approved, reason = risk_gatekeeper.check(signal, account_state, open_positions, calendar_events)

    payload = signal.to_dict()

    if is_approved:
        logger.info(f"[✓] Signal APPROVED: routing to trade operations...")
        signal.status = "approved"
        payload["status"] = "approved"

        # Try drawing trade markers visually
        try:
            chart_annotator.draw_trade(signal)
        except Exception as ec:
            logger.error(f"Visual terminal annotator block error: {ec}")

        # Real route channels
        route_status = "routed"
        route_detail = ""
        
        if mode == "live":
            logger.info(f"Dispatching LIVE standard contracts order via ZMQ OrderRouter...")
            routed_ok = order_router.send_order(signal)
            if not routed_ok:
                route_status = "error_dispatch"
                route_detail = "ZeroMQ channel dispatch timeout or drop."
                publish_error("execution", "ERROR", "Signal routing failed", str(route_detail))
        else: # paper or live_candidate (treated under stage trust paper tracker)
            logger.info("Routing standard PAPER position request to SQLite engine...")
            try:
                headers = {"Content-Type": "application/json"}
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: requests.post("http://paper_trader:5561/signal", json=payload, headers=headers, timeout=5))
                if resp.status_code in [200, 201]:
                    route_detail = resp.json().get("position_id", "")
                else:
                    route_status = "error_paper"
                    route_detail = f"Paper service HTTP rejection: {resp.status_code} {resp.text}"
                    publish_error("execution", "ERROR", "Signal routing failed", str(route_detail))
            except Exception as pe:
                route_status = "error_paper"
                route_detail = f"Could not reach paper trader container: {pe}"
                logger.error(route_detail)
                publish_error("execution", "ERROR", "Signal routing failed", str(route_detail))

        # Publish Approved notice to Redis channel
        try:
            redis_client.publish(
                redis_channels.SIGNAL_APPROVED, 
                json.dumps({
                    "signal": payload,
                    "route_status": route_status,
                    "route_detail": route_detail,
                    "approved_at": datetime.utcnow().isoformat() + "Z"
                })
            )
        except Exception as re:
            logger.error(f"Failed to publish APPROVED signal to Redis: {re}")

        # Flat-file backup logging
        append_signal_log(APPROVED_LOG_FILE, payload, {"route_status": route_status, "route_detail": route_detail})
        
        return {
            "status": "approved",
            "reason": reason,
            "route_status": route_status,
            "route_detail": route_detail,
            "signal": payload
        }
    else:
        logger.warning(f"[!] Signal REJECTED: {reason}")
        signal.status = "rejected"
        payload["status"] = "rejected"

        # Publish Rejected notice to Redis
        try:
            redis_client.publish(
                redis_channels.SIGNAL_REJECTED,
                json.dumps({
                    "signal": payload,
                    "reason": reason,
                    "rejected_at": datetime.utcnow().isoformat() + "Z"
                })
            )
        except Exception as re:
            logger.error(f"Failed to publish REJECTED signal to Redis: {re}")

        # Flat-file backup logging
        append_signal_log(REJECTED_LOG_FILE, payload, {"reason": reason})

        return {
            "status": "rejected",
            "reason": reason,
            "signal": payload
        }


async def redis_listener_loop():
    """Background listener to intercept messages published by Hermes LLM agents."""
    logger.info("Initializing Redis Pub/Sub AGENT_MESSAGE subscriber loop...")
    pubsub = redis_client.pubsub()
    
    try:
        pubsub.subscribe(redis_channels.AGENT_MESSAGE)
    except Exception as e:
        logger.critical(f"Unable to bind background Redis subscription channel: {e}")
        return

    while True:
        try:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                msg_body = message.get("data", "")
                if msg_body:
                    logger.info("Intercepted raw message from Agent thread.")
                    # Try scanning and executing the structural blocks
                    signal = SignalGenerator.parse_agent_output(str(msg_body))
                    if signal:
                        logger.info(f"Auto-dispatching active TradeSignal candidate: ID {signal.signal_id}")
                        # Launch fully guarded route
                        asyncio.create_task(process_and_route_signal(signal))
            await asyncio.sleep(0.1)
        except Exception as ex:
            logger.error(f"Redis main handler loop error: {ex}")
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    """Launches the independent listener daemon task."""
    asyncio.create_task(redis_listener_loop())


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.post("/signal")
async def receive_signal_endpoint(data: Dict[str, Any]):
    """
    Accepts arbitrary JSON payloads via standard POST requests,
    materializes the model, and passes it into the execution gates.
    """
    try:
        signal = TradeSignal.from_dict(data)
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Incoming JSON format is incompatible with model structures: {e}"
        )

    result = await process_and_route_signal(signal)
    return result


if __name__ == "__main__":
    port = int(os.getenv("EXECUTION_PORT", "5563"))
    logger.info(f"Starting Hermes Execution Service on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
