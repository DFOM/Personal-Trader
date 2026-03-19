import json
import logging
import os

from core.ledger_reconciliation import DeepLedgerReconciliationService
from database.init_db import init_db


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    init_db()
    lookback_hours = int(os.getenv("LEDGER_RECONCILIATION_LOOKBACK_HOURS", "24"))

    service = DeepLedgerReconciliationService()
    result = service.run_reconciliation(lookback_hours=max(lookback_hours, 1))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
