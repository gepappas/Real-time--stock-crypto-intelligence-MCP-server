"""
FastAPI application: SEO pages + MCP HTTP/JSON-RPC transport.
v5.2.1 – production‑ready with full SEO enhancements.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from usecases.trading import get_trading_context
from usecases.insider import enrich_insider_context
from domain.services import TradingDecisionEngine
from infrastructure.providers import revolut, binance, frankfurter
from seo.generator import render_ticker_page, generate_all_symbols

logger = logging.getLogger("api")

# ── Configuration ──────────────────────────────────────────────────────────
SITE_URL = os.getenv("SITE_URL", "https://revolut-pulse-mcp-v2.up.railway.app").rstrip("/")
AUTHOR = os.getenv("AUTHOR_NAME", "Revolut Pulse Financial Intelligence")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
OG_IMAGE_URL = os.getenv("OG_IMAGE_URL", "")  # optional

app = FastAPI(
    title="Revolut Pulse MCP v5.2",
    version="5.2.1",
    description="Real-time stock/crypto intelligence + insider tracking MCP server",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── HTML helpers ──────────────────────────────────────────────────────────

def _seo_wrap(title: str, description: str, canonical: str, body: str) -> str:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_human = datetime.now().strftime("%B %d, %Y")
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": now_iso,
        "dateModified": now_iso,
        "author": {"@type": "Organization", "name": AUTHOR},
        "publisher": {"@type": "Organization", "name": AUTHOR},
    })
    og_image_tag = f'<meta property="og:image" content="{OG_IMAGE_URL}">' if OG_IMAGE_URL else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta name="author" content="{AUTHOR}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{canonical}">
  <!-- Open Graph -->
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Revolut Pulse">
  {og_image_tag}
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <!-- Schema.org -->
  <script type="application/ld+json">{schema}</script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem 1.5rem; color: #1a1a2e; }}
    h1 {{ color: #16213e; }} h2 {{ color: #0f3460; }}
    a {{ color: #e94560; }} table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #16213e; color: white; }}
    footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ddd; font-size: 0.85rem; color: #666; }}
  </style>
</head>
<body>
{body}
<footer>
  <p><strong>Last updated:</strong> {now_human}</p>
  <p>Data sourced from Yahoo Finance, Binance, and SEC EDGAR. Not financial advice.</p>
  <p>
    <a href="/sitemap.xml">Sitemap</a> |
    <a href="/revolut-stocks">All Stocks</a> |
    <a href="/revolut-crypto">Crypto List</a> |
    <a href="/robots.txt">Robots</a> |
    <a href="/health">Status</a>
  </p>
</footer>
</body>
</html>"""


# ── Health & Status ───────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "5.2.1",
        "tools": 38,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return JSONResponse({
        "name": "revolut-pulse-mcp",
        "version": "5.2.1",
        "tools": 38,
        "prompts": 17,
        "resources": 5,
        "endpoints": {
            "mcp_stdio": "python main.py (MCP_TRANSPORT=stdio)",
            "mcp_http": "POST /mcp (JSON-RPC 2.0)",
            "mcp_sse": "GET /mcp/sse",
            "seo_stocks": "/revolut-stocks",
            "seo_crypto": "/revolut-crypto",
            "sitemap": "/sitemap.xml",
            "robots": "/robots.txt",
        },
    })


@app.get("/robots.txt")
async def robots():
    """robots.txt for search engine crawlers."""
    content = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml"
    return HTMLResponse(content=content, media_type="text/plain")


# ── SEO Pages ─────────────────────────────────────────────────────

@app.get("/revolut-stocks", response_class=HTMLResponse)
async def revolut_stocks_list():
    stocks = sorted(revolut.REVOLUT_STOCKS.items())
    rows = "".join(
        f'<tr><td><a href="/ticker/{k}">{k}</a></td><td>{v}</td>'
        f'<td><a href="/guide/{k}">Buying Guide</a></td>'
        f'<td><a href="/revolut-vs-etoro/{k}">vs eToro</a></td></tr>'
        for k, v in stocks
    )
    body = f"""
<h1>All Stocks &amp; ETFs on Revolut ({len(stocks)})</h1>
<p>Complete list of equities and exchange-traded funds available to trade on Revolut in 2025‑2026.</p>
<table><thead><tr><th>Ticker</th><th>Name</th><th>Guide</th><th>Compare</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><a href="/revolut-crypto">→ View Crypto List</a></p>
"""
    return _seo_wrap(
        f"All Stocks on Revolut 2025‑2026 – Complete List",
        f"Complete list of {len(stocks)} stocks and ETFs tradeable on Revolut. Updated daily.",
        f"{SITE_URL}/revolut-stocks",
        body,
    )


