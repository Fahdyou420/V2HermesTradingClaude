import os
import sys
import time
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure correct python path for shared modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import requests
import redis.asyncio as redis
import chromadb
import schedule
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Shared utilities
from services.shared.logger import get_logger
from services.shared.error_bus import publish_error

logger = get_logger("embedder")

# configurations
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
QUEUE_NAME = "doc_chunks_queue"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

CHROMA_URL = os.getenv("CHROMA_URL", "http://chromadb:8000")

# Setup Chroma Client
parsed_url = CHROMA_URL.replace("http://", "").replace("https://", "")
if ":" in parsed_url:
    chroma_host, chroma_port_str = parsed_url.split(":", 1)
    chroma_port = int(chroma_port_str)
else:
    chroma_host = parsed_url
    chroma_port = 8000

logger.info(f"Initializing Chroma HTTP Client at {chroma_host}:{chroma_port}...")
chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)

# Fast API setup
app = FastAPI(title="Hermes Vector Embedder Service", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ollama_url": OLLAMA_URL,
        "chroma_url": CHROMA_URL
    }


@app.get("/stats")
async def get_stats():
    try:
        collections_info = {}
        for coll_name in ["trading_knowledge", "market_memory"]:
            try:
                coll = chroma_client.get_collection(coll_name)
                collections_info[coll_name] = coll.count()
            except Exception:
                collections_info[coll_name] = 0
        return {
            "status": "ok",
            "collections": collections_info
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_embedding(text: str) -> List[float]:
    """Call Ollama's embeddings API synchronously."""
    url = f"{OLLAMA_URL}/api/embeddings"
    payload = {
        "model": OLLAMA_EMBED_MODEL,
        "prompt": text
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json().get("embedding", [])
        else:
            msg = f"Ollama embedding failure {response.status_code}: {response.text}"
            logger.error(msg)
            publish_error("embedder", "ERROR", "Ollama embedding failure", msg)
    except Exception as e:
        logger.error(f"Ollama connection error during embedding: {e}")
        publish_error("embedder", "ERROR", "Ollama connection error during embedding", str(e))
    return []


async def get_embedding_async(text: str) -> List[float]:
    """Non-blocking run of the embedding API in an executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_embedding, text)


def parse_markdown_frontmatter(content: str) -> Dict[str, str]:
    """Parse key value frontmatter parameters from Obsidian note headers."""
    metadata = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip().replace('"', '').replace("'", "")
    return metadata


def sync_obsidian_notes():
    """Reads all markdown notes in Obsidian vault and embeds them into the collection 'market_memory'."""
    logger.info("Initializing Obsidian Notes Sync to 'market_memory' search pool.")
    obsidian_path = Path("/data/obsidian")
    if not obsidian_path.exists():
        logger.warning(f"Obsidian mounting directory '{obsidian_path}' is empty or does not exist.")
        return

    try:
        collection = chroma_client.get_or_create_collection("market_memory")
    except Exception as e:
        logger.error(f"Chroma connection failed. Cannot fetch/create 'market_memory': {e}")
        return

    notes_found = list(obsidian_path.rglob("*.md"))
    logger.info(f"Located {len(notes_found)} note(s) inside local Obsidian vault.")

    for md_file in notes_found:
        try:
            with open(md_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content.strip():
                continue

            metadata = parse_markdown_frontmatter(content)
            
            # Extract attributes
            instrument = metadata.get("Associated Instrument") or metadata.get("instrument") or "GLOBAL"
            timeframe = metadata.get("Reference Timeframes") or metadata.get("timeframe") or "GLOBAL"
            
            # ISO timestamp fallback
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime).isoformat() + "Z"
            date_val = metadata.get("date") or mtime

            # Scrub and validate metadata fields
            metadata_clean = {
                "instrument": str(instrument),
                "timeframe": str(timeframe),
                "date": str(date_val),
                "note_path": str(md_file.relative_to(obsidian_path))
            }

            # Embed full content
            embedding = get_embedding(content)
            if not embedding:
                logger.warning(f"Failed to generate embedding vector for Obsidian note: {md_file.name}")
                continue

            note_id = f"obsidian_{md_file.name}_{int(md_file.stat().st_mtime)}"
            collection.upsert(
                documents=[content],
                embeddings=[embedding],
                metadatas=[metadata_clean],
                ids=[note_id]
            )
            logger.info(f"[Sync] Saved Obsidian Page: {md_file.name} to 'market_memory'.")

        except Exception as e:
            logger.error(f"Failed parsing markdown note '{md_file.name}': {e}")


async def process_chunk_payload(payload: Dict[str, Any]):
    """Embeds and saves Inbox chunk payload into Chroma collection 'trading_knowledge'."""
    text = payload.get("text", "").strip()
    if not text:
        return

    source = payload.get("source_file", "unknown")
    idx = payload.get("chunk_index", 0)

    logger.info(f"Embedding chunk {idx} for source document: {source}")
    embedding = await get_embedding_async(text)
    
    if not embedding:
        logger.error(f"Cannot generate chunk embedding vector. Discarding chunk.")
        return

    try:
        collection = chroma_client.get_or_create_collection("trading_knowledge")
        
        # Prepare metadata for storage
        metadata = {
            "source_file": str(source),
            "chunk_index": int(idx),
            "total_chunks": int(payload.get("total_chunks", 1)),
            "doc_type": str(payload.get("doc_type", "txt")),
            "instrument_hint": str(payload.get("instrument_hint", "GLOBAL")),
            "date_ingested": str(payload.get("date_ingested", ""))
        }

        chunk_id = f"{source}_{idx}"
        collection.upsert(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[chunk_id]
        )
        logger.info(f"[✓] Upserted chunk [{chunk_id}] into 'trading_knowledge' collection.")

    except Exception as e:
        logger.error(f"Chroma upsert failed for chunk {chunk_id}: {e}")


async def redis_consumer_task():
    """Continuously BLPOPs incoming document chunk logs from Redis list queues."""
    logger.info(f"Starting background Redis queue list watcher for task queue: '{QUEUE_NAME}'")
    
    # Use distinct async client
    r_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    
    while True:
        try:
            # Pop entry from Redis list
            res = await r_client.blpop(QUEUE_NAME, timeout=2)
            if res:
                _, json_str = res
                try:
                    payload = json.loads(json_str)
                    await process_chunk_payload(payload)
                except Exception as e:
                    logger.error(f"Could not unpack chunk JSON string payload stream: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Redis queue watcher cancelled. Terminating...")
            break
        except Exception as e:
            logger.error(f"Redis consumer connection error logic: {e}")
            await asyncio.sleep(2)
            
    await r_client.close()


def run_cron_obsidian_sync():
    """Cron-triggered synchronizer wrapped by executor."""
    logger.info("Executing scheduled Obsidian synchronizer note refresh...")
    sync_obsidian_notes()


async def schedule_runner_task():
    """Async scheduler run loop."""
    while True:
        schedule.run_pending()
        await asyncio.sleep(5)


@app.on_event("startup")
async def startup_services():
    # Run Obsidian Sync immediately on boot to guarantee freshness
    logger.info("[Startup] Initiating immediate Obsidian notes initialization sync...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_obsidian_notes)

    # Boot background queues
    asyncio.create_task(redis_consumer_task())

    # Set up periodic synchronizer (6 hours)
    schedule.every(6).hours.do(run_cron_obsidian_sync)
    asyncio.create_task(schedule_runner_task())
    logger.info("[Startup] Set Obsidian sync job to trigger every 6 hours.")


if __name__ == "__main__":
    port = int(os.getenv("EMBEDDER_PORT", "5563"))
    logger.info(f"Starting Hermes Embedder Service on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
