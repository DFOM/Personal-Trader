import pytest

from core.risk_manager import CircuitBreaker


class FakeConfigManager:
    def __init__(self):
        self.values = {
            "daily_loss_limit": 0.03,
            "max_risk_per_trade": 0.02,
            "min_ai_confidence_threshold": 80,
            "is_trading_active": True,
        }

    def get_setting(self, key, default=None):
        return self.values.get(key, default)

    def set_setting(self, key, value, description=None):
        self.values[key] = value
        return value


class FakeHistory:
    def __init__(self, equity):
        self.equity = equity


class FakeAccount:
    def __init__(self, equity, last_equity):
        self.equity = equity
        self.last_equity = last_equity


class FakeAlpacaClient:
    def __init__(self, current_equity, start_equity):
        self._account = FakeAccount(equity=current_equity, last_equity=start_equity)
        self._history = FakeHistory(equity=[start_equity, current_equity])

    def get_account(self):
        return self._account

    def get_portfolio_history(self, period="1D", timeframe="1Min", extended_hours=False):
        return self._history


def test_check_daily_drawdown_triggers_master_kill_switch():
    config = FakeConfigManager()
    alpaca = FakeAlpacaClient(current_equity=94000, start_equity=100000)
    breaker = CircuitBreaker(config_manager=config, alpaca_client=alpaca)

    result = breaker.check_daily_drawdown()

    assert result["triggered"] is True
    assert result["loss_pct"] == pytest.approx(0.06)
    assert config.get_setting("is_trading_active") is False


def test_check_daily_drawdown_no_trigger_when_within_limit():
    config = FakeConfigManager()
    alpaca = FakeAlpacaClient(current_equity=98500, start_equity=100000)
    breaker = CircuitBreaker(config_manager=config, alpaca_client=alpaca)

    result = breaker.check_daily_drawdown()

    assert result["triggered"] is False
    assert config.get_setting("is_trading_active") is True


def test_enforce_position_sizing_caps_and_blocks_low_confidence():
    config = FakeConfigManager()
    breaker = CircuitBreaker(config_manager=config, alpaca_client=FakeAlpacaClient(100000, 100000))

    blocked_size = breaker.enforce_position_sizing(proposed_size=0.05, confidence_score=70)
    assert blocked_size == 0.0

    capped_size = breaker.enforce_position_sizing(proposed_size=0.05, confidence_score=90)
    assert capped_size == pytest.approx(0.018)
