import httpx
from infrastructure.cache import cache_get, cache_set
from domain.models import Price
from typing import List, Optional

BINANCE_HEADERS = {"User-Agent": "revolut-pulse/5.2 (github.com/gepappas98/revolut-pulse-mcp.v2)"}
BINANCE_BASE = "https://api.binance.com/api/v3"


async def get_crypto_price(symbol: str) -> Optional[Price]:
    """Get single crypto price from Binance 24hr ticker."""
    sym = symbol.upper()
    key = f"binance:price:{sym}"
    cached = await cache_get(key)
    if cached:
        return Price(**cached)
    try:
        url = f"{BINANCE_BASE}/ticker/24hr"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params={"symbol": f"{sym}USDT"}, headers=BINANCE_HEADERS)
            r.raise_for_status()
            d = r.json()
            price = Price(
                symbol=sym,
                value=float(d["lastPrice"]),
                source="binance",
                currency="USDT",
                change_pct=round(float(d["priceChangePercent"]), 2),
                volume=round(float(d.get("quoteVolume", 0)), 2),
                high_24h=float(d.get("highPrice", 0)),
                low_24h=float(d.get("lowPrice", 0)),
            )
            await cache_set(key, price.__dict__, ttl=10)
            return price
    except Exception:
        return None


async def get_crypto_top_movers(limit: int = 10, min_volume_usd: float = 10_000_000) -> dict:
    """Get top crypto gainers and losers filtered by USDT volume."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{BINANCE_BASE}/ticker/24hr", headers=BINANCE_HEADERS)
            r.raise_for_status()
            all_tickers = r.json()
    except Exception:
        return {"gainers": [], "losers": [], "total_pairs_scanned": 0}

    filtered = []
    for t in all_tickers:
        if not t["symbol"].endswith("USDT"):
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol < min_volume_usd:
            continue
        base = t["symbol"][:-4]
        chg = float(t.get("priceChangePercent", 0))
        filtered.append({
            "ticker": base,
            "price": round(float(t["lastPrice"]), 6),
            "change_pct": round(chg, 2),
            "volume_usd_24h": round(vol, 0),
        })

    return {
        "gainers": sorted(filtered, key=lambda x: x["change_pct"], reverse=True)[:limit],
        "losers": sorted(filtered, key=lambda x: x["change_pct"])[:limit],
        "total_pairs_scanned": len(filtered),
        "min_volume_filter_usd": min_volume_usd,
    }
