from domain.services import TradingDecisionEngine
from infrastructure.providers.revolut import all_assets
from datetime import datetime
import os

def generate_all_symbols() -> list:
    return [a["ticker"] for a in all_assets()]

def render_page(symbol: str, ctx, site_url: str = None) -> str:
    if site_url is None:
        site_url = os.getenv("SITE_URL", "").rstrip("/")
    revolut_ok = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    best = TradingDecisionEngine.best_platform(ctx)
    price = f"${ctx.prices[0].value}" if ctx.prices else "N/A"
    insider = "Yes" if ctx.insider_trades else "No"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{symbol} on Revolut – Price, Fees & Availability</title>
    <meta name="description" content="Check if {symbol} is available on Revolut. Current price, insider trades, and step‑by‑step buying guide.">
    <meta name="author" content="Real-Time Stock & Crypto Intelligence">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{site_url}/ticker/{symbol}">
    <meta property="og:title" content="{symbol} on Revolut – Can You Trade It?">
    <meta property="og:description" content="Check if {symbol} is available on Revolut and where to buy it. Real‑time data.">
    <meta property="og:url" content="{site_url}/ticker/{symbol}">
    <meta property="og:type" content="article">
</head>
<body>
<h1>{symbol} Trading Availability</h1>
<p><strong>Current price:</strong> {price}<br>
<strong>Best platform:</strong> {best}<br>
<strong>Revolut:</strong> {'✅ Available' if revolut_ok else '❌ Not available'}<br>
<strong>Recent insider activity:</strong> {insider}</p>
<p><a href="/guide/{symbol}">How to Buy on Revolut</a> | <a href="/revolut-vs-etoro/{symbol}">Revolut vs eToro</a></p>
<footer style="margin-top:2em;font-size:0.9em;color:#666;">
    <p>Last updated: {datetime.now().strftime('%B %d, %Y')}</p>
    <p>Data from Yahoo Finance, Binance, SEC EDGAR. Not financial advice.</p>
    <p><a href="/sitemap.xml">Sitemap</a> | <a href="/revolut-stocks">All Stocks</a></p>
</footer>
</body></html>"""

# Backward-compat alias — supports both old and new api.py imports
render_ticker_page = render_page
