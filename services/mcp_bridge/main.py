import os
import sys
import json
import asyncio
import httpx
import redis
import requests
import zmq
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Ensure correct python path for shared modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Shared constants
from services.shared.logger import get_logger
from services.shared import redis_channels

logger = get_logger("mcp_bridge")

app = FastAPI(title="Hermes Docker-MCP Bridge Service", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
HOST_RPC_URL = os.getenv("HOST_RPC_URL", "http://host.docker.internal:7778")

logger.info(f"Initializing Redis connection at {REDIS_URL}...")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Document chunk sampler counter
chunk_counter = 0

# Initialize ZeroMQ Draw socket to relay chart commands directly to MetaTrader 5
try:
    zmq_ctx = zmq.Context()
    zmq_draw_socket = zmq_ctx.socket(zmq.PUSH)
    zmq_draw_socket.setsockopt(zmq.LINGER, 1000)
    zmq_draw_socket.setsockopt(zmq.SNDTIMEO, 2000)
    zmq_draw_uri = os.getenv("DRAW_ZMQ_URI", "tcp://host.docker.internal:5556")
    logger.info(f"Connecting MCP Bridge ZMQ Draw socket to {zmq_draw_uri}...")
    zmq_draw_socket.connect(zmq_draw_uri)
except Exception as ze:
    logger.error(f"Failed to initialize ZMQ Draw socket in MCP Bridge: {ze}")
    zmq_draw_socket = None

class ChatRequest(BaseModel):
    message: str
    task_type: Optional[str] = "analysis"
    context: Optional[Dict[str, Any]] = None

class ToolRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any]


@app.post("/signal")
async def signal_proxy_endpoint(data: Dict[str, Any]):
    """
    Proxies a trade signal trigger directly into the Risk Execution Engine container.
    """
    logger.info(f"Incoming /signal proxy trigger for instrument {data.get('instrument')}")
    target_url = "http://execution:5563/signal"
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.post(target_url, json=data, timeout=10))
        return resp.json()
    except Exception as e:
        logger.error(f"Error bridging signal to execution container: {e}")
        # Try fallback to standard paper trader or handle error
        raise HTTPException(status_code=500, detail=f"Execution engine unreachable: {e}")


@app.post("/draw")
async def draw_proxy_endpoint(data: Dict[str, Any]):
    """
    Proxies drawing commands by publishing directly to the Redis CHART_DRAW_CMD channel.
    """
    logger.info(f"Incoming /draw proxy command: ID {data.get('id')} shape {data.get('type')}")
    try:
        redis_client.publish(redis_channels.CHART_DRAW_CMD, json.dumps(data))
        return {"success": True, "message": "Dispatched drawing command to Redis successfully."}
    except Exception as e:
        logger.error(f"Failed to publish draw command: {e}")
        raise HTTPException(status_code=500, detail=f"Redis disconnected: {e}")


async def send_async_chat_request(chat_payload: dict):
    """
    Asynchronously fires a request to the Windows host RPC chat server.
    Logs tokens as they arrive to facilitate background observability.
    """
    target_url = f"{HOST_RPC_URL}/chat"
    logger.info(f"Dispatching async background chat analysis request to {target_url}...")
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", target_url, json=chat_payload) as r:
                if r.status_code != 200:
                    logger.error(f"Auto-chat error: Host RPC returned {r.status_code}")
                    return
                
                full_reply = []
                async for line in r.aiter_lines():
                    if line and line.startswith("data:"):
                        token_payload = line[5:].strip()
                        if token_payload and token_payload != "[DONE]":
                            full_reply.append(token_payload)
                
                logger.info(f"✓ Background chat finished successfully. Response summary size: {len(full_reply)} tokens.")
    except Exception as e:
        logger.error(f"Uncaught exception while calling host chat in background: {e}")


