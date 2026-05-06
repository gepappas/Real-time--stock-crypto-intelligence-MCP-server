"""
revolut-pulse-mcp — MCP Server
Split-tool architecture: 38 tools · 17 prompts · 5 resources

  TOOLS_MODE=market   → 19 market-data + insider tools  (no Revolut creds needed)
  TOOLS_MODE=revolut  → 19 banking/trading tools         (per-user Revolut creds)
  TOOLS_MODE=all      → all 38 tools  (local dev / legacy)

FastMCP for stdio transport; TOOL_HANDLERS + MCP_TOOLS_SCHEMA for HTTP/JSON-RPC.
Both transports now respect TOOLS_MODE so mcpize-market.yaml and
mcpize-revolut.yaml produce correctly scoped deployments.
"""
import json
import os
from datetime import datetime
from typing import Optional, List

from fastmcp import FastMCP
from usecases.trading import get_trading_context
from usecases.insider import enrich_insider_context, get_cluster_context, get_weekly_summary
from domain.services import TradingDecisionEngine
from infrastructure.providers import binance, yahoo, revolut, sec, frankfurter

# ── Tool-split mode ────────────────────────────────────────────────────────
# Set by mcpize-market.yaml / mcpize-revolut.yaml via the TOOLS_MODE secret.
TOOLS_MODE = os.getenv("TOOLS_MODE", "all").lower()

MARKET_TOOL_NAMES = {
    "get_price", "get_prices_bulk", "get_crypto_price", "price_snapshot",
    "revolut_price_check", "crypto_top_movers",
    "get_insider_filings", "get_insider_clusters", "get_insider_weekly_summary",
    "search_revolut_tradable", "cross_reference_insider_revolut",
    "get_revolut_tradable_list",
    "get_exchange_rate", "convert_currency", "get_revolut_fx_fees",
    "create_alert", "list_alerts", "delete_alert", "register_webhook",
}

REVOLUT_TOOL_NAMES = {
    "get_accounts", "get_account_balance",
    "get_pockets", "get_pocket_detail",
    "get_transactions", "get_transaction_detail", "get_spending_by_category",
    "send_domestic_payment", "send_international_payment", "create_standing_order",
    "get_payment_status", "get_scheduled_payments", "get_account_statement",
    "get_multi_currency_balances",
    "get_crypto_tickers", "get_crypto_orders", "place_crypto_order",
    "get_crypto_trades", "get_crypto_ohlc",
}

_server_name = {
    "market": "market-data-intelligence",
    "revolut": "revolut-banking",
}.get(TOOLS_MODE, "real-time-stock-crypto-intelligence")

mcp = FastMCP(_server_name)


# ══════════════════════════════════════════════════════════════════════════════
#  PRICE TOOLS  (6)
# ══════════════════════════════════════════════════════════════════════════════

async def get_price(ticker: str) -> dict:
    """Get current stock/ETF price with Revolut availability flag."""
    ctx = await get_trading_context(ticker)
    if not ctx.prices:
        return {"ticker": ticker.upper(), "error": "No price data available"}
    p = ctx.prices[0]
    rev_ok = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    return {
        "ticker": p.symbol,
        "name": p.name,
        "price": p.value,
        "change_pct": p.change_pct,
        "currency": p.currency,
        "source": p.source,
        "revolut_available": rev_ok,
        "last_updated": ctx.last_updated,
    }


async def get_prices_bulk(tickers: List[str]) -> dict:
    """Get prices for up to 20 tickers at once with gainer/loser summary."""
    results = []
    for t in tickers[:20]:
        r = await get_price(t)
        results.append(r)
    valid = [r for r in results if "error" not in r]
    gainers = sorted(valid, key=lambda x: x.get("change_pct") or 0, reverse=True)[:3]
    losers = sorted(valid, key=lambda x: x.get("change_pct") or 0)[:3]
    avg = sum(r.get("change_pct") or 0 for r in valid) / len(valid) if valid else 0
    return {
        "count": len(results),
        "results": results,
        "summary": {
            "gainers": gainers,
            "losers": losers,
            "avg_change_pct": round(avg, 2),
            "market_mood": "🟢 Risk-On" if avg > 0 else "🔴 Risk-Off",
        },
    }


async def get_crypto_price(symbol: str) -> dict:
    """Get real-time crypto price from Binance 24hr ticker."""
    p = await binance.get_crypto_price(symbol)
    if not p:
        return {"symbol": symbol.upper(), "error": "Not found on Binance USDT pairs"}
    return {
        "symbol": p.symbol,
        "price": p.value,
        "change_pct": p.change_pct,
        "volume_usd_24h": p.volume,
        "high_24h": p.high_24h,
        "low_24h": p.low_24h,
        "source": "binance",
        "revolut_crypto": p.symbol in revolut.REVOLUT_CRYPTO,
    }


