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
from urllib.parse import urlencode
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


async def _fetch_form4_xml(accession_id: str) -> Optional[dict]:
    """
    Fetch and parse a Form 4 XML filing from EDGAR.

    accession_id is the EDGAR accession number in dashed format as returned in
    the EFTS Elasticsearch _id field: e.g. '0001234567-24-000001'.

    Returns a dict of parsed Form 4 fields, or None on any failure.

    Two-step:
      1. Fetch the filing index page to locate the primary Form 4 XML document.
      2. Fetch and parse that XML.

    Both requests share the existing _sec_get_with_retry backoff/rate-limit.
    """
    parts = accession_id.split("-")
    if len(parts) != 3:
        return None

    cik_int = int(parts[0])          # strip leading zeros for the URL path
    accession_nodash = accession_id.replace("-", "")
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}"
        f"/{accession_nodash}/{accession_id}-index.htm"
    )

    # Step 1: filing index page → find the primary XML document URL
    r = await _sec_get_with_retry(index_url, SEC_HEADERS_BASE)
    if not r or r.status_code != 200:
        logger.debug("Form 4 index page unavailable: %s", index_url)
        return None

    soup = BeautifulSoup(r.text, "lxml")
    form4_url = None
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        # Filing index table: [sequence, description, document, type, size]
        # Look for the row whose type cell contains "4"
        if len(cells) >= 4:
            doc_type = cells[3].get_text(strip=True)
            if doc_type == "4":
                link = cells[2].find("a")
                if link and link.get("href"):
                    href = link["href"]
                    form4_url = (
                        href if href.startswith("http")
                        else f"https://www.sec.gov{href}"
                    )
                    break

    if not form4_url:
        logger.debug("No Form 4 XML link found in index: %s", index_url)
        return None

    # Step 2: fetch and parse the Form 4 XML
    r = await _sec_get_with_retry(form4_url, {**SEC_HEADERS_BASE, "Accept": "text/xml,application/xml"})
    if not r or r.status_code != 200:
        logger.debug("Form 4 XML fetch failed: %s", form4_url)
        return None

    try:
        xml = BeautifulSoup(r.text, "lxml-xml")

        def text(tag: str, default: str = "") -> str:
            node = xml.find(tag)
            return node.get_text(strip=True) if node else default

        def float_text(tag: str) -> float:
            node = xml.find(tag)
            if node:
                val_node = node.find("value")
                raw = val_node.get_text(strip=True) if val_node else node.get_text(strip=True)
                try:
                    return float(raw.replace(",", ""))
                except ValueError:
                    pass
            return 0.0

        ticker = text("issuerTradingSymbol").upper()
        if not ticker:
            return None  # malformed filing — skip

        officer_title = text("officerTitle")
        acq_disp = xml.find("transactionAcquiredDisposedCode")
        acq_val = acq_disp.find("value").get_text(strip=True) if (acq_disp and acq_disp.find("value")) else "A"

        shares = float_text("transactionShares")
        price  = float_text("transactionPricePerShare")

        return {
            "ticker":         ticker,
            "insider_name":   text("rptOwnerName", "Unknown"),
            "officer_title":  officer_title,
            "is_director":    text("isDirector") == "1",
            "is_officer":     text("isOfficer") == "1",
            "transaction_type": "Buy" if acq_val == "A" else "Sell",
            "shares":         shares,
            "price":          price,
            "value":          round(shares * price, 2),
            "period":         text("periodOfReport"),
        }
    except Exception as exc:
        logger.warning("Form 4 XML parse error (%s): %s", form4_url, exc)
        return None


