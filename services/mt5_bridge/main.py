import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# Fix python paths for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import zmq
import zmq.asyncio
import redis.asyncio as redis
import aiofiles
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Shared utilities
from services.shared.logger import get_logger
from services.shared.models import MarketBar, TradeSignal
from services.shared import redis_channels
from services.shared.error_bus import publish_error

# Service Logger
logger = get_logger("mt5_bridge")

# App Initialization
app = FastAPI(title="Hermes MT5 ZeroMQ Bridge", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global configuration
ZMQ_HOST = os.getenv("ZMQ_MT5_HOST", "host.docker.internal")
ZMQ_PORT = int(os.getenv("ZMQ_DATA_PORT", "5555"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

LIVE_FEED_PATH = Path("/data/market_data/live_feed.jsonl")
EVENTS_PATH = Path("/data/trades/events.jsonl")

# Ensure target directories exist
os.makedirs("/data/market_data", exist_ok=False or True)
os.makedirs("/data/trades", exist_ok=False or True)

# In-memory store for backtest chunks: keyed by (instrument, timeframe)
backtest_storage: Dict[str, List[Dict[str, Any]]] = {}

# Global Redis instance
redis_client: Optional[redis.Redis] = None


@app.on_event("startup")
async def startup_event():
    global redis_client
    logger.info(f"Connecting to Redis at {REDIS_URL}...")
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Try to ping Redis to ensure connection
    try:
        await redis_client.ping()
        logger.info("[✓] Redis connection confirmed.")
    except Exception as e:
        logger.error(f"[X] Failed to connect to Redis: {e}")

    # Kick off ZMQ background process
    asyncio.create_task(zmq_listener_task())


@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Closed Redis connection.")


# FastAPI Router endpoints
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/latest_bars")
async def get_latest_bars(
    instrument: str = "XAUUSD",
    tf: str = "M15",
    n: int = Query(default=200, ge=1, le=1000)
):
    """
    Reads from live_feed.jsonl and returns the last n bars for the given instrument and timeframe.
    """
    if not LIVE_FEED_PATH.exists():
        return []

    bars = []
    # Read the file and filter. For efficiency we read lines, but limit to avoid memory overflow.
    async with aiofiles.open(LIVE_FEED_PATH, mode="r", encoding="utf-8") as f:
        async for line in f:
            if not line.strip():
                continue
            try:
                bar_dict = json.loads(line)
                b_inst = bar_dict.get("instrument", "")
                b_tf = bar_dict.get("timeframe", bar_dict.get("tf", ""))
                
                if b_inst.upper() == instrument.upper() and b_tf.upper() == tf.upper():
                    bars.append(bar_dict)
            except Exception as e:
                # Silently skip malformed lines
                continue

    # Return the last n bars
    return bars[-n:]


@app.get("/backtest_files")
async def get_backtest_files():
    """
    Returns a list of all raw backtest data files saved in market_data
    """
    dir_path = Path("/data/market_data")
    if not dir_path.exists():
        return []
    
    # Locate all json files that are not live_feed
    files = []
    for f in dir_path.glob("*.json"):
        files.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat() + "Z"
        })
    return files


# Live MT5 Environment State Cache
account_state_store = {
    "balance": 0.0,
    "equity": 0.0,
    "daily_dd_pct": 0.0,
    "weekly_dd_pct": 0.0
}
positions_store = []
calendar_events_store = []

@app.get("/account_state")
async def get_account_state():
    return account_state_store

@app.post("/account_state")
async def update_account_state(data: Dict[str, Any]):
    global account_state_store
    account_state_store.update(data)
    return {"status": "ok", "account_state": account_state_store}

@app.get("/positions")
async def get_positions():
    return positions_store

@app.post("/positions")
async def update_positions(data: List[Dict[str, Any]]):
    global positions_store
    positions_store = data
    return {"status": "ok", "positions": positions_store}

@app.get("/calendar")
async def get_calendar():
    return calendar_events_store

@app.post("/calendar")
async def update_calendar(data: List[Dict[str, Any]]):
    global calendar_events_store
    calendar_events_store = data
    return {"status": "ok", "calendar": calendar_events_store}


# Background Task: ZeroMQ PULL Receiver
async def zmq_listener_task():
    global redis_client
    
    bind_url = f"tcp://0.0.0.0:{ZMQ_PORT}"
    logger.info(f"Setting up ZeroMQ PULL Socket, binding to {bind_url}...")
    
    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.PULL)
    
    # Set Socket options
    sock.setsockopt(zmq.RCVHWM, 100000) # High watermark for backtest data
    
    try:
        sock.bind(bind_url)
        logger.info(f"[✓] ZeroMQ PULL socket bound successfully to {bind_url}")
    except Exception as e:
        logger.critical(f"[X] Failed to bind ZMQ PULL socket on {bind_url}: {e}")
        return

    while True:
        try:
            # Async receive
            raw_msg = await sock.recv_string()
            
            # Message cleaning - parse JSON content if message starts with some topic label
            first_brace = raw_msg.find("{")
            if first_brace == -1:
                logger.warning(f"Received non-JSON message over ZeroMQ: {raw_msg[:100]}")
                continue
            
            json_str = raw_msg[first_brace:]
            try:
                payload = json.loads(json_str)
            except Exception as e:
                logger.error(f"Failed to parse raw JSON: {e} | Original: {raw_msg[:200]}")
                continue
            
            # Inspect event classification type
            msg_type = payload.get("type", "bar")
            
            if msg_type == "bar":
                await handle_live_bar(payload)
                
            elif msg_type == "backtest_chunk":
                await handle_backtest_chunk(payload)
                
            elif msg_type == "backtest_end":
                await handle_backtest_end(payload)
                
            elif msg_type == "trade_event":
                await handle_trade_event(payload)
                
            elif msg_type == "account":
                global account_state_store
                account_state_store.update(payload.get("data", {}))
                logger.info(f"Received account state update from ZMQ: {account_state_store}")
                
            elif msg_type == "positions":
                global positions_store
                positions_store = payload.get("positions", [])
                logger.info(f"Received positions update from ZMQ: {len(positions_store)} positions open.")
                
            else:
                logger.warning(f"Unknown message type received: {msg_type}")
                
        except asyncio.CancelledError:
            logger.info("ZMQ Listener cancelled. Terminating...")
            break
        except Exception as e:
            logger.error(f"ZMQ Listener runtime error: {e}")
            publish_error("mt5_bridge", "ERROR", "ZMQ Listener runtime error", str(e))
            await asyncio.sleep(1) # Simple cooloff before retry


