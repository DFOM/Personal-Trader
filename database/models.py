import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        database_url = "sqlite:///local_trading_bot.db"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


DATABASE_URL = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TradeRecord(Base):
    __tablename__ = "trade_records"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    asset_class = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ai_reasoning = Column(Text, nullable=True)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=False)
    description = Column(String(500), nullable=True)


class TradeProposal(Base):
    __tablename__ = "trade_proposals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    action = Column(String(10), nullable=False)
    confidence = Column(Integer, nullable=False)
    suggested_position_size = Column(Float, nullable=False, default=0.0)
    reasoning = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class LedgerReconciliationRun(Base):
    __tablename__ = "ledger_reconciliation_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    status = Column(String(20), nullable=False, index=True)
    source = Column(String(30), nullable=False, default="LOCAL")
    expected_net_cashflow = Column(Float, nullable=False, default=0.0)
    broker_net_cashflow = Column(Float, nullable=False, default=0.0)
    absolute_delta = Column(Float, nullable=False, default=0.0)
    tolerance_threshold = Column(Float, nullable=False, default=1.0)
    summary = Column(String(300), nullable=False)
    details_json = Column(Text, nullable=False)