@app.get("/revolut-crypto", response_class=HTMLResponse)
async def revolut_crypto_list():
    cryptos = sorted(revolut.REVOLUT_CRYPTO)
    items = "".join(
        f'<li><a href="/ticker/{c}">{c}</a> — '
        f'<a href="/guide/{c}">How to Buy</a> | '
        f'<a href="/revolut-vs-etoro/{c}">vs eToro</a></li>'
        for c in cryptos
    )
    body = f"""
<h1>All Cryptocurrencies on Revolut ({len(cryptos)})</h1>
<p>Full list of crypto assets available to buy and sell on Revolut in 2025‑2026.</p>
<ul>{items}</ul>
<p><a href="/revolut-stocks">→ View Stocks List</a></p>
"""
    return _seo_wrap(
        f"All Crypto on Revolut 2025‑2026 – Complete List",
        f"Full list of {len(cryptos)} cryptocurrencies tradeable on Revolut. Including BTC, ETH, SOL, XRP.",
        f"{SITE_URL}/revolut-crypto",
        body,
    )


@app.get("/ticker/{symbol}", response_class=HTMLResponse)
async def ticker_page(symbol: str):
    sym = symbol.upper()
    ctx = await get_trading_context(sym)
    await enrich_insider_context(ctx)
    html = render_ticker_page(sym, ctx)
    return html


@app.get("/guide/{symbol}", response_class=HTMLResponse)
async def guide_page(symbol: str):
    sym = symbol.upper()
    ctx = await get_trading_context(sym)
    on_rev = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    name = (ctx.prices[0].name if ctx.prices and ctx.prices[0].name else sym)
    price = f"${ctx.prices[0].value:,.2f}" if ctx.prices else "N/A"
    avail = "✅ Available" if on_rev else "❌ Not available"
    body = f"""
<h1>How to Buy {sym} on Revolut</h1>
<p><strong>Status:</strong> {avail} | <strong>Current Price:</strong> {price}</p>
{'<p>✅ <strong>' + name + '</strong> is listed on Revolut and can be traded directly in the app.</p>' if on_rev else '<p>❌ <strong>' + sym + '</strong> is not currently available on Revolut. Consider eToro or Binance as alternatives.</p>'}
<h2>Step 1: Open a Revolut Account</h2>
<p>Download the Revolut app (iOS/Android) and complete KYC verification.</p>
<h2>Step 2: Deposit Funds</h2>
<p>Add money via bank transfer, card, or receive from another Revolut user.</p>
<h2>Step 3: Find {sym}</h2>
<p>Tap <strong>Invest</strong> → search for <strong>{sym}</strong> → review the chart and data.</p>
<h2>Step 4: Place Your Trade</h2>
<p>Choose amount, confirm, done. Fractional shares from $1.</p>
<h2>Revolut Trading Fees</h2>
<table>
<tr><th>Plan</th><th>Fee</th><th>Monthly FX Limit</th></tr>
<tr><td>Standard</td><td>1.49%</td><td>£1,000 free</td></tr>
<tr><td>Premium</td><td>0.49%</td><td>£10,000 free</td></tr>
<tr><td>Metal</td><td>0%</td><td>Unlimited</td></tr>
</table>
<p><a href="/ticker/{sym}">← Back to {sym} overview</a> | <a href="/revolut-vs-etoro/{sym}">Compare with eToro →</a></p>
"""
    return _seo_wrap(
        f"How to Buy {sym} on Revolut – Step-by-Step Guide 2025",
        f"Step-by-step guide to buying {sym} ({name}) on Revolut. Fees, availability, and tips.",
        f"{SITE_URL}/guide/{sym}",
        body,
    )


