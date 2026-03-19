import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.config_manager import ConfigManager
from database.models import LedgerReconciliationRun, SessionLocal, TradeRecord

try:
    import alpaca_trade_api as tradeapi  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    tradeapi = None


logger = logging.getLogger(__name__)


class DeepLedgerReconciliationService:
    """Reconcile internal trade ledger with broker/account snapshot and persist run history."""

    def __init__(self, config_manager: Optional[ConfigManager] = None) -> None:
        self.config_manager = config_manager or ConfigManager()

    def run_reconciliation(self, lookback_hours: int = 24) -> Dict[str, Any]:
        expected = self._compute_expected_ledger(lookback_hours=lookback_hours)
        broker_snapshot = self._fetch_broker_snapshot(lookback_hours=lookback_hours)

        tolerance = float(self.config_manager.get_setting("ledger_reconciliation_tolerance", 1.0))
        tolerance = max(tolerance, 0.0)

        absolute_delta = abs(expected["net_cashflow"] - broker_snapshot["net_cashflow"])
        status = "PASS" if absolute_delta <= tolerance else "DRIFT"

        result = {
            "status": status,
            "source": broker_snapshot["source"],
            "expected_net_cashflow": expected["net_cashflow"],
            "broker_net_cashflow": broker_snapshot["net_cashflow"],
            "absolute_delta": absolute_delta,
            "tolerance_threshold": tolerance,
            "summary": self._build_summary(status=status, delta=absolute_delta, tolerance=tolerance),
            "details": {
                "window_hours": lookback_hours,
                "expected": expected,
                "broker": broker_snapshot,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        self._persist_reconciliation_run(result)

        if status == "DRIFT":
            logger.warning("Ledger reconciliation drift detected: %s", result["summary"])
        else:
            logger.info("Ledger reconciliation passed: %s", result["summary"])

        return result

    def _compute_expected_ledger(self, lookback_hours: int) -> Dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(lookback_hours, 1))

        with SessionLocal() as session:
            records = (
                session.query(TradeRecord)
                .filter(TradeRecord.timestamp >= cutoff.replace(tzinfo=None))
                .order_by(TradeRecord.timestamp.asc())
                .all()
            )

        buy_notional = 0.0
        sell_notional = 0.0
        for record in records:
            side = str(getattr(record, "side", "")).upper().strip()
            quantity = float(getattr(record, "quantity", 0.0) or 0.0)
            price = float(getattr(record, "price", 0.0) or 0.0)
            notional = quantity * price

            if side == "BUY":
                buy_notional += notional
            elif side == "SELL":
                sell_notional += notional

        net_cashflow = sell_notional - buy_notional

        return {
            "trade_count": len(records),
            "buy_notional": buy_notional,
            "sell_notional": sell_notional,
            "net_cashflow": net_cashflow,
        }

    def _fetch_broker_snapshot(self, lookback_hours: int) -> Dict[str, Any]:
        if tradeapi is None:
            fallback = float(self.config_manager.get_setting("broker_cashflow_fallback", 0.0))
            return {
                "source": "CONFIG_FALLBACK",
                "window_hours": lookback_hours,
                "net_cashflow": fallback,
                "equity": float(self.config_manager.get_setting("broker_equity_fallback", 0.0)),
            }

        api_key = os.getenv("ALPACA_API_KEY", "").strip()
        secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()

        if not api_key or not secret_key:
            fallback = float(self.config_manager.get_setting("broker_cashflow_fallback", 0.0))
            return {
                "source": "CONFIG_FALLBACK",
                "window_hours": lookback_hours,
                "net_cashflow": fallback,
                "equity": float(self.config_manager.get_setting("broker_equity_fallback", 0.0)),
            }

        try:
            api = tradeapi.REST(api_key, secret_key, base_url=base_url)  # type: ignore[arg-type]
            account = api.get_account()
            equity = float(getattr(account, "equity", 0.0))
            last_equity = float(getattr(account, "last_equity", equity))
            net_cashflow = equity - last_equity

            return {
                "source": "ALPACA_ACCOUNT",
                "window_hours": lookback_hours,
                "net_cashflow": net_cashflow,
                "equity": equity,
                "last_equity": last_equity,
            }
        except Exception as exc:
            logger.warning("Broker snapshot fetch failed, using fallback values: %s", exc)
            fallback = float(self.config_manager.get_setting("broker_cashflow_fallback", 0.0))
            return {
                "source": "CONFIG_FALLBACK",
                "window_hours": lookback_hours,
                "net_cashflow": fallback,
                "equity": float(self.config_manager.get_setting("broker_equity_fallback", 0.0)),
                "error": str(exc),
            }

    @staticmethod
    def _build_summary(status: str, delta: float, tolerance: float) -> str:
        if status == "PASS":
            return f"Ledger matched broker within tolerance (${delta:,.2f} <= ${tolerance:,.2f})."
        return f"Ledger drift detected (${delta:,.2f} > ${tolerance:,.2f})."

    def _persist_reconciliation_run(self, result: Dict[str, Any]) -> None:
        run = LedgerReconciliationRun(
            status=result["status"],
            source=result["source"],
            expected_net_cashflow=float(result["expected_net_cashflow"]),
            broker_net_cashflow=float(result["broker_net_cashflow"]),
            absolute_delta=float(result["absolute_delta"]),
            tolerance_threshold=float(result["tolerance_threshold"]),
            summary=str(result["summary"]),
            details_json=json.dumps(result["details"]),
        )

        with SessionLocal() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
