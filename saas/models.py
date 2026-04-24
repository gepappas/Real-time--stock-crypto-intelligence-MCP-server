import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    api_key = Column(String, unique=True, index=True, default=lambda: uuid.uuid4().hex)
    plan = Column(String, default="free", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PGUUID, ForeignKey("users.id", ondelete="CASCADE"))
    endpoint = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    price_monthly = Column(Float, default=0)
    max_requests = Column(Integer, default=100)
    max_concurrent = Column(Integer, default=5)
