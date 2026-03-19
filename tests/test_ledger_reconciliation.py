from typing import Any, cast

from core.ledger_reconciliation import DeepLedgerReconciliationService


class FakeConfigManager:
    def __init__(self, values=None):
        self.values = values or {}

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class StubReconciliationService(DeepLedgerReconciliationService):
    def __init__(self):
        fake_config = FakeConfigManager({"ledger_reconciliation_tolerance": 1.0})
        super().__init__(config_manager=cast(Any, fake_config))
        self.persisted = None

    def _compute_expected_ledger(self, lookback_hours: int):
        return {
            "trade_count": 3,
            "buy_notional": 1000.0,
            "sell_notional": 1200.0,
            "net_cashflow": 200.0,
        }

    def _fetch_broker_snapshot(self, lookback_hours: int):
        return {
            "source": "TEST",
            "window_hours": lookback_hours,
            "net_cashflow": 199.25,
            "equity": 10000.0,
        }

    def _persist_reconciliation_run(self, result):
        self.persisted = result


class StubDriftService(StubReconciliationService):
    def _fetch_broker_snapshot(self, lookback_hours: int):
        return {
            "source": "TEST",
            "window_hours": lookback_hours,
            "net_cashflow": 180.0,
            "equity": 10000.0,
        }


def test_reconciliation_passes_within_tolerance():
    service = StubReconciliationService()
    result = service.run_reconciliation(lookback_hours=24)

    assert result["status"] == "PASS"
    assert result["absolute_delta"] == 0.75
    assert service.persisted is not None


def test_reconciliation_flags_drift_outside_tolerance():
    service = StubDriftService()
    result = service.run_reconciliation(lookback_hours=24)

    assert result["status"] == "DRIFT"
    assert result["absolute_delta"] == 20.0
    assert service.persisted is not None
