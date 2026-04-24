from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, func
from .database import SessionLocal
from .models import User, UsageLog, BillingPlan


async def track_usage(user_id: str, endpoint: str):
    """Log a single API call and enforce monthly plan limits."""
    async with SessionLocal() as session:
        log = UsageLog(user_id=user_id, endpoint=endpoint)
        session.add(log)
        await session.commit()

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            return
        plan_stmt = select(BillingPlan).where(BillingPlan.name == user.plan)
        plan_result = await session.execute(plan_stmt)
        plan = plan_result.scalars().first()
        if not plan:
            return
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count_stmt = select(func.count()).where(
            UsageLog.user_id == user_id,
            UsageLog.timestamp >= month_start,
        )
        count_result = await session.execute(count_stmt)
        count = count_result.scalar() or 0
        if count > plan.max_requests:
            raise HTTPException(status_code=429, detail=f"Monthly limit of {plan.max_requests} requests reached.")


async def seed_plans():
    """Insert default billing plans if they don't exist."""
    async with SessionLocal() as session:
        defaults = [
            BillingPlan(id=1, name="free", price_monthly=0, max_requests=100, max_concurrent=5),
            BillingPlan(id=2, name="pro", price_monthly=29, max_requests=10_000, max_concurrent=20),
            BillingPlan(id=3, name="enterprise", price_monthly=99, max_requests=100_000, max_concurrent=100),
        ]
        for p in defaults:
            existing = await session.get(BillingPlan, p.id)
            if not existing:
                session.add(p)
        await session.commit()