@app.get("/revolut-vs-etoro/{symbol}", response_class=HTMLResponse)
async def comparison_page(symbol: str):
    sym = symbol.upper()
    ctx = await get_trading_context(sym)
    on_rev = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    price = f"${ctx.prices[0].value:,.2f}" if ctx.prices else "N/A"
    body = f"""
<h1>{sym}: Revolut vs eToro – Which is Better in 2025?</h1>
<p>Current price: <strong>{price}</strong></p>
<table>
<tr><th>Feature</th><th>Revolut</th><th>eToro</th></tr>
<tr><td>Availability</td><td>{'✅ Yes' if on_rev else '❌ No'}</td><td>✅ Yes</td></tr>
<tr><td>Trading Fee</td><td>0–1.49% (plan-based)</td><td>0% commission</td></tr>
<tr><td>Fractional Shares</td><td>✅ From $1</td><td>✅ From $10</td></tr>
<tr><td>Crypto Support</td><td>✅ 60+ coins</td><td>✅ 70+ coins</td></tr>
<tr><td>Copy Trading</td><td>❌</td><td>✅</td></tr>
<tr><td>FDIC/FSCS Protection</td><td>✅ (Revolut Bank)</td><td>✅ (eToro EU)</td></tr>
<tr><td>Weekend FX Surcharge</td><td>0.5–1% (plan-based)</td><td>None</td></tr>
</table>
<h2>Verdict</h2>
<p>For {sym}: {'Revolut is the better choice for existing users due to integrated banking.' if on_rev else 'Use eToro since ' + sym + ' is not on Revolut.'}</p>
<p><a href="/guide/{sym}">← Revolut guide for {sym}</a> | <a href="/ticker/{sym}">Live data →</a></p>
"""
    return _seo_wrap(
        f"Revolut vs eToro for {sym} – Fees, Availability & Comparison 2025",
        f"Compare Revolut and eToro for trading {sym}. Fees, features, and which platform to use.",
        f"{SITE_URL}/revolut-vs-etoro/{sym}",
        body,
    )


@app.get("/sitemap.xml")
async def sitemap():
    symbols = generate_all_symbols()[:150]
    today = datetime.now().strftime("%Y-%m-%d")
    urls = (
        f"<url><loc>{SITE_URL}/revolut-stocks</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"
        f"<url><loc>{SITE_URL}/revolut-crypto</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"
    )
    for sym in symbols:
        urls += f"<url><loc>{SITE_URL}/ticker/{sym}</loc><lastmod>{today}</lastmod><changefreq>hourly</changefreq></url>"
        urls += f"<url><loc>{SITE_URL}/guide/{sym}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>"
        urls += f"<url><loc>{SITE_URL}/revolut-vs-etoro/{sym}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>"
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HTMLResponse(content=xml, media_type="application/xml")


# ── MCP HTTP / JSON-RPC 2.0 ─────────────────────────────────────

@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE endpoint for MCP probe/heartbeat."""
    async def event_stream():
        yield f"event: endpoint\ndata: {json.dumps({'endpoint': '/mcp'})}\n\n"
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(30)
            yield ": heartbeat\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/mcp")
async def mcp_jsonrpc(request: Request):
    """MCP JSON-RPC 2.0 endpoint."""
    from app.mcp_server import TOOL_HANDLERS, MCP_TOOLS_SCHEMA

    body = await request.json()
    method = body.get("method", "")
    req_id = body.get("id")
    rpc: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

    try:
        if method == "initialize":
            rpc["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                "serverInfo": {"name": "revolut-pulse-mcp", "version": "5.2.1"},
            }
        elif method == "tools/list":
            rpc["result"] = {"tools": MCP_TOOLS_SCHEMA}
        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(tool_name)
            if not handler:
                rpc["error"] = {"code": -32601, "message": f"Tool not found: {tool_name}"}
            else:
                result = await handler(**arguments)
                rpc["result"] = {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
        elif method == "prompts/list":
            rpc["result"] = {"prompts": [
                {"name": "revolut_insider_scan", "description": "Insider scan for a ticker"},
                {"name": "weekly_insider_report", "description": "Weekly insider summary"},
                {"name": "market_watchlist_snapshot", "description": "Market snapshot briefing"},
                {"name": "daily_market_briefing", "description": "60-second daily briefing"},
                {"name": "revolut_trading_signal", "description": "CEO/CFO signal scanner"},
                {"name": "insider_cluster_alert", "description": "High-value cluster alerts"},
                {"name": "seo_finance_content_ideas", "description": "SEO blog title generator"},
                {"name": "daily_trading_thread", "description": "Twitter/X thread generator"},
                {"name": "seo_weekly_finance_newsletter", "description": "Weekly newsletter generator"},
            ]}
        elif method == "resources/list":
            rpc["result"] = {"resources": [
                {"uri": "revolut://tradable/symbols", "name": "Revolut tradable symbols"},
                {"uri": "revolut://plan-limits", "name": "Revolut plan limits"},
                {"uri": "revolut://tradable/etfs-by-sector", "name": "ETFs by sector"},
                {"uri": "seo://financial-keywords", "name": "SEO financial keywords"},
                {"uri": "seo://blog-post-template", "name": "Blog post template"},
            ]}
        elif method == "ping":
            rpc["result"] = {}
        else:
            rpc["error"] = {"code": -32601, "message": f"Method not found: {method}"}
    except Exception as e:
        logger.exception("MCP tool error")
        rpc["error"] = {"code": -32603, "message": str(e)}

    return JSONResponse(content=rpc)