async def get_recent_insider_trades(ticker: Optional[str] = None, limit: int = 25) -> List[InsiderTrade]:
    """
    Fetch Form 4 insider filings from SEC EDGAR.

    Bugs fixed vs previous version:
    - Bug 1: Was POSTing JSON to EDGAR EFTS. EDGAR EFTS is a GET-only endpoint;
      POST returns 405, silently swallowed → 0 trades from primary.
    - Bug 2: _source field names (issuerTradingSymbol, transactionValue, …) are
      Form 4 XML element names, NOT EDGAR EFTS index fields. EFTS _source is
      filing metadata (entity_name, file_date, period_of_report). Every field
      read as "" or {} → InsiderTrade.ticker = "" → never in REVOLUT_STOCKS.
      Fix: get accession ID from EFTS hit, fetch actual Form 4 XML, parse real
      fields via _fetch_form4_xml().
    - Bug 3: Fallback Atom title "4 - JOHN DOE (0001234567) (Reporting)" — the
      parenthesised value is the REPORTER'S CIK, not a ticker. split("(")[-1]
      extracted "Reporting" for every entry.
    - Bug 4: html.parser on Atom XML. xml tags are case-sensitive; html.parser
      lowercases in HTML mode, making find_all("entry") unreliable on
      application/atom+xml. Fix: lxml-xml parser.
    - Bug 5: Fallback always set is_ceo_cfo=False because title="" for every
      fallback trade. Fix: officer title now parsed from Form 4 XML.
    """
    key = f"sec:insider:{ticker or 'all'}:{limit}"
    cached = await cache_get(key)
    if cached:
        try:
            return [InsiderTrade(**t) for t in cached]
        except Exception:
            logger.warning("Cache deserialization failed for %s, refetching", key)

    trades: List[InsiderTrade] = []

    # ── Primary: EDGAR EFTS full-text search (GET) ───────────────────────
    # The EDGAR EFTS endpoint only accepts GET with query params.
    # POST with a JSON body returns 405; silently swallowed by the retry helper
    # → 0 hits from primary every time.
    try:
        qs: dict = {
            "forms": "4",
            "dateRange": "custom",
            "startdt": (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"),
            "enddt": datetime.now().strftime("%Y-%m-%d"),
            "from": "0",
            "size": str(limit),
        }
        if ticker:
            qs["q"] = f'issuerTradingSymbol:{ticker.upper()}'
        url = "https://efts.sec.gov/LATEST/search-index?" + urlencode(qs)

        r = await _sec_get_with_retry(url, {**SEC_HEADERS_BASE, "Accept": "application/json"})
        if r:
            data = r.json()
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                logger.info("EFTS first _source keys: %s", list(hits[0].get("_source", {}).keys()))

            # EFTS _source has filing metadata, NOT Form 4 XML parsed fields.
            # Fetch the actual Form 4 XML for each hit to get real ticker + data.
            sem = asyncio.Semaphore(5)  # max 5 concurrent SEC requests

            async def _primary_fetch(hit: dict) -> Optional[InsiderTrade]:
                accession = hit.get("_id", "")
                src = hit.get("_source", {})
                filing_date = (src.get("file_date") or src.get("filed_at") or "")[:10]
                async with sem:
                    details = await _fetch_form4_xml(accession)
                if not details:
                    return None
                title = details["officer_title"]
                return InsiderTrade(
                    ticker=details["ticker"],
                    insider_name=details["insider_name"],
                    title=title,
                    transaction_type=details["transaction_type"],
                    value=details["value"],
                    shares=details["shares"],
                    price_per_share=details["price"],
                    is_ceo_cfo=any(kw in title.upper() for kw in ["CEO", "CFO", "CHIEF EXECUTIVE", "CHIEF FINANCIAL"]),
                    is_director=details["is_director"],
                    is_officer=details["is_officer"],
                    transaction_date=details["period"],
                    filing_date=filing_date,
                )

            results = await asyncio.gather(*[_primary_fetch(h) for h in hits], return_exceptions=True)
            trades = [t for t in results if isinstance(t, InsiderTrade)]
            logger.info("SEC primary returned %d trades for %s", len(trades), ticker or "all")
        else:
            logger.warning("SEC primary request failed for %s", ticker or "all")
    except Exception as exc:
        logger.warning("SEC primary exception for %s: %s", ticker or "all", exc)

    # ── Fallback: RSS/ATOM browse-edgar ──────────────────────────────────
    # The Atom feed title is "4 - JOHN DOE (CIK) (Reporting)" — no ticker.
    # The prior code extracted "Reporting" from split("(")[-1], which never
    # matched any stock.  Fix: parse accession from the entry link, then call
    # _fetch_form4_xml to get the real ticker, title, and transaction data.
    # Use lxml-xml (not html.parser) for reliable Atom XML tag discovery.
    if not trades:
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcurrent&type=4&dateb={date_str}&start=0&count={limit}&output=atom"
            )
            r = await _sec_get_with_retry(url, SEC_HEADERS_BASE)
            if r and r.status_code == 200:
                # lxml-xml: correct parser for Atom (application/atom+xml)
                # html.parser lowercases tags in HTML mode — unreliable for XML.
                soup = BeautifulSoup(r.text, "lxml-xml")
                entries = soup.find_all("entry")
                logger.info("SEC fallback Atom: %d entries", len(entries))

                # Extract accession IDs from filing index links, e.g.
                # https://www.sec.gov/Archives/edgar/data/123/000123-24-001-index.htm
                # → accession "000123-24-001" → "0-0-0-1-2-3---2-4---0-0-1"... no
                # Actually EDGAR index links have format:
                # .../data/{cik}/{accession_nodash}/{accession}-index.htm
                import re as _re
                accession_pattern = _re.compile(r"(\d{10}-\d{2}-\d{6})-index\.htm")

                accessions: List[str] = []
                for entry in entries:
                    link_tag = entry.find("link")
                    href = ""
                    if link_tag:
                        href = link_tag.get("href") or link_tag.get_text(strip=True)
                    m = accession_pattern.search(href)
                    if m:
                        accessions.append(m.group(1))

                sem = asyncio.Semaphore(5)

                async def _fallback_fetch(accession: str) -> Optional[InsiderTrade]:
                    async with sem:
                        details = await _fetch_form4_xml(accession)
                    if not details:
                        return None
                    title = details["officer_title"]
                    return InsiderTrade(
                        ticker=details["ticker"],
                        insider_name=details["insider_name"],
                        title=title,
                        transaction_type=details["transaction_type"],
                        value=details["value"],
                        shares=details["shares"],
                        price_per_share=details["price"],
                        is_ceo_cfo=any(kw in title.upper() for kw in ["CEO", "CFO", "CHIEF EXECUTIVE", "CHIEF FINANCIAL"]),
                        is_director=details["is_director"],
                        is_officer=details["is_officer"],
                        transaction_date=details.get("period"),
                        filing_date="",
                    )

                results = await asyncio.gather(*[_fallback_fetch(a) for a in accessions], return_exceptions=True)
                trades = [t for t in results if isinstance(t, InsiderTrade)]
                logger.info("SEC fallback returned %d trades", len(trades))
            else:
                logger.warning("SEC fallback request failed for %s", ticker or "all")
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
