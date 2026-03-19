import logging
from typing import Any, Dict

from core.config_manager import ConfigManager
from core.risk_manager import CircuitBreaker
from execution.alpaca_executor import AlpacaExecutor


logger = logging.getLogger(__name__)


class ExecutionService:
    """Centralized execution gateway with mandatory circuit-breaker checks."""

    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.circuit_breaker = CircuitBreaker(config_manager=self.config_manager)
        self.executor = AlpacaExecutor()

    def execute_trade(
        self,
        symbol: str,
        action: str,
        proposed_size: float,
        confidence_score: int,
    ) -> Dict[str, Any]:
        """Execute approved trade only after strict risk validation."""
        if not bool(self.config_manager.get_setting("is_trading_active", False)):
            return {
                "executed": False,
                "reason": "Trading is disabled by master switch.",
            }

        drawdown_state = self.circuit_breaker.check_daily_drawdown()
        if drawdown_state.get("triggered"):
            return {
                "executed": False,
                "reason": "Circuit breaker triggered due to daily drawdown breach.",
                "drawdown_state": drawdown_state,
            }

        safe_size = self.circuit_breaker.enforce_position_sizing(
            proposed_size=proposed_size,
            confidence_score=confidence_score,
        )
        if safe_size <= 0:
            return {
                "executed": False,
                "reason": "Trade blocked by confidence/risk constraints.",
            }

        normalized_action = action.upper().strip()
        if normalized_action not in {"BUY", "SELL"}:
            return {
                "executed": False,
                "reason": f"Unsupported action '{action}' for execution.",
            }

        side = "buy" if normalized_action == "BUY" else "sell"

        execution_response = self.executor.place_market_order(
            symbol=symbol,
            side=side,
            quantity=safe_size,
        )

        logger.info(
            "Trade executed | symbol=%s action=%s requested_size=%.6f executed_size=%.6f confidence=%s",
            symbol,
            normalized_action,
            proposed_size,
            safe_size,
            confidence_score,
        )

        return {
            "executed": True,
            "symbol": symbol,
            "action": normalized_action,
            "position_size": safe_size,
            "confidence_score": confidence_score,
            "response": execution_response,
        }
