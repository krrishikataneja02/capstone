"""
Redis client with graceful fallback — Redis is OPTIONAL for basic API functionality.

The module exposes a singleton ``redis_client`` that is either a working
``redis.Redis`` instance or ``None`` when Redis is unavailable.

All public helpers (``cache_get``, ``cache_set``, ``cache_delete``) silently
degrade to no-ops when Redis is down, ensuring the rest of the API continues
to work.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger("digital_twin.redis")

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis | None:
    """Return the current Redis client (may be ``None``)."""
    return _redis_client


def init_redis() -> redis.Redis | None:
    """
    Initialise the Redis connection.  Called once during application startup.
    Returns the client on success, ``None`` on failure.
    """
    global _redis_client
    if not settings.REDIS_URL:
        _redis_client = None
        logger.info("REDIS_URL is not configured; Redis cache is disabled")
        return None
    try:
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        logger.info("Redis connection established")
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable — running without cache")
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close the Redis connection pool.  Safe to call even when client is ``None``."""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
        logger.info("Redis connection closed")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def redis_health() -> dict:
    """Return ``{"status": "ok"}`` or ``{"status": "unavailable"}``."""
    if _redis_client is None:
        return {"status": "unavailable"}
    try:
        _redis_client.ping()
        return {"status": "ok"}
    except Exception:
        return {"status": "unavailable"}


# ---------------------------------------------------------------------------
# Cache helpers (safe to call even when Redis is down)
# ---------------------------------------------------------------------------

def cache_get(key: str) -> Any | None:
    """Retrieve and JSON-decode a cached value.  Returns ``None`` on miss or error."""
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.debug("cache_get(%s) failed", key, exc_info=True)
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """JSON-encode and store a value with a TTL.  Returns ``True`` on success."""
    if _redis_client is None:
        return False
    try:
        _redis_client.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception:
        logger.debug("cache_set(%s) failed", key, exc_info=True)
        return False


def cache_delete(key: str) -> bool:
    """Delete a cached key.  Returns ``True`` on success."""
    if _redis_client is None:
        return False
    try:
        _redis_client.delete(key)
        return True
    except Exception:
        logger.debug("cache_delete(%s) failed", key, exc_info=True)
        return False


def invalidate_twin_state() -> None:
    """Invalidate the short-lived aggregate snapshot after relevant writes."""
    cache_delete("twin:state:v1")