async def redis_subscription_handler():
    """
    Subscribes to:
    - BACKTEST_COMPLETE -> triggers automated chat response on host RPC.
    - NEW_DOCUMENT_CHUNK -> prints a preview log on every 100th event.
    - CHART_DRAW_CMD -> forwards draw packets to MT5 over ZMQ.
    """
    global chunk_counter
    logger.info("Initializing PubSub listener for MCP Bridge...")
    
    pubsub = redis_client.pubsub()
    try:
        pubsub.subscribe(
            redis_channels.BACKTEST_COMPLETE, 
            redis_channels.NEW_DOCUMENT_CHUNK,
            redis_channels.CHART_DRAW_CMD
        )
        logger.info(f"✓ Subscribed to channels: {redis_channels.BACKTEST_COMPLETE}, {redis_channels.NEW_DOCUMENT_CHUNK}, {redis_channels.CHART_DRAW_CMD}")
    except Exception as err:
        logger.critical(f"Redis PubSub connection failed inside MCP Bridge: {err}")
        return

    while True:
        try:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                channel = message.get("channel")
                data_raw = message.get("data", "")
                
                if channel == redis_channels.BACKTEST_COMPLETE:
                    logger.info(f"[*] Intercepted BACKTEST_COMPLETE event.")
                    try:
                        payload = json.loads(data_raw)
                        strategy_id = payload.get("strategy_id", payload.get("id", "unknown_strategy"))
                        summary = payload.get("summary", payload.get("results", str(payload)))
                        
                        chat_payload = {
                            "message": f"Backtest complete for strategy {strategy_id}. Results: {summary}. Please analyse and update the strategy card in the vault.",
                            "task_type": "analysis",
                            "context": {}
                        }
                        # Launch task in standard event loop to not block Redis readings
                        asyncio.create_task(send_async_chat_request(chat_payload))
                    except Exception as e:
                        logger.error(f"Failed to process BACKTEST_COMPLETE parameters: {e}")
                        
                elif channel == redis_channels.NEW_DOCUMENT_CHUNK:
                    chunk_counter += 1
                    if chunk_counter % 100 == 0:
                        logger.info(f"[Sample #{chunk_counter}] Intercepted raw NEW_DOCUMENT_CHUNK message. Size: {len(str(data_raw))} bytes.")

                elif channel == redis_channels.CHART_DRAW_CMD:
                    logger.info(f"[*] Intercepted CHART_DRAW_CMD to forward to MT5 DRAW channel.")
                    if zmq_draw_socket:
                        try:
                            zmq_draw_socket.send_string(data_raw)
                        except Exception as se:
                            logger.error(f"Failed to forward draw packet over ZeroMQ: {se}")
                        
            await asyncio.sleep(0.05)
        except Exception as ex:
            logger.error(f"Error in PubSub worker loop: {ex}")
            await asyncio.sleep(5.0)


@app.on_event("startup")
async def startup_event():
    """Binds background threads and daemon routines."""
    asyncio.create_task(redis_subscription_handler())


@app.get("/health")
async def health():
    """Verify backend and bridge proxy dependencies state."""
    rpc_ok = False
    rpc_msg = "unreachable"
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(f"{HOST_RPC_URL}/health", timeout=2))
        if resp.status_code == 200:
            rpc_ok = True
            rpc_msg = "online"
    except Exception as e:
        rpc_msg = f"offline (error: {e})"
        
    return {
        "status": "ok" if rpc_ok else "degraded",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "host_rpc": {
            "status": "online" if rpc_ok else "offline",
            "message": rpc_msg
        },
        "redis": "connected"
    }


@app.post("/chat")
async def chat_proxy_endpoint(payload: ChatRequest):
    """
    Proxies a user prompt down to host.docker.internal Windows server.
    Streams results back to client as an SSE stream.
    """
    logger.info(f"Incoming /chat proxy invocation (Task: {payload.task_type}). Message length: {len(payload.message)}")
    target_url = f"{HOST_RPC_URL}/chat"
    
    async def sse_stream_generator():
        req_body = {
            "message": payload.message,
            "task_type": payload.task_type or "analysis",
            "context": payload.context or {}
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                async with client.stream("POST", target_url, json=req_body) as r:
                    if r.status_code != 200:
                        err_text = await r.aread()
                        logger.error(f"Host RPC server returned error {r.status_code}: {err_text}")
                        yield f"data: Error from RPC Host: {r.status_code} - {err_text.decode('utf-8', errors='ignore')}\n\n"
                        return
                    
                    async for line in r.aiter_lines():
                        if line:
                            # Forward incoming line cleanly back to listener
                            yield line + "\n"
                        else:
                            # Keep alive empty line
                            yield "\n"
            except httpx.RequestError as exc:
                logger.error(f"HTTP stream connection failure linking host: {exc}")
                yield f"data: [Bridge Connection Error] {str(exc)}\n\n"
            except Exception as exc:
                logger.error(f"Unexpected bridge failure during stream: {exc}")
                yield f"data: [Bridge Exception] {str(exc)}\n\n"

    return StreamingResponse(sse_stream_generator(), media_type="text/event-stream")


@app.post("/tool")
async def tool_proxy_endpoint(payload: ToolRequest):
    """
    Direct proxy for executing structured tools on raw host filesystem / Obsidian context.
    """
    logger.info(f"Incoming /tool proxy request: {payload.tool_name}")
    target_url = f"{HOST_RPC_URL}/tool"
    
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.post(
            target_url,
            json={"tool_name": payload.tool_name, "params": payload.params},
            timeout=120
        ))
        if resp.status_code != 200:
            logger.error(f"Host RPC tool execution returned exit code: {resp.status_code}. Detail: {resp.text}")
            return {
                "success": False,
                "error": f"Upstream host returned status code: {resp.status_code}",
                "result": None
            }
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to bridge tool call directly to host RPC: {e}")
        return {
            "success": False,
            "error": f"Internal proxy bridge error: {str(e)}",
            "result": None
        }


if __name__ == "__main__":
    port = int(os.getenv("MCP_BRIDGE_PORT", "5562"))
    logger.info(f"Launching Hermes MCP Bridge Service on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
