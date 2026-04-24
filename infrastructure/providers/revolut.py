"""
Revolut tradable asset registry.
Stocks, ETFs, crypto — all assets confirmed available on Revolut as of 2024.
"""

REVOLUT_STOCKS: dict = {
    # ── Tech Giants ──────────────────────────────────────────────────────
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet A", "GOOG": "Alphabet C",
    "META": "Meta", "AMZN": "Amazon", "NVDA": "NVIDIA", "TSLA": "Tesla", "NFLX": "Netflix",
    # ── Enterprise Software ──────────────────────────────────────────────
    "ADBE": "Adobe", "CRM": "Salesforce", "ORCL": "Oracle", "IBM": "IBM", "INTC": "Intel",
    "AMD": "AMD", "QCOM": "Qualcomm", "TXN": "Texas Instruments", "AVGO": "Broadcom",
    "MU": "Micron", "AMAT": "Applied Materials", "NOW": "ServiceNow", "INTU": "Intuit",
    "SNOW": "Snowflake", "UBER": "Uber", "SHOP": "Shopify", "SQ": "Block",
    "PYPL": "PayPal", "PLTR": "Palantir", "COIN": "Coinbase", "MSTR": "MicroStrategy",
    # ── Finance ──────────────────────────────────────────────────────────
    "JPM": "JPMorgan Chase", "BAC": "Bank of America", "WFC": "Wells Fargo",
    "GS": "Goldman Sachs", "MS": "Morgan Stanley", "V": "Visa", "MA": "Mastercard",
    "AXP": "American Express", "BRKB": "Berkshire Hathaway B", "BLK": "BlackRock",
    "SCHW": "Charles Schwab",
    # ── Healthcare ───────────────────────────────────────────────────────
    "JNJ": "Johnson & Johnson", "PFE": "Pfizer", "MRNA": "Moderna", "ABBV": "AbbVie",
    "LLY": "Eli Lilly", "MRK": "Merck", "AMGN": "Amgen", "GILD": "Gilead Sciences",
    "UNH": "UnitedHealth", "CVS": "CVS Health",
    # ── Energy ───────────────────────────────────────────────────────────
    "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips", "OXY": "Occidental",
    # ── Defence & Aerospace ──────────────────────────────────────────────
    "LMT": "Lockheed Martin", "RTX": "RTX Corp", "BA": "Boeing",
    "GD": "General Dynamics", "NOC": "Northrop Grumman",
    "LHX": "L3Harris Technologies", "HII": "Huntington Ingalls",
    # ── Consumer ─────────────────────────────────────────────────────────
    "KO": "Coca-Cola", "PEP": "PepsiCo", "MCD": "McDonald's", "SBUX": "Starbucks",
    "NKE": "Nike", "DIS": "Disney", "WMT": "Walmart", "COST": "Costco", "HD": "Home Depot",
    # ── Telecom ──────────────────────────────────────────────────────────
    "T": "AT&T", "VZ": "Verizon", "CMCSA": "Comcast",
    # ── Semiconductors / Intl ────────────────────────────────────────────
    "TSM": "TSMC ADR", "ASML": "ASML ADR", "LRCX": "Lam Research",
    # ── ETFs ─────────────────────────────────────────────────────────────
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "IWM": "Russell 2000 ETF",
    "GLD": "Gold ETF", "SLV": "Silver ETF", "TLT": "20yr Treasury ETF",
    "XLK": "Technology SPDR", "XLE": "Energy SPDR", "XLF": "Financial SPDR",
    "XLV": "Health Care SPDR", "XLI": "Industrial SPDR",
    "ITA": "Aerospace & Defense ETF",
    "ARKK": "ARK Innovation ETF", "VOO": "Vanguard S&P 500", "SOXX": "Semiconductor ETF",
    # ── SaaS / Cloud ─────────────────────────────────────────────────────
    "DDOG": "Datadog", "NET": "Cloudflare", "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks",
    "ZS": "Zscaler", "FTNT": "Fortinet", "SNAP": "Snap", "PINS": "Pinterest",
    "ZM": "Zoom", "RBLX": "Roblox", "SPOT": "Spotify", "LYFT": "Lyft",
    "HUBS": "HubSpot", "TEAM": "Atlassian", "TWLO": "Twilio", "DOCU": "DocuSign",
    "OKTA": "Okta", "PATH": "UiPath", "U": "Unity Software", "AI": "C3.ai",
}

REVOLUT_CRYPTO: set = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK",
    "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "THETA", "FIL", "AAVE",
    "COMP", "SNX", "MKR", "SUSHI", "YFI", "BAT", "ZRX", "ENJ", "MANA", "SAND",
    "AXS", "CHZ", "GALA", "IMX", "APE", "NEAR", "FTM", "HBAR", "ICP", "ETC",
    "TRX", "EOS", "NEO", "DASH", "ZEC", "XMR", "QTUM", "ONT", "ZIL", "ICX",
    "BNB", "OP", "ARB", "SUI", "SEI", "TIA", "PYTH", "JUP",
}

KNOWN_CRYPTO: set = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX",
    "MATIC", "LINK", "UNI", "ATOM", "LTC", "BCH", "BNB", "OP", "ARB",
    "NEAR", "FTM", "HBAR", "SAND", "MANA", "AXS", "IMX", "APE",
    "SUI", "SEI", "TIA", "JUP", "PYTH",
}


async def is_tradable(symbol: str) -> bool:
    sym = symbol.upper()
    return sym in REVOLUT_STOCKS or sym in REVOLUT_CRYPTO


def all_assets() -> list:
    stocks = [{"ticker": k, "name": v, "type": "stock"} for k, v in sorted(REVOLUT_STOCKS.items())]
    crypto = [{"ticker": c, "type": "crypto"} for c in sorted(REVOLUT_CRYPTO)]
    return stocks + crypto


def search_assets(query: str) -> list:
    q = query.upper().strip()
    results = []
    for ticker, name in REVOLUT_STOCKS.items():
        if q in ticker or q in name.upper():
            results.append({"ticker": ticker, "name": name, "type": "stock"})
    for crypto in REVOLUT_CRYPTO:
        if q in crypto:
            results.append({"ticker": crypto, "type": "crypto"})
    return results


def get_etf_sectors() -> dict:
    return {
        "Technology": ["XLK", "SOXX", "QQQ"],
        "Energy": ["XLE"],
        "Finance": ["XLF"],
        "Healthcare": ["XLV"],
        "Industrials": ["XLI"],
        "Aerospace & Defence": ["ITA"],
        "Gold / Metals": ["GLD", "SLV"],
        "Broad Market": ["SPY", "VOO", "IWM"],
        "Bonds": ["TLT"],
        "Innovation": ["ARKK"],
    }
