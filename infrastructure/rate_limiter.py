import time
from fastapi import HTTPException
from infrastructure.cache import cache_get, cache_set


async def rate_limit(key: str, max_calls: int = 60, window: int = 60):
    """Sliding-window rate limiter backed by cache."""
    now = int(time.time())
    slid_key = f"rl:{key}:{now // window}"
    data = await cache_get(slid_key)
    count = data.get("count", 0) if data else 0
    if count >= max_calls:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    await cache_set(slid_key, {"count": count + 1}, ttl=window)