async def handle_live_bar(payload: Dict[str, Any]):
    global redis_client
    try:
        # Re-verify and parse fields into our Standard Model
        market_bar = MarketBar.from_dict(payload)
        bar_dict = market_bar.to_dict()
        
        # Append to live_feed.jsonl
        async with aiofiles.open(LIVE_FEED_PATH, mode="a", encoding="utf-8") as f:
            await f.write(json.dumps(bar_dict) + "\n")
            
        # Publish to Redis
        if redis_client:
            await redis_client.publish(redis_channels.NEW_BAR, json.dumps(bar_dict))
            
    except Exception as e:
        logger.error(f"Could not handle live bar payload: {e}")


async def handle_backtest_chunk(payload: Dict[str, Any]):
    # Backtest chunks are kept in memory until the sequence terminates
    inst = payload.get("instrument", "UNKNOWN").upper()
    tf = payload.get("timeframe", payload.get("tf", "M15")).upper()
    key = f"{inst}_{tf}"
    
    if key not in backtest_storage:
        backtest_storage[key] = []
        
    try:
        # Standardize bar fields
        bar = MarketBar.from_dict(payload)
        backtest_storage[key].append(bar.to_dict())
    except Exception as e:
        logger.error(f"Malformed backtest chunk bar filter: {e}")


async def handle_backtest_end(payload: Dict[str, Any]):
    global redis_client
    inst = payload.get("instrument", "UNKNOWN").upper()
    tf = payload.get("timeframe", payload.get("tf", "M15")).upper()
    key = f"{inst}_{tf}"
    
    bar_list = backtest_storage.get(key, [])
    if not bar_list:
        logger.warning(f"Received backtest_end for {key} but storage list is empty!")
        return
        
    # Construct descriptive filename
    current_date = datetime.utcnow().strftime("%Y%m%d")
    out_filename = f"{inst}_{tf}_{current_date}.json"
    out_path = Path("/data/market_data") / out_filename
    
    try:
        # Write array of bars to disk
        async with aiofiles.open(out_path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(bar_list, indent=2))
            
        logger.info(f"[✓] Saved backtest data to file: {out_path} ({len(bar_list)} bars)")
        
        # Clear working memory cache
        backtest_storage[key] = []
        
        # Notify components via Redis Pub/Sub
        if redis_client:
            done_payload = {
                "instrument": inst,
                "timeframe": tf,
                "file_path": str(out_path),
                "total_bars": len(bar_list),
                "timestamp": int(datetime.utcnow().timestamp())
            }
            await redis_client.publish(redis_channels.BACKTEST_COMPLETE, json.dumps(done_payload))
            
    except Exception as e:
        logger.error(f"Failed handling backtest end completion write: {e}")


async def handle_trade_event(payload: Dict[str, Any]):
    global redis_client
    try:
        # Write to chronological log events
        async with aiofiles.open(EVENTS_PATH, mode="a", encoding="utf-8") as f:
            await f.write(json.dumps(payload) + "\n")
            
        action = payload.get("action", "").upper()
        
        # Route to appropriate Redis Pub/Sub channel
        if redis_client:
            if action in ["OPEN", "BUY", "SELL"]:
                await redis_client.publish(redis_channels.TRADE_OPENED, json.dumps(payload))
                logger.info(f"[Trade Event] TRADE OPENED: {payload.get('ticket', 'N/A')}")
            elif action in ["CLOSE", "LIQUID", "TP", "SL"]:
                await redis_client.publish(redis_channels.TRADE_CLOSED, json.dumps(payload))
                logger.info(f"[Trade Event] TRADE CLOSED: {payload.get('ticket', 'N/A')} | PnL: ${payload.get('pnl', 0.0)}")
            else:
                # fallback payload publishing
                await redis_client.publish(redis_channels.PAPER_TRADE_UPDATE, json.dumps(payload))
                
    except Exception as e:
        logger.error(f"Error handling trade event: {e}")


if __name__ == "__main__":
    # Load and run FastAPI
    port = int(os.getenv("MT5_BRIDGE_PORT", "5558"))
    logger.info(f"Starting Hermes MT5 Bridge Server on host 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