async def price_snapshot(tickers: Optional[List[str]] = None) -> dict:
    """Rich market snapshot: default watchlist or custom tickers."""
    DEFAULT_STOCKS = ["NVDA", "AAPL", "MSFT", "TSLA", "LMT", "RTX", "GLD", "SPY", "META", "AMZN"]
    DEFAULT_CRYPTO = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
    if tickers:
        upper = [t.upper().strip() for t in tickers[:25]]
        stock_list = [t for t in upper if t not in revolut.KNOWN_CRYPTO]
        crypto_list = [t for t in upper if t in revolut.KNOWN_CRYPTO]
    else:
        stock_list, crypto_list = DEFAULT_STOCKS, DEFAULT_CRYPTO

    stock_results = [await get_price(t) for t in stock_list]
    crypto_results = [await get_crypto_price(t) for t in crypto_list]
    all_valid = [r for r in stock_results + crypto_results if "error" not in r]
    avg_chg = sum(r.get("change_pct") or 0 for r in all_valid) / len(all_valid) if all_valid else 0
    top_g = max(all_valid, key=lambda x: x.get("change_pct") or 0, default=None)
    top_l = min(all_valid, key=lambda x: x.get("change_pct") or 0, default=None)
    return {
        "stocks": stock_results,
        "crypto": crypto_results,
        "summary": {
            "total_assets": len(all_valid),
            "avg_change_pct": round(avg_chg, 2),
            "market_mood": "🟢 Risk-On" if avg_chg > 0 else "🔴 Risk-Off",
            "top_gainer": {"ticker": top_g.get("ticker") or top_g.get("symbol"), "change_pct": top_g.get("change_pct")} if top_g else None,
            "top_loser": {"ticker": top_l.get("ticker") or top_l.get("symbol"), "change_pct": top_l.get("change_pct")} if top_l else None,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    }


async def revolut_price_check(ticker: str) -> dict:
    """One-stop check: price + Revolut availability + quick verdict."""
    ctx = await get_trading_context(ticker)
    rev_ok = TradingDecisionEngine.is_tradable_on(ctx, "revolut")
    price_val = ctx.prices[0].value if ctx.prices else "N/A"
    chg = ctx.prices[0].change_pct if ctx.prices else None
    return {
        "ticker": ticker.upper(),
        "price": price_val,
        "change_pct": chg,
        "revolut_available": rev_ok,
        "quick_verdict": f"{'✅' if rev_ok else '❌'} {ticker.upper()} {'is' if rev_ok else 'is NOT'} on Revolut — ${price_val}",
        "best_platform": TradingDecisionEngine.best_platform(ctx),
    }


async def crypto_top_movers(limit: int = 10, min_volume_usd: float = 10_000_000) -> dict:
    """Top crypto gainers & losers from Binance (filtered by 24h volume)."""
    return await binance.get_crypto_top_movers(limit=limit, min_volume_usd=min_volume_usd)


# ══════════════════════════════════════════════════════════════════════════════
#  INSIDER TOOLS  (5)
# ══════════════════════════════════════════════════════════════════════════════

async def get_insider_filings(ticker: Optional[str] = None, limit: int = 25) -> dict:
    """Fetch Form 4 insider filings from SEC EDGAR."""
    trades = await sec.get_recent_insider_trades(ticker=ticker, limit=limit)
    ceo = [t for t in trades if t.is_ceo_cfo]
    rev_tradable = [t for t in trades if t.ticker in revolut.REVOLUT_STOCKS]
    return {
        "filings": [t.__dict__ for t in trades],
        "count": len(trades),
        "summary": {
            "ceo_cfo_trades": len(ceo),
            "total_value_usd": round(sum(t.value or 0 for t in trades), 2),
            "revolut_tradable_count": len(rev_tradable),
        },
        "source": "SEC EDGAR",
        "ticker_filter": ticker,
    }


async def get_insider_clusters(days: int = 7) -> dict:
    """Detect multiple insiders trading the same ticker on the same day."""
    clusters = await sec.get_insider_clusters(days=days)
    high_value = [c for c in clusters if c["total_value"] >= 1_000_000]
    return {
        "clusters": clusters,
        "count": len(clusters),
        "high_value_count": len(high_value),
        "high_value_clusters": high_value[:5],
        "source": "SEC EDGAR",
    }


async def get_insider_weekly_summary() -> dict:
    """Structured weekly insider summary with top 10 tickers & CEO count."""
    return await get_weekly_summary()


async def search_revolut_tradable(query: str) -> dict:
    """Search Revolut tradable assets by ticker or name substring."""
    results = revolut.search_assets(query)
    return {"query": query, "results": results, "count": len(results)}


async def cross_reference_insider_revolut(limit: int = 25) -> dict:
    """Find insider filings where the stock is tradable on Revolut."""
    trades = await sec.get_recent_insider_trades(limit=limit)
    rev_trades = [t for t in trades if t.ticker in revolut.REVOLUT_STOCKS]
    ceo_rev = [t for t in rev_trades if t.is_ceo_cfo]
    return {
        "revolut_tradable_count": len(rev_trades),
        "ceo_cfo_on_revolut": len(ceo_rev),
        "top_opportunity": rev_trades[0].__dict__ if rev_trades else None,
        "all_revolut_trades": [t.__dict__ for t in rev_trades[:10]],
        "source": "SEC EDGAR x Revolut",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REVOLUT ASSET TOOLS  (2)
# ══════════════════════════════════════════════════════════════════════════════

async def get_revolut_tradable_list(category: str = "all") -> dict:
    """Return Revolut stocks, crypto, or full asset list."""
    if category == "stocks":
        items = [{"ticker": k, "name": v, "type": "stock"} for k, v in sorted(revolut.REVOLUT_STOCKS.items())]
        return {"category": "stocks", "count": len(items), "assets": items}
    elif category == "crypto":
        items = [{"ticker": c, "type": "crypto"} for c in sorted(revolut.REVOLUT_CRYPTO)]
        return {"category": "crypto", "count": len(items), "assets": items}
    else:
        return {
            "stock_count": len(revolut.REVOLUT_STOCKS),
            "crypto_count": len(revolut.REVOLUT_CRYPTO),
            "total": len(revolut.REVOLUT_STOCKS) + len(revolut.REVOLUT_CRYPTO),
            "etf_sectors": revolut.get_etf_sectors(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  BANKING / OPEN BANKING TOOLS  (10)
# ══════════════════════════════════════════════════════════════════════════════

async def get_accounts() -> dict:
    return {
        "error": "Revolut Open Banking not configured",
        "setup": "Set REVOLUT_CLIENT_ID, REVOLUT_CLIENT_SECRET, and mTLS cert paths.",
        "docs": "https://developer.revolut.com/docs/open-banking",
    }


async def get_account_balance(account_id: str) -> dict:
    return {"error": "Open Banking not configured", "account_id": account_id}


async def get_pockets() -> dict:
    return {
        "error": "Revolut personal API not configured",
        "setup": "Set REVOLUT_DEVICE_ID and REVOLUT_PHONE_TOKEN.",
    }


async def get_pocket_detail(pocket_id: str) -> dict:
    return {"error": "Not configured", "pocket_id": pocket_id}


async def get_transactions(account_id: str, from_date: str = None, to_date: str = None, limit: int = 50) -> dict:
    return {"error": "Not configured", "account_id": account_id}


async def get_transaction_detail(account_id: str, transaction_id: str) -> dict:
    return {"error": "Not configured", "account_id": account_id, "transaction_id": transaction_id}


async def get_spending_by_category(account_id: str, month: str = None) -> dict:
    return {"error": "Not configured", "account_id": account_id}


async def send_domestic_payment(
    amount: float,
    currency: str,
    creditor_name: str,
    creditor_account: str,
    creditor_sort_code: str = "",
    reference: str = "",
) -> dict:
    return {"error": "Not configured. Requires Open Banking PIS consent."}


async def send_international_payment(
    amount: float,
    currency: str,
    creditor_name: str,
    creditor_account: str,
    creditor_bic: str,
) -> dict:
    return {"error": "Not configured. Requires Open Banking PIS consent."}


async def create_standing_order(
    amount: float,
    currency: str,
    frequency: str,
    creditor_name: str,
    creditor_account: str,
) -> dict:
    return {"error": "Not configured. Requires Open Banking PIS consent."}


async def get_payment_status(payment_id: str, payment_type: str = "domestic") -> dict:
    return {"error": "Not configured", "payment_id": payment_id}


async def get_scheduled_payments(account_id: str) -> dict:
    return {"error": "Not configured", "account_id": account_id}


async def get_account_statement(account_id: str, from_date: str = None, to_date: str = None) -> dict:
    return {"error": "Not configured", "account_id": account_id}


async def get_multi_currency_balances() -> dict:
    return {"error": "Not configured. Requires Open Banking AIS consent."}


# ══════════════════════════════════════════════════════════════════════════════
#  FX TOOLS  (3)
# ══════════════════════════════════════════════════════════════════════════════

async def get_exchange_rate(base: str = "GBP", targets: str = "EUR,USD", date: str = None) -> dict:
    """Get FX rates from ECB via Frankfurter."""
    data = await frankfurter.get_exchange_rates(base, targets, date)
    return data or {"error": "Failed to fetch exchange rates"}


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert amount between any two currencies (ECB rates)."""
    return await frankfurter.convert_currency(amount, from_currency, to_currency)


async def get_revolut_fx_fees(
    plan: str = "standard",
    amount: float = 1000,
    from_currency: str = "GBP",
    to_currency: str = "EUR",
) -> dict:
    """Estimate Revolut FX fees based on plan and amount."""
    plans = {
        "standard": {"monthly_limit": 1000, "over_limit_fee": 0.005, "weekend_fee": 0.01},
        "premium": {"monthly_limit": 10000, "over_limit_fee": 0.0, "weekend_fee": 0.005},
        "metal": {"monthly_limit": float("inf"), "over_limit_fee": 0.0, "weekend_fee": 0.0},
    }
    p = plans.get(plan.lower(), plans["standard"])
    is_weekend = datetime.now().weekday() >= 5
    over = max(0.0, amount - p["monthly_limit"])
    fee = over * p["over_limit_fee"] + amount * (p["weekend_fee"] if is_weekend else 0)
    return {
        "plan": plan,
        "from": from_currency.upper(),
        "to": to_currency.upper(),
        "amount": amount,
        "estimated_fee_usd": round(fee, 2),
        "is_weekend": is_weekend,
        "weekend_surcharge_applied": is_weekend and p["weekend_fee"] > 0,
        "monthly_fx_limit": p["monthly_limit"],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REVOLUT X (CRYPTO EXCHANGE) TOOLS  (5)
# ══════════════════════════════════════════════════════════════════════════════

async def get_crypto_tickers() -> dict:
    return {
        "error": "Revolut X not configured",
        "setup": "Set REVOLUT_X_API_KEY and REVOLUT_X_PRIVATE_KEY.",
        "docs": "https://developer.revolut.com/docs/revolut-x",
    }


async def get_crypto_orders() -> dict:
    return {"error": "Revolut X not configured"}


async def place_crypto_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: float = None,
) -> dict:
    return {
        "error": "Revolut X not configured",
        "params_received": {
            "symbol": symbol, "side": side,
            "order_type": order_type, "quantity": quantity, "price": price,
        },
    }


async def get_crypto_trades(symbol: str = None, limit: int = 50) -> dict:
    return {"error": "Revolut X not configured", "symbol": symbol}


async def get_crypto_ohlc(symbol: str, interval: str = "1h", limit: int = 100) -> dict:
    return {
        "error": "Revolut X not configured",
        "fallback_tip": f"Use get_crypto_price('{symbol}') for current price.",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ALERT & WEBHOOK TOOLS  (4)
# ══════════════════════════════════════════════════════════════════════════════

_ALERTS: dict = {}  # In-memory store; replace with Redis/DB for production


async def create_alert(
    alert_type: str,
    target: float,
    direction: str = "above",
    ticker: str = None,
    user_id: str = "default",
) -> dict:
    """Create a price alert (stored in memory; use Redis/DB in production)."""
    alert_id = f"alert_{int(datetime.now().timestamp())}_{ticker or alert_type}"
    _ALERTS[alert_id] = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "ticker": ticker,
        "target": target,
        "direction": direction,
        "user_id": user_id,
        "status": "active",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return {"alert_id": alert_id, "status": "active", "message": f"Alert set: {ticker or alert_type} {direction} {target}"}


async def list_alerts(user_id: str = "default") -> dict:
    """List all active alerts for a user."""
    user_alerts = [a for a in _ALERTS.values() if a.get("user_id") == user_id]
    return {"alerts": user_alerts, "count": len(user_alerts)}


async def delete_alert(alert_id: str) -> dict:
    """Delete an alert by ID."""
    if alert_id in _ALERTS:
        del _ALERTS[alert_id]
        return {"status": "deleted", "alert_id": alert_id}
    return {"status": "not_found", "alert_id": alert_id}


async def register_webhook(url: str, events: Optional[List[str]] = None) -> dict:
    """Register a webhook URL for event notifications."""
    supported = ["price_alert", "insider_filing", "cluster_detected", "revolut_listing"]
    subscribed = events or supported
    return {
        "status": "registered",
        "url": url,
        "events": subscribed,
        "webhook_id": f"wh_{int(datetime.now().timestamp())}",
        "note": "Webhook persistence requires a database. Currently in-memory only.",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY  (38 tools)
# ══════════════════════════════════════════════════════════════════════════════

TOOL_HANDLERS = {
    # Price
    "get_price": get_price,
    "get_prices_bulk": get_prices_bulk,
    "get_crypto_price": get_crypto_price,
    "price_snapshot": price_snapshot,
    "revolut_price_check": revolut_price_check,
    "crypto_top_movers": crypto_top_movers,
    # Insider
    "get_insider_filings": get_insider_filings,
    "get_insider_clusters": get_insider_clusters,
    "get_insider_weekly_summary": get_insider_weekly_summary,
    "search_revolut_tradable": search_revolut_tradable,
    "cross_reference_insider_revolut": cross_reference_insider_revolut,
    # Asset list
    "get_revolut_tradable_list": get_revolut_tradable_list,
    # Banking
    "get_accounts": get_accounts,
    "get_account_balance": get_account_balance,
    "get_pockets": get_pockets,
    "get_pocket_detail": get_pocket_detail,
    "get_transactions": get_transactions,
    "get_transaction_detail": get_transaction_detail,
    "get_spending_by_category": get_spending_by_category,
    "send_domestic_payment": send_domestic_payment,
    "send_international_payment": send_international_payment,
    "create_standing_order": create_standing_order,
    "get_payment_status": get_payment_status,
    "get_scheduled_payments": get_scheduled_payments,
    "get_account_statement": get_account_statement,
    "get_multi_currency_balances": get_multi_currency_balances,
    # FX
    "get_exchange_rate": get_exchange_rate,
    "convert_currency": convert_currency,
    "get_revolut_fx_fees": get_revolut_fx_fees,
    # Revolut X
    "get_crypto_tickers": get_crypto_tickers,
    "get_crypto_orders": get_crypto_orders,
    "place_crypto_order": place_crypto_order,
    "get_crypto_trades": get_crypto_trades,
    "get_crypto_ohlc": get_crypto_ohlc,
    # Alerts / Webhooks
    "create_alert": create_alert,
    "list_alerts": list_alerts,
    "delete_alert": delete_alert,
    "register_webhook": register_webhook,
}

MCP_TOOLS_SCHEMA = [
    # ── Price tools ──────────────────────────────────────────────────────────
    {
        "name": "get_price",
        "description": "Current stock/ETF price with Revolut availability",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock or ETF ticker symbol"},
            },
            "required": ["ticker"],
            "examples": [
                {"ticker": "NVDA"},
                {"ticker": "AAPL"},
                {"ticker": "SPY"},
            ],
        },
    },
    {
        "name": "get_prices_bulk",
        "description": "Prices for up to 20 tickers at once with gainer/loser summary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "List of stock/ETF tickers (max 20)"},
            },
            "required": ["tickers"],
            "examples": [
                {"tickers": ["AAPL", "MSFT", "NVDA", "TSLA", "META"]},
                {"tickers": ["SPY", "QQQ", "GLD", "LMT", "RTX"]},
            ],
        },
    },
    {
        "name": "get_crypto_price",
        "description": "Real-time crypto price from Binance 24hr ticker",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Crypto symbol without USDT suffix"},
            },
            "required": ["symbol"],
            "examples": [
                {"symbol": "BTC"},
                {"symbol": "ETH"},
                {"symbol": "SOL"},
            ],
        },
    },
    {
        "name": "price_snapshot",
        "description": "Rich market snapshot for default or custom watchlist",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "Optional custom list; omit for default (NVDA, AAPL, MSFT, TSLA, BTC, ETH, SOL)"},
            },
            "examples": [
                {},
                {"tickers": ["NVDA", "AAPL", "BTC", "ETH", "SOL"]},
                {"tickers": ["LMT", "RTX", "BA", "GLD", "SPY"]},
            ],
        },
    },
    {
        "name": "revolut_price_check",
        "description": "Price + Revolut availability + quick buy/skip verdict",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock, ETF, or crypto symbol"},
            },
            "required": ["ticker"],
            "examples": [
                {"ticker": "TSLA"},
                {"ticker": "AMZN"},
                {"ticker": "BTC"},
            ],
        },
    },
    {
        "name": "crypto_top_movers",
        "description": "Top crypto gainers & losers from Binance by 24h volume",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Number of results per side (gainers / losers)"},
                "min_volume_usd": {"type": "number", "default": 10000000, "description": "Minimum 24h USD volume filter"},
            },
            "examples": [
                {},
                {"limit": 5, "min_volume_usd": 50000000},
                {"limit": 20, "min_volume_usd": 1000000},
            ],
        },
    },
    # ── Insider tools ────────────────────────────────────────────────────────
    {
        "name": "get_insider_filings",
        "description": "Form 4 insider filings from SEC EDGAR — CEO/CFO buy & sell transactions",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Filter to a specific company (omit for all recent filings)"},
                "limit": {"type": "integer", "default": 25, "description": "Max filings to return"},
            },
            "examples": [
                {"ticker": "NVDA", "limit": 10},
                {"ticker": "AAPL"},
                {"limit": 50},
            ],
        },
    },
    {
        "name": "get_insider_clusters",
        "description": "Detect tickers where multiple insiders traded on the same day — strong conviction signal",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Look-back window in days"},
            },
            "examples": [
                {},
                {"days": 3},
                {"days": 30},
            ],
        },
    },
    {
        "name": "get_insider_weekly_summary",
        "description": "Structured weekly insider summary: top buys, CEO/CFO count, largest trades",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    {
        "name": "search_revolut_tradable",
        "description": "Search Revolut assets by ticker or company name substring",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Ticker or partial company name"},
            },
            "required": ["query"],
            "examples": [
                {"query": "apple"},
                {"query": "NVDA"},
                {"query": "semiconductor"},
            ],
        },
    },
    {
        "name": "cross_reference_insider_revolut",
        "description": "Insider filings filtered to only tickers tradable on Revolut — actionable signal list",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 25, "description": "Max filings to cross-reference"},
            },
            "examples": [
                {},
                {"limit": 10},
                {"limit": 50},
            ],
        },
    },
    {
        "name": "get_revolut_tradable_list",
        "description": "Full Revolut asset catalogue: stocks, crypto, or both",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["all", "stocks", "crypto"], "default": "all"},
            },
            "examples": [
                {},
                {"category": "stocks"},
                {"category": "crypto"},
            ],
        },
    },
    # ── Banking tools ────────────────────────────────────────────────────────
    {
        "name": "get_accounts",
        "description": "List all Revolut Open Banking accounts (requires REVOLUT_CLIENT_ID setup)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    {
        "name": "get_account_balance",
        "description": "Current balance for a specific Revolut account",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID from get_accounts"},
            },
            "required": ["account_id"],
            "examples": [
                {"account_id": "acc_123abc"},
            ],
        },
    },
    {
        "name": "get_pockets",
        "description": "List all Revolut vaults/pockets (requires REVOLUT_DEVICE_ID + REVOLUT_PHONE_TOKEN)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    {
        "name": "get_pocket_detail",
        "description": "Detail for a single Revolut vault or savings pocket",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pocket_id": {"type": "string", "description": "Pocket ID from get_pockets"},
            },
            "required": ["pocket_id"],
            "examples": [
                {"pocket_id": "pkt_456def"},
            ],
        },
    },
    {
        "name": "get_transactions",
        "description": "Paginated transaction list for a Revolut account with optional date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID from get_accounts"},
                "from_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["account_id"],
            "examples": [
                {"account_id": "acc_123abc", "from_date": "2024-01-01", "to_date": "2024-01-31"},
                {"account_id": "acc_123abc", "limit": 10},
                {"account_id": "acc_123abc"},
            ],
        },
    },
    {
        "name": "get_transaction_detail",
        "description": "Full detail for a single Revolut transaction including merchant and category",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID from get_accounts"},
                "transaction_id": {"type": "string", "description": "Transaction ID from get_transactions"},
            },
            "required": ["account_id", "transaction_id"],
            "examples": [
                {"account_id": "acc_123abc", "transaction_id": "txn_789ghi"},
            ],
        },
    },
    {
        "name": "get_spending_by_category",
        "description": "Monthly spending breakdown grouped by merchant category",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID from get_accounts"},
                "month": {"type": "string", "description": "YYYY-MM format; omit for current month"},
            },
            "required": ["account_id"],
            "examples": [
                {"account_id": "acc_123abc", "month": "2024-01"},
                {"account_id": "acc_123abc"},
            ],
        },
    },
    {
        "name": "send_domestic_payment",
        "description": "Send a domestic bank transfer from Revolut (requires PIS consent)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Payment amount"},
                "currency": {"type": "string", "description": "ISO 4217 currency code"},
                "creditor_name": {"type": "string"},
                "creditor_account": {"type": "string", "description": "IBAN or domestic account number"},
                "reference": {"type": "string", "description": "Payment reference shown on recipient statement"},
            },
            "required": ["amount", "currency", "creditor_name", "creditor_account"],
            "examples": [
                {"amount": 250.00, "currency": "GBP", "creditor_name": "Jane Smith", "creditor_account": "GB29NWBK60161331926819", "reference": "Rent March"},
                {"amount": 50.00, "currency": "EUR", "creditor_name": "John Doe", "creditor_account": "DE89370400440532013000", "reference": "Dinner split"},
            ],
        },
    },
    {
        "name": "send_international_payment",
        "description": "Send an international SWIFT or SEPA payment from Revolut",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "currency": {"type": "string", "description": "ISO 4217 currency code"},
                "creditor_name": {"type": "string"},
                "creditor_account": {"type": "string", "description": "IBAN"},
                "creditor_bic": {"type": "string", "description": "BIC/SWIFT code of the recipient bank"},
            },
            "required": ["amount", "currency", "creditor_name", "creditor_account", "creditor_bic"],
            "examples": [
                {"amount": 1000.00, "currency": "EUR", "creditor_name": "Acme GmbH", "creditor_account": "DE89370400440532013000", "creditor_bic": "COBADEFFXXX"},
                {"amount": 500.00, "currency": "USD", "creditor_name": "Supplier Inc", "creditor_account": "US12345678901234567890", "creditor_bic": "CHASUS33"},
            ],
        },
    },
    {
        "name": "create_standing_order",
        "description": "Create a recurring standing order on Revolut",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "currency": {"type": "string"},
                "frequency": {"type": "string", "description": "weekly | monthly | quarterly"},
                "creditor_name": {"type": "string"},
                "creditor_account": {"type": "string", "description": "IBAN or domestic account number"},
            },
            "required": ["amount", "currency", "frequency", "creditor_name", "creditor_account"],
            "examples": [
                {"amount": 800.00, "currency": "GBP", "frequency": "monthly", "creditor_name": "Landlord Ltd", "creditor_account": "GB29NWBK60161331926819"},
                {"amount": 200.00, "currency": "EUR", "frequency": "weekly", "creditor_name": "Savings Account", "creditor_account": "DE89370400440532013000"},
            ],
        },
    },
    {
        "name": "get_payment_status",
        "description": "Check the current status of a submitted payment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "string", "description": "Payment ID returned by send_domestic_payment or send_international_payment"},
                "payment_type": {"type": "string", "default": "domestic", "description": "domestic | international"},
            },
            "required": ["payment_id"],
            "examples": [
                {"payment_id": "pay_abc123", "payment_type": "domestic"},
                {"payment_id": "pay_xyz789", "payment_type": "international"},
            ],
        },
    },
    {
        "name": "get_scheduled_payments",
        "description": "List all active scheduled payments and standing orders for an account",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
            },
            "required": ["account_id"],
            "examples": [
                {"account_id": "acc_123abc"},
            ],
        },
    },
    {
        "name": "get_account_statement",
        "description": "Download a Revolut account statement for a given date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "from_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            },
            "required": ["account_id"],
            "examples": [
                {"account_id": "acc_123abc", "from_date": "2024-01-01", "to_date": "2024-03-31"},
                {"account_id": "acc_123abc", "from_date": "2024-12-01", "to_date": "2024-12-31"},
            ],
        },
    },
    {
        "name": "get_multi_currency_balances",
        "description": "All Revolut multi-currency wallet balances in a single call",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    # ── FX tools ─────────────────────────────────────────────────────────────
    {
        "name": "get_exchange_rate",
        "description": "FX rates from ECB via Frankfurter — spot or historical",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base": {"type": "string", "default": "GBP", "description": "ISO 4217 base currency"},
                "targets": {"type": "string", "default": "EUR,USD", "description": "Comma-separated target currencies"},
                "date": {"type": "string", "description": "ISO date for historical rate; omit for latest"},
            },
            "examples": [
                {"base": "GBP", "targets": "EUR,USD,JPY"},
                {"base": "USD", "targets": "EUR,GBP,CHF", "date": "2024-01-15"},
                {"base": "EUR", "targets": "USD"},
            ],
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount between any two currencies using ECB rates",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string", "description": "ISO 4217 source currency"},
                "to_currency": {"type": "string", "description": "ISO 4217 target currency"},
            },
            "required": ["amount", "from_currency", "to_currency"],
            "examples": [
                {"amount": 1000, "from_currency": "GBP", "to_currency": "EUR"},
                {"amount": 500, "from_currency": "USD", "to_currency": "JPY"},
                {"amount": 250, "from_currency": "EUR", "to_currency": "CHF"},
            ],
        },
    },
    {
        "name": "get_revolut_fx_fees",
        "description": "Estimate Revolut FX conversion fees and weekend surcharge by plan",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "string", "enum": ["standard", "premium", "metal"], "default": "standard"},
                "amount": {"type": "number", "default": 1000},
                "from_currency": {"type": "string", "default": "GBP"},
                "to_currency": {"type": "string", "default": "EUR"},
            },
            "examples": [
                {"plan": "standard", "amount": 2000, "from_currency": "GBP", "to_currency": "EUR"},
                {"plan": "premium", "amount": 5000, "from_currency": "USD", "to_currency": "GBP"},
                {"plan": "metal", "amount": 10000, "from_currency": "EUR", "to_currency": "USD"},
            ],
        },
    },
    # ── Revolut X crypto trading tools ───────────────────────────────────────
    {
        "name": "get_crypto_tickers",
        "description": "All available trading pairs on Revolut X exchange (requires REVOLUT_X_API_KEY)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    {
        "name": "get_crypto_orders",
        "description": "List all active/open orders on your Revolut X account",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "examples": [{}],
        },
    },
    {
        "name": "place_crypto_order",
        "description": "Place a market or limit order on Revolut X (requires REVOLUT_X_API_KEY + REVOLUT_X_PRIVATE_KEY)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading pair e.g. BTC-USD"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "order_type": {"type": "string", "enum": ["market", "limit"]},
                "quantity": {"type": "number", "description": "Amount of base asset"},
                "price": {"type": "number", "description": "Limit price — required for limit orders, omit for market"},
            },
            "required": ["symbol", "side", "order_type", "quantity"],
            "examples": [
                {"symbol": "BTC-USD", "side": "buy", "order_type": "limit", "quantity": 0.01, "price": 60000},
                {"symbol": "ETH-USD", "side": "buy", "order_type": "market", "quantity": 0.5},
                {"symbol": "SOL-USD", "side": "sell", "order_type": "limit", "quantity": 10, "price": 155},
            ],
        },
    },
    {
        "name": "get_crypto_trades",
        "description": "Trade history on your Revolut X account, optionally filtered by symbol",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Filter to a specific trading pair e.g. BTC-USD"},
                "limit": {"type": "integer", "default": 50},
            },
            "examples": [
                {},
                {"symbol": "BTC-USD", "limit": 25},
                {"symbol": "ETH-USD"},
            ],
        },
    },
    {
        "name": "get_crypto_ohlc",
        "description": "OHLCV candlestick data from Revolut X for charting and analysis",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading pair e.g. BTC-USD"},
                "interval": {"type": "string", "default": "1h", "description": "Candle interval: 1m 5m 15m 1h 4h 1d"},
                "limit": {"type": "integer", "default": 100, "description": "Number of candles (max 500)"},
            },
            "required": ["symbol"],
            "examples": [
                {"symbol": "BTC-USD", "interval": "1h", "limit": 48},
                {"symbol": "ETH-USD", "interval": "4h", "limit": 30},
                {"symbol": "SOL-USD", "interval": "1d", "limit": 90},
            ],
        },
    },
    # ── Alert & webhook tools ────────────────────────────────────────────────
    {
        "name": "create_alert",
        "description": "Create a price alert — triggers when ticker crosses target in specified direction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alert_type": {"type": "string", "description": "price | insider | volume"},
                "target": {"type": "number", "description": "Threshold value (price, volume, etc.)"},
                "direction": {"type": "string", "enum": ["above", "below"], "default": "above"},
                "ticker": {"type": "string", "description": "Stock or crypto symbol"},
                "user_id": {"type": "string", "default": "default"},
            },
            "required": ["alert_type", "target"],
            "examples": [
                {"alert_type": "price", "ticker": "NVDA", "target": 1000, "direction": "above"},
                {"alert_type": "price", "ticker": "BTC", "target": 50000, "direction": "below"},
                {"alert_type": "insider", "ticker": "AAPL", "target": 1, "direction": "above"},
            ],
        },
    },
    {
        "name": "list_alerts",
        "description": "List all active price/insider alerts for a user",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "default": "default"},
            },
            "examples": [
                {},
                {"user_id": "user_42"},
            ],
        },
    },
    {
        "name": "delete_alert",
        "description": "Delete a price or insider alert by its ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alert_id": {"type": "string", "description": "Alert ID from list_alerts"},
            },
            "required": ["alert_id"],
            "examples": [
                {"alert_id": "alert_abc123"},
            ],
        },
    },
    {
        "name": "register_webhook",
        "description": "Register a webhook URL to receive real-time event notifications",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTPS endpoint that accepts POST JSON payloads"},
                "events": {"type": "array", "items": {"type": "string"}, "description": "Event types to subscribe to"},
            },
            "required": ["url"],
            "examples": [
                {"url": "https://myapp.com/hooks/mcp", "events": ["price_alert", "insider_trade"]},
                {"url": "https://myapp.com/hooks/mcp", "events": ["insider_cluster"]},
            ],
        },
    },
]

# ── Apply TOOLS_MODE filter ────────────────────────────────────────────────
# Filter both dicts/lists so that HTTP (FastAPI) and stdio (FastMCP) transports
# expose only the tools appropriate for this deployment.
if TOOLS_MODE == "market":
    TOOL_HANDLERS = {k: v for k, v in TOOL_HANDLERS.items() if k in MARKET_TOOL_NAMES}
    MCP_TOOLS_SCHEMA = [t for t in MCP_TOOLS_SCHEMA if t["name"] in MARKET_TOOL_NAMES]
elif TOOLS_MODE == "revolut":
    TOOL_HANDLERS = {k: v for k, v in TOOL_HANDLERS.items() if k in REVOLUT_TOOL_NAMES}
    MCP_TOOLS_SCHEMA = [t for t in MCP_TOOLS_SCHEMA if t["name"] in REVOLUT_TOOL_NAMES]
# TOOLS_MODE=all (default): no filtering, all 38 tools exposed

# Register filtered tools with FastMCP for stdio transport
for _name, _func in TOOL_HANDLERS.items():
    mcp.tool()(_func)


# ══════════════════════════════════════════════════════════════════════════════
#  PROMPTS  (17)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.prompt()
def revolut_insider_scan(ticker: str = "NVDA") -> str:
    return (
        f"Check the latest insider filings for {ticker.upper()} using get_insider_filings(ticker='{ticker}') "
        f"then check its price with revolut_price_check(ticker='{ticker}'). "
        f"Summarise: total filings, total value, any CEO/CFO trades, and whether it's on Revolut."
    )


@mcp.prompt()
def weekly_insider_report() -> str:
    return (
        "Call get_insider_weekly_summary(). "
        "Format as a structured report: top 3 tickers by total value, CEO/CFO count, "
        "Revolut tradable count, and a 1-line actionable recommendation for each."
    )


@mcp.prompt()
def market_watchlist_snapshot() -> str:
    return (
        "Call price_snapshot(). Interpret the market mood. "
        "Highlight top gainer and loser. Suggest one Revolut-tradable action based on the data."
    )


@mcp.prompt()
def account_overview() -> str:
    return "Call get_accounts() and get_multi_currency_balances(). Summarise all balances and net worth."


@mcp.prompt()
def revolut_portfolio_health() -> str:
    return (
        "Call get_accounts(), get_pockets(), and get_spending_by_category() for the current month. "
        "Give a financial health score 1–10, top spending categories, and 3 actionable tips."
    )


@mcp.prompt()
def revolut_fx_opportunity() -> str:
    return (
        "Call get_exchange_rate(base='GBP', targets='EUR,USD') and "
        "get_revolut_fx_fees(plan='premium', amount=5000). "
        "Recommend whether today or Monday is better for a 5000 GBP→EUR conversion."
    )


@mcp.prompt()
def revolut_crypto_alert_setup() -> str:
    return (
        "Call get_crypto_price('BTC'). "
        "Then create two alerts: create_alert('price', target=BTC_price*1.10, direction='above', ticker='BTC') "
        "and create_alert('price', target=BTC_price*0.90, direction='below', ticker='BTC'). "
        "Confirm both alert IDs."
    )


@mcp.prompt()
def revolut_upcoming_payments() -> str:
    return (
        "Call get_scheduled_payments() and get_account_balance(). "
        "List upcoming payments sorted by date. "
        "Warn if any payment would overdraw the current balance."
    )


@mcp.prompt()
def insider_cluster_alert() -> str:
    return (
        "Call get_insider_clusters(days=7). "
        "Filter for clusters with total_value >= 1,000,000. "
        "For each match, check revolut_price_check(ticker). "
        "Output as a trading watchlist with 🚨 emoji for CEO/CFO involvement."
    )


@mcp.prompt()
def daily_market_briefing() -> str:
    return (
        "60-second market briefing: "
        "1) price_snapshot() — mood + top mover "
        "2) crypto_top_movers(limit=3) — hottest crypto "
        "3) get_insider_clusters(days=1) — any fresh clusters "
        "Format as a TL;DR paragraph under 100 words."
    )


@mcp.prompt()
def revolut_savings_goal_tracker() -> str:
    return (
        "Call get_pockets(). For each vault with a goal set, "
        "calculate weekly savings needed to hit the goal by the target date. "
        "Suggest which ETF on Revolut could grow the savings faster."
    )


@mcp.prompt()
def revolut_trading_signal() -> str:
    return (
        "Call cross_reference_insider_revolut(limit=50). "
        "Filter for CEO/CFO trades. "
        "For each, call revolut_price_check(ticker). "
        "Output a ranked signal list: ticker, insider role, trade value, current price, Revolut ✅/❌."
    )


@mcp.prompt()
def seo_finance_content_ideas() -> str:
    return (
        "Call get_insider_clusters() and crypto_top_movers(). "
        "Generate 10 SEO blog post titles using the data. "
        "Include search intent (informational vs transactional) and a target keyword for each."
    )


@mcp.prompt()
def competitor_insider_analysis(ticker: str = "NVDA", competitor: str = "AMD") -> str:
    return (
        f"Compare insider trades: get_insider_filings('{ticker}') vs get_insider_filings('{competitor}'). "
        f"Also pull prices: revolut_price_check('{ticker}') and revolut_price_check('{competitor}'). "
        f"Write a 200-word competitor analysis blog intro."
    )


@mcp.prompt()
def daily_trading_thread() -> str:
    return (
        "Create a 5-tweet Twitter/X thread from today's market data. "
        "Use price_snapshot() for market mood, crypto_top_movers(limit=2) for crypto, "
        "and get_insider_clusters() for a 🚨 insider alert tweet. "
        "Each tweet max 280 chars. Include tickers with $ prefix."
    )


@mcp.prompt()
def crypto_seo_topic_discovery() -> str:
    return (
        "Call crypto_top_movers(limit=20). "
        "For each top gainer check get_crypto_price(symbol). "
        "Generate SEO H1 titles, meta descriptions, and FAQ questions for the top 5 movers."
    )


@mcp.prompt()
def seo_weekly_finance_newsletter() -> str:
    return (
        "Generate a complete weekly finance newsletter: "
        "Subject line, 3-sentence intro using price_snapshot() data, "
        "top insider cluster story from get_insider_clusters(), "
        "crypto highlight from crypto_top_movers(limit=3), "
        "and a CTA to trade on Revolut. Target 300 words."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RESOURCES  (5)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.resource("revolut://tradable/symbols")
def revolut_tradable_symbols() -> str:
    return json.dumps({
        "stocks": sorted(revolut.REVOLUT_STOCKS.keys()),
        "crypto": sorted(revolut.REVOLUT_CRYPTO),
        "total": len(revolut.REVOLUT_STOCKS) + len(revolut.REVOLUT_CRYPTO),
    })


@mcp.resource("revolut://plan-limits")
def revolut_plan_limits() -> str:
    return json.dumps({
        "standard": {"monthly_fx_limit_gbp": 1000, "stock_fee_pct": 1.49, "crypto_fee_pct": 1.49},
        "premium": {"monthly_fx_limit_gbp": 10000, "stock_fee_pct": 0.49, "crypto_fee_pct": 1.49},
        "metal": {"monthly_fx_limit_gbp": "unlimited", "stock_fee_pct": 0.0, "crypto_fee_pct": 1.49},
    })


@mcp.resource("revolut://tradable/etfs-by-sector")
def revolut_etf_sectors() -> str:
    return json.dumps(revolut.get_etf_sectors())


@mcp.resource("seo://financial-keywords")
def seo_financial_keywords() -> str:
    return json.dumps([
        "best stocks to buy on Revolut",
        "crypto price prediction 2025",
        "Revolut stock list",
        "how to buy ETF on Revolut",
        "insider trading alerts",
        "Revolut vs eToro fees",
        "top crypto gainers today",
        "SEC Form 4 filings alert",
    ])


@mcp.resource("seo://blog-post-template")
def seo_blog_post_template() -> str:
    return json.dumps({
        "title_formula": "[TICKER] Insider Buying Alert – [DATE]",
        "meta_description_formula": "CEO/CFO insiders bought [VALUE] of [TICKER] stock. Is it available on Revolut?",
        "structure": [
            "H1: What happened (insider event)",
            "H2: Why it matters (signal strength)",
            "H2: Is [TICKER] on Revolut?",
            "H2: How to trade it (step-by-step)",
            "FAQ: 3 questions",
        ],
        "word_count_target": 800,
        "cta": "Start trading on Revolut today",
    })
