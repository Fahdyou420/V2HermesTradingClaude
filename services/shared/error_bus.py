import os
import json
import time
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
ERROR_LOG_KEY = "hermes:errors"
MAX_ERRORS = 500

def publish_error(service: str, level: str, message: str, detail: str = ""):
    """Push a structured error to the shared Redis error bus with localhost fallback."""
    try:
        try:
            r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1.0)
            r.ping()
        except Exception:
            r = redis.Redis.from_url("redis://localhost:6379", decode_responses=True, socket_timeout=1.0)
            r.ping()

        entry = json.dumps({
            "timestamp": int(time.time()),
            "service": service,
            "level": level,        # "ERROR", "CRITICAL", "WARNING"
            "message": message,
            "detail": detail
        })
        r.lpush(ERROR_LOG_KEY, entry)
        r.ltrim(ERROR_LOG_KEY, 0, MAX_ERRORS - 1)
    except Exception:
        pass  # Never let error reporting crash the caller

def get_recent_errors(n: int = 50):
    """Retrieve recent errors from the shared bus."""
    try:
        try:
            r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1.0)
            raw = r.lrange(ERROR_LOG_KEY, 0, n - 1)
        except Exception:
            r = redis.Redis.from_url("redis://localhost:6379", decode_responses=True, socket_timeout=1.0)
            raw = r.lrange(ERROR_LOG_KEY, 0, n - 1)
        return [json.loads(e) for e in raw]
    except Exception:
        return []
