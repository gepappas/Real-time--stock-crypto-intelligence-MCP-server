from .models import TradingContext


class TradingDecisionEngine:

    @staticmethod
    def best_platform(context: TradingContext) -> str:
        for a in context.availability:
            if a.available:
                return a.platform
        return "unavailable"

    @staticmethod
    def is_tradable_on(context: TradingContext, platform: str) -> bool:
        return any(a.platform == platform and a.available for a in context.availability)

    @staticmethod
    def has_insider_activity(context: TradingContext) -> bool:
        return len(context.insider_trades) > 0

    @staticmethod
    def ceo_insider_signal(context: TradingContext) -> bool:
        return any(t.is_ceo_cfo for t in context.insider_trades)

    @staticmethod
    def market_mood(context: TradingContext) -> str:
        if not context.prices:
            return "neutral"
        avg_chg = sum(p.change_pct or 0 for p in context.prices) / len(context.prices)
        return "🟢 Risk-On" if avg_chg > 0 else "🔴 Risk-Off"

    @staticmethod
    def top_gainer(context: TradingContext) -> dict:
        if not context.prices:
            return {}
        best = max(context.prices, key=lambda p: p.change_pct or 0)
        return {"symbol": best.symbol, "change_pct": best.change_pct}

    @staticmethod
    def top_loser(context: TradingContext) -> dict:
        if not context.prices:
            return {}
        worst = min(context.prices, key=lambda p: p.change_pct or 0)
        return {"symbol": worst.symbol, "change_pct": worst.change_pct}
