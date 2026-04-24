from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Price:
    symbol: str
    value: float
    source: str
    currency: str = "USD"
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    name: Optional[str] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None


@dataclass
class Availability:
    symbol: str
    platform: str
    available: bool


@dataclass
class InsiderTrade:
    ticker: str
    insider_name: str
    title: str
    transaction_type: str
    value: float
    shares: float = 0
    price_per_share: float = 0
    is_ceo_cfo: bool = False
    is_director: bool = False
    is_officer: bool = False
    transaction_date: Optional[str] = None
    filing_date: Optional[str] = None


@dataclass
class Account:
    account_id: str
    currency: str
    balance: float
    account_type: str = "CurrentAccount"


@dataclass
class Pocket:
    pocket_id: str
    name: str
    balance: float
    currency: str = "GBP"
    goal: Optional[float] = None
    goal_progress_pct: Optional[float] = None


@dataclass
class Transaction:
    transaction_id: str
    date: str
    amount: float
    currency: str
    merchant: str = ""
    category: str = "Other"
    type: str = "debit"


@dataclass
class TradingContext:
    symbol: str
    prices: List[Price] = field(default_factory=list)
    availability: List[Availability] = field(default_factory=list)
    insider_trades: List[InsiderTrade] = field(default_factory=list)
    accounts: List[Account] = field(default_factory=list)
    pockets: List[Pocket] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    last_updated: Optional[str] = None
