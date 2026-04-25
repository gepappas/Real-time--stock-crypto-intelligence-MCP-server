"""
Stampede-safe cache: Redis primary, in-memory fallback.

FIXES in v5.2.2:
- Suppress localhost Redis warnings in serverless environments (expected behaviour)
- Connection health check on first use to avoid repeated failed attempts
- Graceful silent fallback without log spam
"""
import json
import os
import time
import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger("cache")

try:
    import redis.asyncio as redis
    _USE_REDIS = True
except ImportError:
    _USE_REDIS = False

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_in_memory_cache: Dict[str, tuple] = {}
_inflight: Dict[str, asyncio.Lock] = {}

# Track whether Redis is actually reachable to avoid repeated warnings
_redis_healthy: Optional[bool] = None
_redis_check_lock = asyncio.Lock()


async def _redis_available() -> bool:
    """Check Redis connectivity once per process lifetime."""
    global _redis_healthy
    if _redis_healthy is not None:
        return _redis_healthy
    async with _redis_check_lock:
        if _redis_healthy is not None:
            return _redis_healthy
        if not _USE_REDIS:
            _redis_healthy = False
            return False
        try:
            pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=10, socket_connect_timeout=2)
            r = redis.Redis(connection_pool=pool)
            await r.ping()
            _redis_healthy = True
            logger.info("Redis connected at %s", REDIS_URL)
            return True
        except Exception:
            _redis_healthy = False
            # Only log once at INFO level — localhost fallback is expected in dev/Cloud Run
            logger.info("Redis unavailable at %s — using in-memory fallback", REDIS_URL)
            return False


async def _get_redis():
    if not hasattr(_get_redis, "pool"):
        _get_redis.pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=10)
    return redis.Redis(connection_pool=_get_redis.pool)


async def cache_set(key: str, value: dict, ttl: int = 30):
    if await _redis_available():
        try:
            r = await _get_redis()
            await r.setex(key, ttl, json.dumps(value))
            return
        except Exception:
            # Silent fallback — Redis may have dropped since health check
            pass
    _in_memory_cache[key] = (value, time.time() + ttl)


async def cache_get(key: str) -> Optional[dict]:
    if await _redis_available():
        try:
            r = await _get_redis()
            data = await r.get(key)
            return json.loads(data) if data else None
        except Exception:
            pass
    if key in _in_memory_cache:
        val, expiry = _in_memory_cache[key]
        if time.time() < expiry:
            return val
        del _in_memory_cache[key]
    return None


async def cache_delete(key: str):
    if await _redis_available():
        try:
            r = await _get_redis()
            await r.delete(key)
        except Exception:
            pass
    _in_memory_cache.pop(key, None)


async def get_or_compute(key: str, compute_fn, ttl: int = 30):
    """Stampede-safe cache-aside: only one coroutine computes per key at a time."""
    cached = await cache_get(key)
    if cached is not None:
        return cached
    if key not in _inflight:
        _inflight[key] = asyncio.Lock()
    async with _inflight[key]:
        # Double-check after acquiring lock
        cached = await cache_get(key)
        if cached is not None:
            return cached
        result = await compute_fn()
        if result is not None:
            await cache_set(key, result, ttl=ttl)
        return result
