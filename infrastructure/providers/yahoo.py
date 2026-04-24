import httpx
from infrastructure.cache import cache_get, cache_set
from domain.models import Price

YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


async def get_stock_price(ticker: str) -> Price:
    """Get stock/ETF price from Yahoo Finance v8 chart API."""
    sym = ticker.upper()
    key = f"yahoo:price:{sym}"
    cached = await cache_get(key)
    if cached:
        return Price(**cached)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(url, params={"interval": "1d", "range": "2d"}, headers=YAHOO_HEADERS)
            r.raise_for_status()
            data = r.json()
            meta = data["chart"]["result"][0]["meta"]
            price_val = float(meta.get("regularMarketPrice", 0))
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose", price_val) or price_val)
            change = price_val - prev
            change_pct = round((change / prev * 100), 2) if prev else 0.0
            price = Price(
                symbol=sym,
                name=meta.get("longName") or meta.get("shortName") or sym,
                value=price_val,
                source="yahoo",
                currency=meta.get("currency", "USD"),
                change_pct=change_pct,
                volume=meta.get("regularMarketVolume"),
                market_cap=meta.get("marketCap"),
            )
            await cache_set(key, price.__dict__, ttl=30)
            return price
    except Exception:
        return Price(symbol=sym, value=0, source="yahoo", currency="USD")
