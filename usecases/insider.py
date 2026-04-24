from datetime import datetime
from domain.models import TradingContext
from infrastructure.providers import sec, revolut


async def enrich_insider_context(ctx: TradingContext, limit: int = 25):
    """Add insider trading data to an existing TradingContext in place."""
    trades = await sec.get_recent_insider_trades(ticker=ctx.symbol, limit=limit)
    ctx.insider_trades.extend(trades)


async def get_cluster_context() -> list:
    """Return all multi-insider clusters from the last 7 days."""
    return await sec.get_insider_clusters(days=7)


async def get_weekly_summary() -> dict:
    """Generate a structured weekly insider trading summary with Revolut tagging."""
    trades = await sec.get_recent_insider_trades(limit=100)
    if not trades:
        return {"error": "No filings found this week", "total_filings": 0}

    by_ticker: dict = {}
    for t in trades:
        by_ticker.setdefault(t.ticker, []).append(t)

    ticker_summary = []
    sorted_tickers = sorted(
        by_ticker.items(),
        key=lambda x: sum(t.value or 0 for t in x[1]),
        reverse=True,
    )[:10]

    for ticker, ticker_trades in sorted_tickers:
        total_val = sum(t.value or 0 for t in ticker_trades)
        unique_insiders = len({t.insider_name for t in ticker_trades})
        ticker_summary.append({
            "ticker": ticker,
            "trade_count": len(ticker_trades),
            "unique_insiders": unique_insiders,
            "total_value": round(total_val, 2),
            "revolut_available": ticker in revolut.REVOLUT_STOCKS,
            "has_ceo_cfo": any(t.is_ceo_cfo for t in ticker_trades),
        })

    ceo_trades = [t for t in trades if t.is_ceo_cfo]
    return {
        "week": datetime.now().strftime("%Y-W%U"),
        "total_filings": len(trades),
        "top_tickers": ticker_summary,
        "ceo_cfo_count": len(ceo_trades),
        "revolut_tradable_count": sum(1 for t in ticker_summary if t["revolut_available"]),
        "source": "SEC EDGAR",
    }
