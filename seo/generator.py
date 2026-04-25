"""
SEO HTML Generator for Ticker Pages
Generates search-engine optimized pages with structured data for financial instruments.

v5.2.2 — CRITICAL FIXES:
- Full Schema.org JSON-LD (FinancialProduct, Offer, BreadcrumbList, FAQPage, Organization)
- Viewport meta for mobile-first indexing
- Twitter Cards + Open Graph with dimensions
- Semantic HTML5 (<main>, <article>, <section>, <nav>, <time>)
- Safe price extraction (no crashes on empty/missing data)
- Dark-themed CSS for better UX/dwell time
- ARIA labels and accessibility
- Keyword-rich, CTR-optimized titles and descriptions
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Domain imports — keep isolated so generator can be imported safely
try:
    from domain.services import TradingDecisionEngine
except ImportError:  # pragma: no cover
    TradingDecisionEngine = None  # type: ignore

try:
    from infrastructure.providers.revolut import all_assets
except ImportError:  # pragma: no cover
    def all_assets() -> List[Dict[str, Any]]:  # type: ignore
        return []


def generate_all_symbols() -> List[str]:
    """Return all tradable ticker symbols."""
    return [a["ticker"] for a in all_assets()]


def _safe_price(ctx: Any) -> tuple[str, str]:
    """Extract price safely; returns (display_str, iso_str)."""
    if not ctx or not getattr(ctx, "prices", None):
        return ("N/A", "")
    try:
        p = ctx.prices[0]
        val = getattr(p, "value", None)
        if val is None:
            return ("N/A", "")
        try:
            num = float(val)
            return (f"${num:,.2f}", f"{num:.2f}")
        except (ValueError, TypeError):
            return (f"${val}", str(val))
    except Exception:
        return ("N/A", "")


def _safe_best_platform(ctx: Any) -> str:
    """Return best platform name or fallback."""
    if TradingDecisionEngine is None:
        return "Multiple platforms"
    try:
        best = TradingDecisionEngine.best_platform(ctx)
        return str(best) if best else "Multiple platforms"
    except Exception:
        return "Multiple platforms"


def _is_revolut_tradable(ctx: Any) -> bool:
    """Safely check Revolut availability."""
    if TradingDecisionEngine is None:
        return False
    try:
        return bool(TradingDecisionEngine.is_tradable_on(ctx, "revolut"))
    except Exception:
        return False


def _has_insider_activity(ctx: Any) -> bool:
    """Safely check insider trades."""
    try:
        return bool(getattr(ctx, "insider_trades", None))
    except Exception:
        return False


def _build_json_ld(
    symbol: str,
    price_display: str,
    price_iso: str,
    best_platform: str,
    revolut_ok: bool,
    has_insider: bool,
    site_url: str,
    now_iso: str,
) -> str:
    """Build comprehensive Schema.org JSON-LD."""
    canonical = f"{site_url}/ticker/{symbol}"

    structured: Dict[str, Any] = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": ["WebPage", "FinancialProduct"],
                "@id": canonical,
                "url": canonical,
                "name": f"{symbol} Stock Price & Trading Guide",
                "headline": f"Is {symbol} Available on Revolut? Live Price & Fees",
                "description": f"Check {symbol} live price ({price_display}), Revolut availability, fees comparison, and step-by-step buying guide. Updated daily.",
                "dateModified": now_iso,
                "inLanguage": "en",
                "mainEntity": {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "FinancialProduct",
                        "name": symbol,
                        "tickerSymbol": symbol,
                    },
                    "availableAtOrFrom": {
                        "@type": "FinancialService",
                        "name": best_platform,
                    },
                    "price": price_iso if price_iso else "0",
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock" if revolut_ok else "https://schema.org/OutOfStock",
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "Real-Time Stock & Crypto Intelligence",
                    "url": site_url,
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Home",
                        "item": site_url,
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "All Stocks",
                        "item": f"{site_url}/revolut-stocks",
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": symbol,
                        "item": canonical,
                    },
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f"Can I buy {symbol} on Revolut?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f'{"Yes, " + symbol + " is available for trading on Revolut with real-time market data and competitive fees." if revolut_ok else "No, " + symbol + " is not currently available on Revolut. The best alternative platform is " + best_platform + "."}',
                        },
                    },
                    {
                        "@type": "Question",
                        "name": f"What is the current price of {symbol}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f'The current price of {symbol} is {price_display}. Prices are updated in real-time during market hours.',
                        },
                    },
                    {
                        "@type": "Question",
                        "name": f"Has there been recent insider trading activity for {symbol}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f'{"Yes, there have been recent insider transactions reported to the SEC for " + symbol + ". Review the latest filings before making investment decisions." if has_insider else "No recent insider trading activity has been reported for " + symbol + " in the latest SEC filings."}',
                        },
                    },
                ],
            },
        ],
    }
    return json.dumps(structured, ensure_ascii=False)


def render_page(symbol: str, ctx: Any, site_url: Optional[str] = None) -> str:
    """
    Render a fully SEO-optimized ticker page.

    Args:
        symbol: The stock/crypto ticker symbol.
        ctx: Data context with prices, insider_trades, etc.
        site_url: Base URL for canonical/OG tags. Falls back to SITE_URL env var.
    """
    if site_url is None:
        site_url = os.getenv("SITE_URL", "").rstrip("/")
    if not site_url:
        site_url = "https://example.com"

    price_display, price_iso = _safe_price(ctx)
    best_platform = _safe_best_platform(ctx)
    revolut_ok = _is_revolut_tradable(ctx)
    has_insider = _has_insider_activity(ctx)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_human = now.strftime("%B %d, %Y at %H:%M UTC")

    canonical = f"{site_url}/ticker/{symbol}"
    guide_url = f"{site_url}/guide/{symbol}"
    vs_url = f"{site_url}/revolut-vs-etoro/{symbol}"
    og_image = f"{site_url}/assets/og-ticker.png"

    json_ld = _build_json_ld(
        symbol=symbol,
        price_display=price_display,
        price_iso=price_iso,
        best_platform=best_platform,
        revolut_ok=revolut_ok,
        has_insider=has_insider,
        site_url=site_url,
        now_iso=now_iso,
    )

    revolut_badge = "✅ Available on Revolut" if revolut_ok else "❌ Not available on Revolut"
    revolut_meta = "Available" if revolut_ok else "Not Available"

    insider_text = (
        "Recent insider filings detected — see SEC EDGAR for details."
        if has_insider
        else "No recent insider activity reported."
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{symbol} Price & Availability 2026 — Revolut, Fees & Live Data</title>
    <meta name="description" content="Is {symbol} on Revolut? Live price {price_display}, platform comparison, trading fees, and step-by-step buying guide. Updated {now_human.split(" at ")[0]}.">
    <meta name="author" content="Real-Time Stock & Crypto Intelligence">
    <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
    <meta name="googlebot" content="index, follow">
    <link rel="canonical" href="{canonical}">
    <link rel="preconnect" href="https://fonts.googleapis.com">

    <!-- Open Graph / Facebook -->
    <meta property="og:title" content="{symbol} on Revolut — Live Price & Trading Guide">
    <meta property="og:description" content="Check if {symbol} is available on Revolut. Current price: {price_display}. Compare fees and start trading.">
    <meta property="og:url" content="{canonical}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="Real-Time Stock & Crypto Intelligence">
    <meta property="og:image" content="{og_image}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="article:modified_time" content="{now_iso}">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{symbol} Price & Revolut Availability">
    <meta name="twitter:description" content="Live {symbol} price ({price_display}), Revolut status, and fee comparison.">
    <meta name="twitter:image" content="{og_image}">

    <!-- Theme & Mobile -->
    <meta name="theme-color" content="#0f172a">
    <meta name="msapplication-TileColor" content="#0f172a">

    <!-- Structured Data -->
    <script type="application/ld+json">
    {json_ld}
    </script>

    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --text: #f8fafc;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --success: #22c55e;
            --danger: #ef4444;
            --radius: 0.75rem;
            --max-width: 768px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 1rem;
        }}
        .container {{
            max-width: var(--max-width);
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 1.5rem;
        }}
        .breadcrumb {{
            font-size: 0.875rem;
            color: var(--muted);
            margin-bottom: 0.5rem;
        }}
        .breadcrumb a {{
            color: var(--accent);
            text-decoration: none;
        }}
        .breadcrumb a:hover {{ text-decoration: underline; }}
        h1 {{
            font-size: 1.875rem;
            font-weight: 800;
            letter-spacing: -0.025em;
            line-height: 1.2;
        }}
        h1 span {{
            color: var(--accent);
        }}
        .tagline {{
            color: var(--muted);
            margin-top: 0.25rem;
            font-size: 1rem;
        }}
        .card {{
            background: var(--surface);
            border-radius: var(--radius);
            padding: 1.25rem;
            margin-bottom: 1rem;
            border: 1px solid #334155;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .stat {{
            display: flex;
            flex-direction: column;
        }}
        .stat-label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--muted);
            margin-bottom: 0.25rem;
        }}
        .stat-value {{
            font-size: 1.25rem;
            font-weight: 700;
        }}
        .price {{
            font-size: 2rem;
            color: var(--accent);
        }}
        .status {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
        }}
        .status.available {{ color: var(--success); }}
        .status.unavailable {{ color: var(--danger); }}
        .actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.625rem 1.25rem;
            border-radius: var(--radius);
            font-weight: 600;
            text-decoration: none;
            font-size: 0.9375rem;
            transition: opacity 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; }}
        .btn-primary {{
            background: var(--accent);
            color: var(--bg);
        }}
        .btn-secondary {{
            background: #334155;
            color: var(--text);
        }}
        .insider {{
            font-size: 0.9375rem;
            color: var(--muted);
        }}
        .insider strong {{
            color: var(--text);
        }}
        footer {{
            margin-top: 2rem;
            padding-top: 1.5rem;
            border-top: 1px solid #334155;
            font-size: 0.875rem;
            color: var(--muted);
            text-align: center;
        }}
        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}
        footer a:hover {{ text-decoration: underline; }}
        .disclaimer {{
            margin-top: 0.75rem;
            font-size: 0.75rem;
            opacity: 0.8;
        }}
        @media (max-width: 480px) {{
            h1 {{ font-size: 1.5rem; }}
            .price {{ font-size: 1.5rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <nav aria-label="Breadcrumb">
                <ol class="breadcrumb" itemscope itemtype="https://schema.org/BreadcrumbList">
                    <li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
                        <a itemprop="item" href="{site_url}"><span itemprop="name">Home</span></a>
                        <meta itemprop="position" content="1">
                    </li>
                    <li> / </li>
                    <li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
                        <a itemprop="item" href="{site_url}/revolut-stocks"><span itemprop="name">All Stocks</span></a>
                        <meta itemprop="position" content="2">
                    </li>
                    <li> / </li>
                    <li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
                        <span itemprop="name">{symbol}</span>
                        <meta itemprop="item" content="{canonical}">
                        <meta itemprop="position" content="3">
                    </li>
                </ol>
            </nav>
            <h1><span>{symbol}</span> Price, Fees & Revolut Availability</h1>
            <p class="tagline">Real-time data, platform comparison, and insider activity for {symbol}.</p>
        </header>

        <main>
            <article>
                <section class="card" aria-labelledby="price-heading">
                    <h2 id="price-heading" class="sr-only" style="position:absolute;left:-10000px;">Market Data</h2>
                    <div class="grid">
                        <div class="stat">
                            <span class="stat-label">Current Price</span>
                            <span class="stat-value price" itemprop="price" content="{price_iso}">{price_display}</span>
                            <meta itemprop="priceCurrency" content="USD">
                        </div>
                        <div class="stat">
                            <span class="stat-label">Best Platform</span>
                            <span class="stat-value">{best_platform}</span>
                        </div>
                        <div class="stat">
                            <span class="stat-label">Revolut Status</span>
                            <span class="stat-value status {"available" if revolut_ok else "unavailable"}">{revolut_badge}</span>
                        </div>
                        <div class="stat">
                            <span class="stat-label">Insider Activity</span>
                            <span class="stat-value">{"Yes" if has_insider else "No"}</span>
                        </div>
                    </div>
                </section>

                <section class="card" aria-labelledby="insider-heading">
                    <h2 id="insider-heading" class="stat-label" style="margin-bottom:0.5rem;">Insider Trading Summary</h2>
                    <p class="insider">{insider_text}</p>
                </section>

                <section class="card" aria-labelledby="actions-heading">
                    <h2 id="actions-heading" class="stat-label" style="margin-bottom:0.75rem;">Quick Actions</h2>
                    <div class="actions">
                        <a class="btn btn-primary" href="{guide_url}">📘 How to Buy {symbol}</a>
                        <a class="btn btn-secondary" href="{vs_url}">⚖️ Revolut vs eToro</a>
                        <a class="btn btn-secondary" href="{site_url}/revolut-stocks">📋 All Stocks</a>
                    </div>
                </section>
            </article>
        </main>

        <footer>
            <p>Last updated: <time datetime="{now_iso}">{now_human}</time></p>
            <p>Data sources: Yahoo Finance, Binance, SEC EDGAR. Prices are indicative.</p>
            <p class="disclaimer">Not financial advice. Always do your own research before investing.</p>
            <p style="margin-top:0.75rem;">
                <a href="{site_url}/sitemap.xml">Sitemap</a> · 
                <a href="{site_url}/revolut-stocks">All Stocks</a> · 
                <a href="{site_url}/privacy">Privacy</a>
            </p>
        </footer>
    </div>
</body>
</html>"""
    return html


# Backward-compat alias — supports both old and new api.py imports
render_ticker_page = render_page
