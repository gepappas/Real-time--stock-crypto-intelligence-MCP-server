"""
Stampede-safe cache: Redis primary, in-memory fallback.
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


async def _get_redis():
    if not hasattr(_get_redis, "pool"):
        _get_redis.pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=10)
    return redis.Redis(connection_pool=_get_redis.pool)


async def cache_set(key: str, value: dict, ttl: int = 30):
    if _USE_REDIS:
        try:
            r = await _get_redis()
            await r.setex(key, ttl, json.dumps(value))
            return
        except Exception as e:
            logger.warning("Redis set failed, falling back to memory: %s", e)
    _in_memory_cache[key] = (value, time.time() + ttl)


async def cache_get(key: str) -> Optional[dict]:
    if _USE_REDIS:
        try:
            r = await _get_redis()
            data = await r.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("Redis get failed, falling back to memory: %s", e)
    if key in _in_memory_cache:
        val, expiry = _in_memory_cache[key]
        if time.time() < expiry:
            return val
        del _in_memory_cache[key]
    return None


async def cache_delete(key: str):
    if _USE_REDIS:
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
