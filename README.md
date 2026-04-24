markdown
# revolut-pulse-mcp ⚡💳
**MCP Server + Programmatic SEO Engine for Revolut Trading, Insider Data & Financial Intelligence**

> 📊 Real‑time stocks, crypto & insider trading from Yahoo, Binance, SEC EDGAR  
> 💳 Full Revolut banking integration (Open Banking, Revolut X, savings vaults)  
> 🕵️ Insider cluster detection, CEO/CFO trade alerts, weekly recaps  
> 🧠 17 built‑in prompts & 5 resources for AI‑powered content creation  
> 💰 **450+ SEO‑optimised pages** (buying guides, fee comparisons, availability checks)  

**No API keys required for market data & insider info.**  
Banking tools degrade gracefully when credentials aren't set.

## 🚀 Quick Start

```bash
git clone https://github.com/gepappas/Real-time--stock-crypto-intelligence-MCP-server.git
cd Real-time--stock-crypto-intelligence-MCP-server
pip install -r requirements.txt
python main.py
```

For Claude Desktop integration

Add to claude_desktop_config.json:

```json
{
  "mcpServers": {
    "revolut-pulse-mcp": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx,beautifulsoup4,pynacl,fastapi,uvicorn,redis,asyncpg,sqlalchemy", "python", "main.py"],
      "cwd": "/path/to/Real-time--stock-crypto-intelligence-MCP-server"
    }
  }
}
```

✨ What's Inside

38 MCP Tools

All tools are accessible via MCP JSON‑RPC and SSE transport.

· Market Data (12 tools): get_price, get_prices_bulk, get_crypto_price, price_snapshot, revolut_price_check, crypto_top_movers, get_insider_filings, get_insider_clusters, get_insider_weekly_summary, get_revolut_tradable_list, search_revolut_tradable, cross_reference_insider_revolut
· Revolut Banking (23 tools): get_accounts, get_account_balance, get_pockets, get_pocket_detail, get_transactions, get_transaction_detail, get_spending_by_category, send_domestic_payment, send_international_payment, create_standing_order, get_payment_status, get_scheduled_payments, get_exchange_rate, convert_currency, get_revolut_fx_fees, get_multi_currency_balances, get_crypto_tickers, get_crypto_orders, place_crypto_order, get_crypto_trades, get_crypto_ohlc, create_alert, list_alerts, delete_alert, register_webhook, get_account_statement

17 Built‑in Prompts

Pre‑written prompt templates for AI assistants:

· Trading: revolut_insider_scan, insider_cluster_alert, revolut_trading_signal, daily_market_briefing
· Banking: account_overview, revolut_portfolio_health, revolut_fx_opportunity, revolut_upcoming_payments, revolut_savings_goal_tracker
· Crypto: revolut_crypto_alert_setup
· SEO/Content: weekly_insider_report, seo_finance_content_ideas, competitor_insider_analysis, daily_trading_thread, crypto_seo_topic_discovery, seo_weekly_finance_newsletter

5 Static Resources

Direct data access via MCP resource URIs:

· revolut://tradable/symbols – All Revolut‑traded stocks & crypto
· revolut://plan-limits – Revolut plan fair‑usage limits
· revolut://tradable/etfs-by-sector – Sector‑grouped ETFs
· seo://financial-keywords – High‑volume financial keywords
· seo://blog-post-template – SEO‑optimised blog post template

Programmatic SEO Engine (v2)

When running in HTTP mode (MCP_TRANSPORT=http), the server generates a full site structure:

Page Type URL Pattern Description
Hub Pages /revolut-stocks, /revolut-crypto Complete lists of tradable assets
Detail Pages /ticker/{symbol} Price, availability, insider trades
Buying Guides /guide/{symbol} Step‑by‑step “How to buy on Revolut”
Comparisons /revolut-vs-etoro/{symbol} Revolut vs eToro fee & feature comparison
Sitemap /sitemap.xml Auto‑generated XML sitemap

Each page includes structured data (Schema.org), Open Graph tags, author & last‑modified timestamps, and internal links for SEO.

🔧 Configuration

Required

· MCPRICE_API_KEYS (in production) – comma‑separated keys for API auth
· PORT – server port (default 8080)

Revolut Open Banking (optional)

```bash
export REVOLUT_ENV=sandbox
export REVOLUT_CLIENT_ID=your_client_id
export REVOLUT_CERT_PATH=./certs/transport.pem
export REVOLUT_KEY_PATH=./certs/private.key
```

Revolut X Crypto Trading (optional)

```bash
export REVOLUT_X_API_KEY=your_rx_key
export REVOLUT_X_PRIVATE_KEY=base64_ed25519_key
```

Requires pynacl for signing.

Unofficial Personal API (Pockets/Vaults)

```bash
export REVOLUT_DEVICE_ID=...
export REVOLUT_PHONE_TOKEN=...
```

Webhook for Alerts

```bash
export MCPRICE_ALERT_WEBHOOK=https://your-webhook.url
```

🌐 Deploy to Production

Railway

· Use the included railway.json
· Set MCP_TRANSPORT=http and the required env vars
· The SEO pages will be live at your Railway URL

Fly.io

```bash
fly launch
fly secrets set MCP_TRANSPORT=http PORT=8080
fly deploy
```

HTTP Mode (generic)

```bash
MCP_TRANSPORT=http python main.py
```

The server exposes both the MCP endpoint (/mcp/sse, /mcp) and the SEO website on the same port.

📊 Data Sources

Source Data Delay API Key
Yahoo Finance Stocks, ETFs ~15 min None
Binance Crypto Real‑time None
SEC EDGAR Insider filings Live None
Frankfurter ECB FX rates Daily None
Revolut Open Banking Accounts, payments Real (sandbox/prod) OAuth2
Revolut X Crypto trading Real‑time Ed25519
Unofficial Personal Pockets/vaults Real Device token

🛡 Security & Reliability

· All market data from public APIs – no keys required
· Banking endpoints return clear setup instructions when unconfigured
· TTL‑based caching (30s stocks, 10s crypto, 5min insider)
· Exponential backoff retry (3 attempts)
· Concurrency limiter (max 5 outbound calls)
· Strict input validation (regex)
· Structured logging

📈 SEO & Monetisation Potential

The built‑in programmatic SEO engine creates a traffic‑ready website with no extra code. Pages target low‑competition, high‑intent keywords:

· "Is [ticker] available on Revolut"
· "How to buy [ticker] on Revolut"
· "Revolut vs eToro for [ticker]"

These can be monetised via affiliate links (eToro, Trading212) or premium API tiers. Add your own backlinks and watch the traffic grow.

📄 License

MIT – free for commercial and personal use.
