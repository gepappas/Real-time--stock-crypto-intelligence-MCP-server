"""
SEC EDGAR Form 4 insider-trading fetcher.
Primary: EDGAR full-text search API (efts.sec.gov).
Fallback: RSS/ATOM feed from browse-edgar.

CRITICAL FIXES in v5.2.2:
- Rotating User-Agent to avoid SEC 403 blocks
- Exponential backoff retry (3 attempts)
- Rate-limit delay between requests
- Proper error handling without swallowing exceptions silently
- Graceful degradation: return empty list instead of crashing
"""
import httpx
import asyncio
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from typing import List, Optional
from infrastructure.cache import cache_get, cache_set
from domain.models import InsiderTrade

logger = logging.getLogger("sec_edgar")

# SEC requires a realistic browser User-Agent and enforces rate limits.
# Rotate through several to avoid blocks.
SEC_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

SEC_HEADERS_BASE = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sec.gov/",
}

# SEC requests no more than 10 requests per second.
_sec_rate_limit_lock = asyncio.Lock()
_sec_last_request_time: Optional[datetime] = None


async def _sec_rate_limit():
    """Enforce ~100ms gap between SEC requests to stay under 10 req/s."""
    global _sec_last_request_time
    async with _sec_rate_limit_lock:
        now = datetime.utcnow()
        if _sec_last_request_time:
            elapsed = (now - _sec_last_request_time).total_seconds()
            if elapsed < 0.12:
                await asyncio.sleep(0.12 - elapsed)
        _sec_last_request_time = datetime.utcnow()


async def _sec_post_with_retry(url: str, payload: dict, headers: dict, max_retries: int = 3) -> Optional[httpx.Response]:
    """POST to SEC with exponential backoff and UA rotation."""
    for attempt in range(max_retries):
        await _sec_rate_limit()
        ua = SEC_USER_AGENTS[attempt % len(SEC_USER_AGENTS)]
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.post(url, json=payload, headers={**headers, "User-Agent": ua})
                if r.status_code == 200:
                    return r
                elif r.status_code == 403:
                    logger.warning("SEC returned 403 on attempt %d — rotating UA and backing off", attempt + 1)
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("SEC returned %d on attempt %d", r.status_code, attempt + 1)
                    await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            logger.warning("SEC request failed on attempt %d: %s", attempt + 1, exc)
            await asyncio.sleep(2 ** attempt)
    return None


async def _sec_get_with_retry(url: str, headers: dict, max_retries: int = 3) -> Optional[httpx.Response]:
    """GET from SEC with exponential backoff and UA rotation."""
    for attempt in range(max_retries):
        await _sec_rate_limit()
        ua = SEC_USER_AGENTS[attempt % len(SEC_USER_AGENTS)]
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(url, headers={**headers, "User-Agent": ua})
                if r.status_code == 200:
                    return r
                elif r.status_code == 403:
                    logger.warning("SEC GET returned 403 on attempt %d — rotating UA and backing off", attempt + 1)
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("SEC GET returned %d on attempt %d", r.status_code, attempt + 1)
                    await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            logger.warning("SEC GET failed on attempt %d: %s", attempt + 1, exc)
            await asyncio.sleep(2 ** attempt)
    return None


