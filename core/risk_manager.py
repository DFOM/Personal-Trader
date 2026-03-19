import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.config_manager import ConfigManager

try:
    import alpaca_trade_api as tradeapi  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dependency validated at runtime in deployment env
    tradeapi = None


logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Absolute risk failsafe that overrides AI and pauses trading when breached."""

    HARD_MAX_DAILY_DRAWDOWN = 0.12
    HARD_MAX_POSITION_RISK = 0.05

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        alpaca_client: Optional[Any] = None,
    ) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.alpaca_client = alpaca_client

    def _get_alpaca_client(self) -> Any:
        if self.alpaca_client is not None:
            return self.alpaca_client

        if tradeapi is None:
            raise RuntimeError("alpaca-trade-api is not installed.")

        api_key = os.getenv("ALPACA_API_KEY", "").strip()
        secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()

        if not api_key or not secret_key:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")

        self.alpaca_client = tradeapi.REST(api_key, secret_key, base_url=base_url)  # type: ignore[arg-type]
        return self.alpaca_client

    def _get_start_of_day_equity(self, client: Any, fallback_equity: float) -> float:
        try:
            history = client.get_portfolio_history(period="1D", timeframe="1Min", extended_hours=False)
            equities = getattr(history, "equity", None)
            if equities and len(equities) > 0:
                for value in equities:
                    if value is not None:
                        return float(value)
        except Exception as exc:
            logger.warning("Failed to fetch portfolio history for start-of-day equity: %s", exc)

        return fallback_equity

    def check_daily_drawdown(self) -> Dict[str, Any]:
        """Check intraday drawdown and disable trading if limit is breached."""
        account_client = self._get_alpaca_client()
        account = account_client.get_account()

        current_equity = float(getattr(account, "equity", 0.0))
        fallback_start = float(getattr(account, "last_equity", current_equity))
        start_of_day_equity = self._get_start_of_day_equity(account_client, fallback_equity=fallback_start)

        if start_of_day_equity <= 0:
            return {
                "triggered": False,
                "current_equity": current_equity,
                "start_of_day_equity": start_of_day_equity,
                "loss_pct": 0.0,
                "limit_pct": 0.0,
                "reason": "Invalid start-of-day equity; drawdown check skipped safely.",
            }

        configured_limit = float(self.config_manager.get_setting("daily_loss_limit", 0.03))
        effective_limit = min(max(configured_limit, 0.0), self.HARD_MAX_DAILY_DRAWDOWN)

        loss_pct = max((start_of_day_equity - current_equity) / start_of_day_equity, 0.0)
        triggered = loss_pct >= effective_limit

        result = {
            "triggered": triggered,
            "current_equity": current_equity,
            "start_of_day_equity": start_of_day_equity,
            "loss_pct": loss_pct,
            "limit_pct": effective_limit,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        if triggered:
            self.config_manager.set_setting(
                "is_trading_active",
                False,
                description="Global switch to enable or disable live/paper trade execution.",
            )
            logger.critical(
                "CIRCUIT_BREAKER_TRIGGERED | Daily drawdown %.2f%% exceeded limit %.2f%%. Trading paused.",
                loss_pct * 100,
                effective_limit * 100,
            )

        return result

    def enforce_position_sizing(self, proposed_size: float, confidence_score: int) -> float:
        """Cap proposed trade risk based on DB risk settings + hardcoded failsafe ceiling."""
        safe_proposed_size = max(float(proposed_size), 0.0)
        confidence = max(min(int(confidence_score), 100), 0)

        min_confidence = int(self.config_manager.get_setting("min_ai_confidence_threshold", 80))
        if confidence < min_confidence:
            return 0.0

        configured_max_risk = float(self.config_manager.get_setting("max_risk_per_trade", 0.02))
        configured_max_risk = max(configured_max_risk, 0.0)
        hard_capped_risk = min(configured_max_risk, self.HARD_MAX_POSITION_RISK)

        confidence_multiplier = max(confidence / 100.0, 0.1)
        adjusted_cap = hard_capped_risk * confidence_multiplier

        return min(safe_proposed_size, adjusted_cap)
