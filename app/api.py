"""
FastAPI application: SEO pages + MCP HTTP/JSON-RPC transport.
v5.2.2 – CRITICAL FIXES: sitemap XML, HTML wrapper, viewport, error handling, OG image.
"""
import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from usecases.trading import get_trading_context
from usecases.insider import enrich_insider_context
from domain.services import TradingDecisionEngine
from infrastructure.providers import revolut, binance, frankfurter
from seo.generator import render_page, generate_all_symbols

logger = logging.getLogger("api")

# ── Configuration ──────────────────────────────────────────────────────────
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")
if not SITE_URL:
    import warnings
    warnings.warn("SITE_URL env var not set — canonical URLs, sitemap and OG tags will be broken for SEO.")
AUTHOR = os.getenv("AUTHOR_NAME", "Real-Time Stock & Crypto Intelligence")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
OG_IMAGE_URL = os.getenv("OG_IMAGE_URL", "")

# ── Lifespan: init DB once, non-blocking ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from saas.database import engine, Base
        from saas.billing import seed_plans
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_plans()
        logger.info("Database initialised and billing plans seeded")
    except Exception as exc:
        logger.warning("Database init skipped: %s", exc)
    yield
    logger.info("Shutting down")

app = FastAPI(
    title="Real-Time Stock & Crypto Intelligence MCP",
    version="5.2.2",
    description="Real-time stock/crypto intelligence + insider tracking MCP server",
    lifespan=lifespan,
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
    og_image_tag = f'\n    <meta property="og:image" content="{OG_IMAGE_URL}">\n    <meta property="og:image:width" content="1200">\n    <meta property="og:image:height" content="630">' if OG_IMAGE_URL else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="author" content="{AUTHOR}">
    <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
    <link rel="canonical" href="{canonical}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="{AUTHOR}">{og_image_tag}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    {f'<meta name="twitter:image" content="{OG_IMAGE_URL}">' if OG_IMAGE_URL else ""}
    <script type="application/ld+json">
    {schema}
    </script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 768px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #f8fafc; background: #0f172a; }}
        h1, h2 {{ color: #38bdf8; }}
        a {{ color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ border: 1px solid #334155; padding: 0.5rem; text-align: left; }}
        th {{ background: #1e293b; }}
        .muted {{ color: #94a3b8; font-size: 0.9rem; }}
        footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; font-size: 0.85rem; color: #94a3b8; }}
    </style>
</head>
<body>
{body}
<footer>
    <p>Last updated: <time datetime="{now_iso}">{now_human}</time></p>
    <p>Data from Yahoo Finance, Binance, SEC EDGAR. Not financial advice.</p>
    <p><a href="{SITE_URL}/sitemap.xml">Sitemap</a> · <a href="{SITE_URL}/revolut-stocks">All Stocks</a></p>
</footer>
</body>
</html>"""

# ── Health & Status ───────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "5.2.2",
        "tools": 38,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ping")
async def ping():
    """MCPize / Railway / Cloud Run startup probe — must respond 200 before traffic is routed."""
    return {"status": "ok"}

@app.get("/")
async def root():
    return JSONResponse({
        "name": "real-time-stock-crypto-intelligence",
        "version": "5.2.2",
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
        f'<tr><td><strong>{k}</strong></td><td>{v}</td><td><a href="{SITE_URL}/guide/{k}">Guide</a></td><td><a href="{SITE_URL}/revolut-vs-etoro/{k}">vs eToro</a></td></tr>'
        for k, v in stocks
    )
    year = datetime.now().year
    body = f"""
<h1>All Stocks & ETFs on Revolut ({len(stocks)})</h1>
<p class="muted">Complete list of equities and exchange-traded funds available to trade on Revolut in {year}.</p>
<table>
<thead><tr><th>Ticker</th><th>Name</th><th>Guide</th><th>Compare</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p><a href="{SITE_URL}/revolut-crypto">→ View Crypto List</a></p>
"""
    return _seo_wrap(
        f"All Stocks on Revolut {year} – Complete List",
        f"Complete list of {len(stocks)} stocks and ETFs tradeable on Revolut. Updated daily.",
        f"{SITE_URL}/revolut-stocks",
        body,
    )

@app.get("/revolut-crypto", response_class=HTMLResponse)
async def revolut_crypto_list():
    cryptos = sorted(revolut.REVOLUT_CRYPTO)
    items = "".join(
        f'<li><strong>{c}</strong> — <a href="{SITE_URL}/guide/{c}">How to Buy</a> · <a href="{SITE_URL}/revolut-vs-etoro/{c}">vs eToro</a></li>'
        for c in cryptos
    )
    year = datetime.now().year
    body = f"""
<h1>All Cryptocurrencies on Revolut ({len(cryptos)})</h1>
<p class="muted">Full list of crypto assets available to buy and sell on Revolut in {year}.</p>
<ul>{items}</ul>
<p><a href="{SITE_URL}/revolut-stocks">→ View Stocks List</a></p>
"""
    return _seo_wrap(
        f"All Crypto on Revolut {year} – Complete List",
        f"Full list of {len(cryptos)} cryptocurrencies tradeable on Revolut. Including BTC, ETH, SOL, XRP.",
        f"{SITE_URL}/revolut-crypto",
        body,
    )

@app.get("/ticker/{symbol}", response_class=HTMLResponse)
async def ticker_page(symbol: str):
    sym = symbol.upper()
    # Validate ticker format to prevent injection / junk requests
    if not re.fullmatch(r"[A-Z0-9\-\.]{1,20}", sym):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    try:
        ctx = await get_trading_context(sym)
        await enrich_insider_context(ctx)
    except Exception as exc:
        logger.exception("Failed to build trading context for %s", sym)
        raise HTTPException(status_code=503, detail=f"Data temporarily unavailable for {sym}")
    html = render_page(sym, ctx, site_url=SITE_URL)
    return html

@app.get("/guide/{symbol}", response_class=HTMLResponse)
async def guide_page(symbol: str):
    sym = symbol.upper()
    if not re.fullmatch(r"[A-Z0-9\-\.]{1,20}", sym):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    try:
        ctx = await get_trading_context(sym)
    except Exception as exc:
        logger.exception("Failed to build guide context for %s", sym)
        raise HTTPException(status_code=503, detail=f"Data temporarily unavailable for {sym}")
    on_rev = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    name = (ctx.prices[0].name if ctx.prices and ctx.prices[0].name else sym)
    price = f"${ctx.prices[0].value:,.2f}" if ctx.prices and ctx.prices[0].value else "N/A"
    avail = "✅ Available" if on_rev else "❌ Not available"
    body = f"""
<h1>How to Buy {sym} on Revolut</h1>
<p><strong>Status:</strong> {avail} · <strong>Current Price:</strong> {price}</p>
{"<p>✅ <strong>" + name + "</strong> is listed on Revolut and can be traded directly in the app.</p>" if on_rev else "<p>❌ <strong>" + sym + "</strong> is not currently available on Revolut. Consider eToro or Binance as alternatives.</p>"}
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
<thead><tr><th>Plan</th><th>Fee</th><th>Monthly FX Limit</th></tr></thead>
<tbody>
<tr><td>Standard</td><td>1.49%</td><td>£1,000 free</td></tr>
<tr><td>Premium</td><td>0.49%</td><td>£10,000 free</td></tr>
<tr><td>Metal</td><td>0%</td><td>Unlimited</td></tr>
</tbody>
</table>
<p><a href="{SITE_URL}/ticker/{sym}">← Back to {sym} overview</a> · <a href="{SITE_URL}/revolut-vs-etoro/{sym}">Compare with eToro →</a></p>
"""
    return _seo_wrap(
        f"How to Buy {sym} on Revolut – Step-by-Step Guide {datetime.now().year}",
        f"Step-by-step guide to buying {sym} ({name}) on Revolut. Fees, availability, and tips.",
        f"{SITE_URL}/guide/{sym}",
        body,
    )

@app.get("/revolut-vs-etoro/{symbol}", response_class=HTMLResponse)
async def comparison_page(symbol: str):
    sym = symbol.upper()
    if not re.fullmatch(r"[A-Z0-9\-\.]{1,20}", sym):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    try:
        ctx = await get_trading_context(sym)
    except Exception as exc:
        logger.exception("Failed to build comparison context for %s", sym)
        raise HTTPException(status_code=503, detail=f"Data temporarily unavailable for {sym}")
    on_rev = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    price = f"${ctx.prices[0].value:,.2f}" if ctx.prices and ctx.prices[0].value else "N/A"
    year = datetime.now().year
    body = f"""
<h1>{sym}: Revolut vs eToro – Which is Better in {year}?</h1>
<p>Current price: <strong>{price}</strong></p>
<table>
<thead><tr><th>Feature</th><th>Revolut</th><th>eToro</th></tr></thead>
<tbody>
<tr><td>Availability</td><td>{"✅ Yes" if on_rev else "❌ No"}</td><td>✅ Yes</td></tr>
<tr><td>Trading Fee</td><td>0–1.49% (plan-based)</td><td>0% commission</td></tr>
<tr><td>Fractional Shares</td><td>✅ From $1</td><td>✅ From $10</td></tr>
<tr><td>Crypto Support</td><td>✅ 60+ coins</td><td>✅ 70+ coins</td></tr>
<tr><td>Copy Trading</td><td>❌</td><td>✅</td></tr>
<tr><td>FDIC/FSCS Protection</td><td>✅ (Revolut Bank)</td><td>✅ (eToro EU)</td></tr>
<tr><td>Weekend FX Surcharge</td><td>0.5–1% (plan-based)</td><td>None</td></tr>
</tbody>
</table>
<h2>Verdict</h2>
<p>For {sym}: {"Revolut is the better choice for existing users due to integrated banking." if on_rev else f"Use eToro since {sym} is not on Revolut."}</p>
<p><a href="{SITE_URL}/guide/{sym}">← Revolut guide for {sym}</a> · <a href="{SITE_URL}/ticker/{sym}">Live data →</a></p>
"""
    return _seo_wrap(
        f"Revolut vs eToro for {sym} – Fees, Availability & Comparison {year}",
        f"Compare Revolut and eToro for trading {sym}. Fees, features, and which platform to use.",
        f"{SITE_URL}/revolut-vs-etoro/{sym}",
        body,
    )

@app.get("/sitemap.xml")
async def sitemap():
    symbols = generate_all_symbols()
    today = datetime.now().strftime("%Y-%m-%d")
    urls = []
    urls.append(f"  <url>\n    <loc>{SITE_URL}/revolut-stocks</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>")
    urls.append(f"  <url>\n    <loc>{SITE_URL}/revolut-crypto</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>")
    for sym in symbols:
        urls.append(f"  <url>\n    <loc>{SITE_URL}/ticker/{sym}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>hourly</changefreq>\n    <priority>0.8</priority>\n  </url>")
        urls.append(f"  <url>\n    <loc>{SITE_URL}/guide/{sym}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>")
        urls.append(f"  <url>\n    <loc>{SITE_URL}/revolut-vs-etoro/{sym}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>")
    urls_joined = "\n".join(urls)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_joined}
</urlset>"""
    return HTMLResponse(content=xml, media_type="application/xml")

# ── MCP HTTP / JSON-RPC 2.0 ─────────────────────────────────────

@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE endpoint for MCP probe/heartbeat."""
    async def event_stream():
        endpoint_data = json.dumps({'endpoint': '/mcp'})
        yield f"event: endpoint\ndata: {endpoint_data}\n\n"
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
                "serverInfo": {"name": "real-time-stock-crypto-intelligence", "version": "5.2.2"},
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