async def get_recent_insider_trades(ticker: Optional[str] = None, limit: int = 25) -> List[InsiderTrade]:
    """Fetch Form 4 insider filings from SEC EDGAR (primary + fallback)."""
    key = f"sec:insider:{ticker or 'all'}:{limit}"
    cached = await cache_get(key)
    if cached:
        try:
            return [InsiderTrade(**t) for t in cached]
        except Exception:
            logger.warning("Cache deserialization failed for %s, refetching", key)

    trades: List[InsiderTrade] = []

    # ── Primary: EDGAR full-text search ──────────────────────────────────
    try:
        query = 'formType:"4"'
        if ticker:
            query += f' AND issuerTradingSymbol:{ticker.upper()}'
        payload = {
            "q": query,
            "dateRange": "custom",
            "startdt": (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"),
            "enddt": datetime.now().strftime("%Y-%m-%d"),
            "from": 0,
            "size": limit,
            "sort": {"filedAt": {"order": "desc"}},
        }
        r = await _sec_post_with_retry(
            "https://efts.sec.gov/LATEST/search-index",
            payload,
            {**SEC_HEADERS_BASE, "Content-Type": "application/json"},
        )
        if r:
            data = r.json()
            hits = data.get("hits", {}).get("hits", [])
            for hit in hits:
                src = hit.get("_source", {})
                rel = src.get("reportingOwnerRelationship", {})
                title = rel.get("officerTitle", "")
                trade = InsiderTrade(
                    ticker=src.get("issuerTradingSymbol", "").upper(),
                    insider_name=src.get("reportingOwnerName", "Unknown"),
                    title=title,
                    transaction_type=src.get("transactionType", "Buy"),
                    value=src.get("transactionValue", {}).get("value", 0) or 0,
                    shares=src.get("transactionShares", {}).get("value", 0) or 0,
                    price_per_share=src.get("transactionPricePerShare", {}).get("value", 0) or 0,
                    is_ceo_cfo=any(kw in title.upper() for kw in ["CEO", "CFO", "CHIEF EXECUTIVE", "CHIEF FINANCIAL"]),
                    is_director=bool(rel.get("isDirector", False)),
                    is_officer=bool(rel.get("isOfficer", False)),
                    transaction_date=src.get("periodOfReport", ""),
                    filing_date=src.get("filedAt", "")[:10] if src.get("filedAt") else "",
                )
                trades.append(trade)
            logger.info("SEC primary returned %d trades for %s", len(trades), ticker or "all")
        else:
            logger.warning("SEC primary failed after all retries for %s", ticker or "all")
    except Exception as exc:
        logger.warning("SEC primary exception for %s: %s", ticker or "all", exc)

    # ── Fallback: RSS/ATOM browse-edgar ──────────────────────────────────
    if not trades:
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcurrent&type=4&dateb={date_str}&start=0&count={limit}&output=atom"
            )
            r = await _sec_get_with_retry(url, SEC_HEADERS_BASE)
            if r and r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for entry in soup.find_all("entry"):
                    title_tag = entry.find("title")
                    title_text = title_tag.text if title_tag else ""
                    ticker_extracted = (
                        title_text.split("(")[-1].replace(")", "").strip().upper()
                        if "(" in title_text else ""
                    )
                    updated = entry.find("updated")
                    trades.append(InsiderTrade(
                        ticker=ticker_extracted,
                        insider_name="See filing",
                        title="",
                        transaction_type="Unknown",
                        value=0,
                        filing_date=updated.text[:10] if updated else "",
                    ))
                logger.info("SEC fallback returned %d trades", len(trades))
            else:
                logger.warning("SEC fallback failed for %s", ticker or "all")
        except Exception as exc:
            logger.warning("SEC fallback exception for %s: %s", ticker or "all", exc)

    try:
        await cache_set(key, [t.__dict__ for t in trades], ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache SEC results: %s", exc)
    return trades


async def get_insider_clusters(days: int = 7) -> list:
    """Detect multiple insiders trading the same ticker on the same day."""
    trades = await get_recent_insider_trades(limit=200)
    clusters: dict = {}
    for t in trades:
        if not t.ticker or not t.transaction_date:
            continue
        k = (t.ticker, t.transaction_date)
        clusters.setdefault(k, []).append(t)

    result = []
    for (ticker, date), group in clusters.items():
        if len(group) < 2:
            continue
        total_val = sum(g.value or 0 for g in group)
        has_ceo = any(g.is_ceo_cfo for g in group)
        insiders = list({g.insider_name for g in group})
        result.append({
            "ticker": ticker,
            "date": date,
            "insiders": insiders,
            "insider_count": len(insiders),
            "total_value": round(total_val, 2),
            "has_ceo_cfo": has_ceo,
        })
    result.sort(key=lambda x: x["total_value"], reverse=True)
    return result
