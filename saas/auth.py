from fastapi import Header, HTTPException
from sqlalchemy import select
from .database import SessionLocal
from .models import User


async def get_current_user(x_api_key: str = Header(None)) -> User:
    """Validate X-API-Key header and return the matching User."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required (X-API-Key header)")
    async with SessionLocal() as session:
        stmt = select(User).where(User.api_key == x_api_key)
        result = await session.execute(stmt)
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user
