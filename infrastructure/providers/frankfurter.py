import httpx
from infrastructure.cache import cache_get, cache_set
from typing import Optional

FRANKFURTER_BASE = "https://api.frankfurter.app"


async def get_exchange_rates(
    base: str = "EUR",
    targets: str = "USD,GBP",
    date: Optional[str] = None,
) -> dict:
    """Get FX rates from Frankfurter (backed by ECB)."""
    key = f"fx:{base.upper()}:{targets.upper()}:{date or 'latest'}"
    cached = await cache_get(key)
    if cached:
        return cached

    path = f"/{date}" if date else "/latest"
    params = {"from": base.upper(), "to": targets.upper()}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{FRANKFURTER_BASE}{path}", params=params)
        r.raise_for_status()
        data = r.json()
        await cache_set(key, data, ttl=3600)  # ECB rates update daily
        return data


async def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> dict:
    """Convert amount between two currencies."""
    data = await get_exchange_rates(base=from_currency, targets=to_currency)
    rate = data.get("rates", {}).get(to_currency.upper(), 0)
    return {
        "from": from_currency.upper(),
        "to": to_currency.upper(),
        "amount": amount,
        "converted": round(amount * rate, 4),
        "rate": rate,
        "date": data.get("date", ""),
        "source": "ECB via Frankfurter",
    }
