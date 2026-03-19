import logging
import os
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.blocking import BlockingScheduler

from ai_agent import TradeAnalyst, TradeAnalystError
from core.config_manager import ConfigManager
from core.risk_manager import CircuitBreaker
from database.init_db import init_db
from database.models import SessionLocal, TradeProposal
from notifications.telegram_bot import MobileCommander


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
MOBILE_COMMANDER: Optional[MobileCommander] = None


def _get_symbol_universe(config_manager: ConfigManager) -> List[str]:
    allowed_crypto = config_manager.get_setting("allowed_crypto", ["BTC/USD", "ETH/USD"]) or []
    allowed_stocks = config_manager.get_setting("allowed_stocks", ["AAPL", "MSFT", "NVDA"]) or []

    merged = []
    for symbol in [*allowed_crypto, *allowed_stocks]:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in merged:
            merged.append(normalized)

    return merged


def _stage_symbol(
    analyst: TradeAnalyst,
    circuit_breaker: CircuitBreaker,
    symbol: str,
) -> Dict[str, Any]:
    decision = analyst.analyze_symbol(symbol)

    if decision["action"] in {"BUY", "SELL"}:
        safe_size = circuit_breaker.enforce_position_sizing(
            proposed_size=float(decision.get("suggested_position_size", 0.0)),
            confidence_score=int(decision.get("confidence_score", 0)),
        )
        if safe_size <= 0:
            logger.warning("Proposal blocked by circuit breaker sizing rules for %s.", symbol)
            return {
                "staged": False,
                "symbol": symbol,
                "reason": "Blocked by confidence/risk sizing constraints.",
            }
        decision["suggested_position_size"] = safe_size

    return analyst.stage_proposal(decision)


def run_cycle() -> None:
    try:
        config_manager = ConfigManager()
        circuit_breaker = CircuitBreaker(config_manager=config_manager)

        if not bool(config_manager.get_setting("is_trading_active", False)):
            logger.info("Scheduler cycle skipped: master trading switch is disabled.")
            return

        drawdown_state = circuit_breaker.check_daily_drawdown()
        if drawdown_state.get("triggered"):
            logger.critical("Scheduler halted by circuit breaker: %s", drawdown_state)
            return

        symbol_universe = _get_symbol_universe(config_manager)
        if not symbol_universe:
            logger.warning("Scheduler cycle skipped: no symbols configured.")
            return

        analyst = TradeAnalyst()

        for symbol in symbol_universe:
            try:
                staged = _stage_symbol(analyst=analyst, circuit_breaker=circuit_breaker, symbol=symbol)
                logger.info("Proposal pipeline result for %s: %s", symbol, staged)

                proposal_id = staged.get("proposal_id") if isinstance(staged, dict) else None
                if MOBILE_COMMANDER is not None and proposal_id:
                    with SessionLocal() as session:
                        proposal = session.get(TradeProposal, int(proposal_id))
                        if proposal is not None:
                            MOBILE_COMMANDER.send_proposal_sync(proposal)
            except TradeAnalystError as exc:
                logger.exception("Trade analyst error for %s: %s", symbol, exc)
            except Exception as exc:
                logger.exception("Unexpected scheduler failure for %s: %s", symbol, exc)
    except Exception as exc:
        logger.exception("run_cycle failed with unhandled error: %s", exc)


def main() -> None:
    global MOBILE_COMMANDER
    init_db()

    try:
        MOBILE_COMMANDER = MobileCommander()
        MOBILE_COMMANDER.start_in_background()
    except Exception as exc:
        MOBILE_COMMANDER = None
        logger.warning("MobileCommander not started: %s", exc)

    interval_minutes = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "15"))
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_cycle, "interval", minutes=max(interval_minutes, 1), id="proposal_cycle")

    logger.info("Scheduler started with %s-minute interval.", max(interval_minutes, 1))
    run_cycle()
    scheduler.start()


if __name__ == "__main__":
    main()
