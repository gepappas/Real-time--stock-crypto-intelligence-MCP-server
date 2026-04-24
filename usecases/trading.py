from datetime import datetime
from domain.models import TradingContext, Availability
from infrastructure.providers import binance, yahoo, revolut


async def get_trading_context(symbol: str) -> TradingContext:
    """Build a full TradingContext for any ticker (stock or crypto)."""
    sym = symbol.upper()
    ctx = TradingContext(symbol=sym)

    # Try crypto price first (Binance)
    if sym in revolut.KNOWN_CRYPTO or sym in revolut.REVOLUT_CRYPTO:
        crypto_price = await binance.get_crypto_price(sym)
        if crypto_price:
            ctx.prices.append(crypto_price)
            ctx.availability.append(Availability(sym, "binance", True))

    # Try stock/ETF price (Yahoo Finance)
    stock_price = await yahoo.get_stock_price(sym)
    if stock_price and stock_price.value > 0:
        ctx.prices.append(stock_price)
        ctx.availability.append(Availability(sym, "yahoo", True))

    # Revolut availability
    rev_avail = await revolut.is_tradable(sym)
    ctx.availability.append(Availability(sym, "revolut", rev_avail))
    if rev_avail:
        ctx.availability.append(Availability(sym, "revolut_x", True))

    ctx.last_updated = datetime.utcnow().isoformat() + "Z"
    return ctx
