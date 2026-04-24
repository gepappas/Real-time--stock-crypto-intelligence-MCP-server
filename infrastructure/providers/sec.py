"""
SEC EDGAR Form 4 insider-trading fetcher.
Primary: EDGAR full-text search API (efts.sec.gov).
Fallback: RSS/ATOM feed from browse-edgar.
"""
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from typing import List, Optional
from infrastructure.cache import cache_get, cache_set
from domain.models import InsiderTrade

SEC_HEADERS = {
    "User-Agent": "revolut-pulse/5.2 (github.com/gepappas98/revolut-pulse-mcp.v2; contact@revolut-pulse.io)"
}


async def get_recent_insider_trades(ticker: Optional[str] = None, limit: int = 25) -> List[InsiderTrade]:
    """Fetch Form 4 insider filings from SEC EDGAR (primary + fallback)."""
    key = f"sec:insider:{ticker or 'all'}:{limit}"
    cached = await cache_get(key)
    if cached:
        return [InsiderTrade(**t) for t in cached]

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
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://efts.sec.gov/LATEST/search-index",
                json=payload,
                headers={**SEC_HEADERS, "Content-Type": "application/json"},
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
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
    except Exception:
        pass

    # ── Fallback: RSS/ATOM browse-edgar ──────────────────────────────────
    if not trades:
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcurrent&type=4&dateb={date_str}&start=0&count={limit}&output=atom"
            )
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(url, headers=SEC_HEADERS)
                if r.status_code == 200:
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
        except Exception:
            pass

    await cache_set(key, [t.__dict__ for t in trades], ttl=300)
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
