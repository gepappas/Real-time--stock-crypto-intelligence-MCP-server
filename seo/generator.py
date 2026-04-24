"""
SEO page renderer and symbol generator.
"""
from domain.services import TradingDecisionEngine
from infrastructure.providers.revolut import all_assets


def generate_all_symbols() -> list:
    """Return all tradable tickers for sitemap generation."""
    return [a["ticker"] for a in all_assets()]


def render_ticker_page(symbol: str, ctx) -> str:
    """Render a full SEO-optimised ticker page as HTML string."""
    rev_ok = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    best = TradingDecisionEngine.best_platform(ctx)
    mood = TradingDecisionEngine.market_mood(ctx)
    has_insider = TradingDecisionEngine.has_insider_activity(ctx)
    ceo_signal = TradingDecisionEngine.ceo_insider_signal(ctx)

    price_str = "N/A"
    change_str = ""
    vol_str = ""
    name_str = symbol
    if ctx.prices:
        p = ctx.prices[0]
        price_str = f"${p.value:,.4f}" if p.value < 10 else f"${p.value:,.2f}"
        if p.change_pct is not None:
            arrow = "▲" if p.change_pct >= 0 else "▼"
            color = "green" if p.change_pct >= 0 else "red"
            change_str = f'<span style="color:{color}">{arrow} {abs(p.change_pct):.2f}%</span>'
        if p.name:
            name_str = p.name
        if p.volume:
            vol_str = f"${p.volume:,.0f}"

    insider_rows = ""
    for t in ctx.insider_trades[:5]:
        badge = "🔑 CEO/CFO" if t.is_ceo_cfo else ("👤 Director" if t.is_director else "👤 Officer")
        insider_rows += (
            f"<tr><td>{t.insider_name}</td><td>{badge}</td>"
            f"<td>{t.transaction_type}</td><td>${t.value:,.0f}</td>"
            f"<td>{t.transaction_date or t.filing_date}</td></tr>"
        )

    insider_section = ""
    if has_insider:
        alert = ""
        if ceo_signal:
            alert = '<p style="background:#fff3cd;padding:0.5rem;border-radius:4px;">⚠️ <strong>CEO/CFO activity detected</strong> — high-conviction signal.</p>'
        insider_section = f"""
<h2>Recent Insider Activity</h2>
{alert}
<table>
<thead><tr><th>Insider</th><th>Role</th><th>Type</th><th>Value</th><th>Date</th></tr></thead>
<tbody>{insider_rows}</tbody>
</table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{symbol} Stock Price – Revolut Availability &amp; Insider Data</title>
  <meta name="description" content="Live {symbol} price, {name_str} on Revolut availability, and SEC insider filing data. Updated in real-time.">
  <meta name="robots" content="index, follow">
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem 1.5rem; }}
    .price {{ font-size: 2rem; font-weight: bold; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: bold; }}
    .available {{ background: #d4edda; color: #155724; }}
    .unavailable {{ background: #f8d7da; color: #721c24; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.9rem; }}
    th {{ background: #16213e; color: white; }}
    a {{ color: #e94560; }}
  </style>
</head>
<body>
<h1>{symbol} – {name_str}</h1>
<p class="price">{price_str} {change_str}</p>
<p>
  <span class="badge {'available' if rev_ok else 'unavailable'}">
    {'✅ On Revolut' if rev_ok else '❌ Not on Revolut'}
  </span>
  &nbsp;
  <span class="badge" style="background:#e8f4f8;color:#0c5460;">
    Best platform: {best}
  </span>
  &nbsp;
  <span>{mood}</span>
</p>
{f'<p>Volume (24h): {vol_str}</p>' if vol_str else ''}
{insider_section}
<p>
  <a href="/guide/{symbol}">How to Buy {symbol} on Revolut →</a> |
  <a href="/revolut-vs-etoro/{symbol}">Revolut vs eToro for {symbol} →</a>
</p>
<footer style="margin-top:2rem;border-top:1px solid #ddd;padding-top:1rem;font-size:0.8rem;color:#666;">
  Data from Yahoo Finance, Binance, SEC EDGAR. Not financial advice.
  <a href="/revolut-stocks">All Stocks</a> | <a href="/revolut-crypto">Crypto</a>
</footer>
</body></html>"""
