"""
Yahoo Finance stock/ETF price provider.

FIXES in v5.2.2:
- Return None instead of $0 Price for invalid/delisted tickers
- Better error logging
- Handle empty meta fields gracefully
"""
import httpx
import logging
from typing import Optional
from infrastructure.cache import cache_get, cache_set
from domain.models import Price

logger = logging.getLogger("yahoo")

YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


async def get_stock_price(ticker: str) -> Optional[Price]:
    """Get stock/ETF price from Yahoo Finance v8 chart API.

    Returns None if ticker is invalid, delisted, or Yahoo returns no data.
    """
    sym = ticker.upper()
    key = f"yahoo:price:{sym}"
    cached = await cache_get(key)
    if cached:
        try:
            return Price(**cached)
        except Exception:
            logger.warning("Corrupted cache for %s, refetching", sym)

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(url, params={"interval": "1d", "range": "2d"}, headers=YAHOO_HEADERS)
            r.raise_for_status()
            data = r.json()

            chart = data.get("chart", {})
            if chart.get("error"):
                logger.info("Yahoo returned error for %s: %s", sym, chart["error"])
                return None

            results = chart.get("result")
            if not results:
                logger.info("Yahoo returned no data for %s", sym)
                return None

            meta = results[0].get("meta", {})
            price_val = float(meta.get("regularMarketPrice", 0) or 0)

            # If price is 0, likely delisted or invalid ticker
            if price_val <= 0:
                logger.info("Yahoo returned zero/negative price for %s — treating as unavailable", sym)
                return None

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
    except httpx.HTTPStatusError as exc:
        logger.warning("Yahoo HTTP error for %s: %s", sym, exc.response.status_code)
        return None
    except Exception as exc:
        logger.warning("Yahoo fetch failed for %s: %s", sym, exc)
        return None
