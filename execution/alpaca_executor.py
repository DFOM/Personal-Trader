from typing import Optional


class AlpacaExecutor:
    """Thin execution adapter placeholder for Alpaca market orders."""

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float = 1.0,
        notional: Optional[float] = None,
    ) -> dict:
        return {
            "status": "submitted",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "notional": notional,
            "note": "Replace this placeholder with the Phase 2 Alpaca API implementation.",
        }
