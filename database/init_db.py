from database.models import (
    Base,
    DATABASE_URL,
    LedgerReconciliationRun,
    SystemSettings,
    TradeProposal,
    TradeRecord,
    engine,
)


def init_db() -> None:
    _ = (TradeRecord, SystemSettings, TradeProposal, LedgerReconciliationRun)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print(f"Database initialized successfully using: {DATABASE_URL}")
