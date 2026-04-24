# revolut-pulse-mcp v5.2

**Real-time stock & crypto intelligence MCP server** — 38 tools, 17 prompts, 5 resources.

Deployed on [Railway](https://railway.app) | Registered on [Smithery](https://smithery.ai) & [MCPize](https://mcpize.com)

---

## Features

| Category | Tools | Description |
|---|---|---|
| 💰 Prices | 6 | Yahoo Finance stocks, Binance crypto, bulk snapshot |
| 🕵️ Insider | 5 | SEC Form 4 filings, cluster detection, weekly summary |
| 📋 Assets | 2 | Full Revolut tradable list, search |
| 🏦 Banking | 10 | Open Banking AIS/PIS (requires setup) |
| 💱 FX | 3 | ECB rates, convert, Revolut fee calculator |
| 🔄 Revolut X | 5 | Crypto exchange API (requires API key) |
| 🔔 Alerts | 4 | Price alerts, webhooks |
| 📝 Prompts | 17 | Insider scan, market briefing, SEO content, newsletters |
| 📦 Resources | 5 | Asset lists, plan limits, ETF sectors, SEO templates |

---

## Quick Start

### Local (Claude Desktop)

```bash
git clone https://github.com/gepappas98/revolut-pulse-mcp.v2
cd revolut-pulse-mcp.v2
pip install -r requirements.txt
cp .env.example .env
python main.py   # MCP_TRANSPORT defaults to stdio
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "revolut-pulse-mcp": {
      "command": "python",
      "args": ["main.py"],
      "cwd": "/absolute/path/to/revolut-pulse-mcp.v2",
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

### Deploy to Railway

```bash
railway login
railway init
railway up
```

Set these env vars in the Railway dashboard:

```
MCP_TRANSPORT=http
PORT=8080
REDIS_URL=<your-redis-url>          # optional
DATABASE_URL=<your-postgres-url>    # optional
```

### Deploy to Fly.io

```bash
fly launch
fly deploy
```

---

## API Endpoints (HTTP mode)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status check |
| POST | `/mcp` | MCP JSON-RPC 2.0 |
| GET | `/mcp/sse` | SSE probe / heartbeat |
| GET | `/revolut-stocks` | SEO: all stocks |
| GET | `/revolut-crypto` | SEO: all crypto |
| GET | `/ticker/{symbol}` | SEO: live ticker page |
| GET | `/guide/{symbol}` | SEO: buying guide |
| GET | `/revolut-vs-etoro/{symbol}` | SEO: platform comparison |
| GET | `/sitemap.xml` | XML sitemap |

---

## Tool Reference (38 tools)

### Price Tools
- `get_price(ticker)` — Stock/ETF price + Revolut availability
- `get_prices_bulk(tickers)` — Up to 20 tickers at once
- `get_crypto_price(symbol)` — Binance 24hr ticker
- `price_snapshot(tickers?)` — Full market snapshot
- `revolut_price_check(ticker)` — Price + quick verdict
- `crypto_top_movers(limit, min_volume_usd)` — Gainers & losers

### Insider Tools
- `get_insider_filings(ticker?, limit)` — SEC Form 4 data
- `get_insider_clusters(days)` — Multi-insider same-day events
- `get_insider_weekly_summary()` — Weekly structured report
- `search_revolut_tradable(query)` — Search assets by name/ticker
- `cross_reference_insider_revolut(limit)` — Insider × Revolut filter

### Asset Tools
- `get_revolut_tradable_list(category)` — stocks / crypto / all

### Banking Tools (require Open Banking setup)
- `get_accounts()`, `get_account_balance(account_id)`
- `get_pockets()`, `get_pocket_detail(pocket_id)`
- `get_transactions(account_id, ...)`, `get_transaction_detail(...)`
- `get_spending_by_category(account_id, month?)`
- `send_domestic_payment(...)`, `send_international_payment(...)`
- `create_standing_order(...)`, `get_payment_status(payment_id)`
- `get_scheduled_payments(account_id)`, `get_account_statement(...)`
- `get_multi_currency_balances()`

### FX Tools
- `get_exchange_rate(base, targets, date?)` — ECB rates
- `convert_currency(amount, from, to)` — Convert any pair
- `get_revolut_fx_fees(plan, amount, from, to)` — Fee estimator

### Revolut X Tools (require API key)
- `get_crypto_tickers()`, `get_crypto_orders()`
- `place_crypto_order(symbol, side, order_type, quantity, price?)`
- `get_crypto_trades(symbol?, limit)`, `get_crypto_ohlc(symbol, interval, limit)`

### Alert & Webhook Tools
- `create_alert(alert_type, target, direction, ticker?, user_id?)`
- `list_alerts(user_id?)`, `delete_alert(alert_id)`
- `register_webhook(url, events?)`

---

## Architecture

```
revolut-pulse-mcp/
├── domain/              # Models + decision engine
├── infrastructure/      # Cache, rate limiter, providers
│   └── providers/       # binance, yahoo, revolut, sec, frankfurter
├── usecases/            # Orchestration (trading, insider)
├── app/                 # FastAPI + MCP server (38 tools, 17 prompts, 5 resources)
├── seo/                 # SEO page renderer
├── saas/                # Auth, billing, database
└── main.py              # Dual transport entry point
```

---

## Environment Variables

See `.env.example` for full reference.

Core required for production:
- `MCP_TRANSPORT=http`
- `PORT=8080`

Optional but recommended:
- `REDIS_URL` — stampede-safe caching
- `DATABASE_URL` — SaaS billing layer

---

## License

MIT — see [TERMS.md](TERMS.md)
