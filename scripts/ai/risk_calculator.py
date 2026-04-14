"""
risk_calculator.py — Position sizing and risk management.
Ensures no single trade risks more than MAX_RISK_PER_TRADE_PCT of balance.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.logger import get_logger

logger = get_logger("risk_calculator")

# Correlation matrix — coins that should not both be open on the same side
CORRELATION_GROUPS = [
    {"BTC", "ETH"},          # Highly correlated
    {"ETH", "SOL"},          # Moderately correlated
    {"GOLD", "SILVER"},      # Correlated commodities
]


class RiskCalculator:
    def __init__(self, account_balance: float):
        self.balance = account_balance
        self.max_risk_pct = Config.MAX_RISK_PER_TRADE_PCT / 100
        self.max_total_risk_pct = 0.08  # 8% max total open risk
        self.max_daily_loss_pct = 0.05  # 5% daily loss = stop trading

    def calc_position_size(
        self,
        entry: float,
        stop_loss: float,
        risk_pct: float = None,
    ) -> dict:
        """
        Calculate position size in base currency units.
        risk_pct: override default risk per trade (0.0 – 1.0)
        """
        risk_pct = risk_pct or self.max_risk_pct
        risk_amount = self.balance * risk_pct
        sl_distance = abs(entry - stop_loss)

        if sl_distance == 0:
            return {"error": "stop_loss equals entry"}

        units = risk_amount / sl_distance
        position_value = units * entry

        return {
            "units": round(units, 6),
            "position_value_usd": round(position_value, 2),
            "risk_amount_usd": round(risk_amount, 2),
            "risk_pct": round(risk_pct * 100, 2),
            "sl_distance_pct": round(sl_distance / entry * 100, 2),
        }

    def calc_futures_position(
        self,
        entry: float,
        stop_loss: float,
        leverage: int,
        risk_pct: float = None,
    ) -> dict:
        """
        Calculate futures position size considering leverage.
        Margin = position_value / leverage
        """
        risk_pct = risk_pct or self.max_risk_pct
        risk_amount = self.balance * risk_pct
        sl_distance = abs(entry - stop_loss)

        if sl_distance == 0:
            return {"error": "stop_loss equals entry"}

        # Without leverage: how many units to risk `risk_amount` on SL
        units = risk_amount / sl_distance
        notional_value = units * entry
        margin_required = notional_value / leverage

        # Liquidation price (approximate)
        liq_distance = entry / leverage
        liq_long = entry - liq_distance * 0.9
        liq_short = entry + liq_distance * 0.9

        return {
            "units": round(units, 6),
            "notional_value_usd": round(notional_value, 2),
            "margin_required_usd": round(margin_required, 2),
            "margin_pct_of_balance": round(margin_required / self.balance * 100, 2),
            "risk_amount_usd": round(risk_amount, 2),
            "risk_pct": round(risk_pct * 100, 2),
            "leverage": leverage,
            "liquidation_long": round(liq_long, 4),
            "liquidation_short": round(liq_short, 4),
        }

    def check_daily_drawdown(self, daily_pnl_pct: float) -> dict:
        """Check if daily loss limit has been hit."""
        pnl = daily_pnl_pct / 100
        if pnl <= -self.max_daily_loss_pct:
            return {
                "can_trade": False,
                "reason": f"Daily loss limit hit ({daily_pnl_pct:.1f}%). No new trades.",
                "daily_pnl_pct": daily_pnl_pct,
            }
        if pnl <= -0.03:
            return {
                "can_trade": True,
                "size_multiplier": 0.5,
                "reason": "Daily loss >3% — position sizes reduced by 50%",
                "daily_pnl_pct": daily_pnl_pct,
            }
        return {"can_trade": True, "size_multiplier": 1.0, "daily_pnl_pct": daily_pnl_pct}

    def check_correlation(self, new_coin: str, new_side: str, open_positions: list) -> dict:
        """
        Check if new trade is correlated with an existing open position.
        open_positions: list of dicts with 'coin' and 'side'
        """
        for group in CORRELATION_GROUPS:
            if new_coin in group:
                for pos in open_positions:
                    if pos["coin"] in group and pos["coin"] != new_coin:
                        if pos["side"] == new_side:
                            return {
                                "correlated": True,
                                "warning": f"{new_coin} is correlated with open {pos['coin']} {pos['side']} position",
                                "recommendation": "Reduce size or skip",
                            }
        return {"correlated": False}

    def validate_trade(
        self,
        coin: str,
        side: str,
        entry: float,
        stop_loss: float,
        daily_pnl_pct: float,
        open_positions: list,
    ) -> dict:
        """Full pre-trade validation: drawdown + correlation + position size."""
        dd = self.check_daily_drawdown(daily_pnl_pct)
        if not dd["can_trade"]:
            return {"approved": False, "reason": dd["reason"]}

        corr = self.check_correlation(coin, side, open_positions)
        size_mult = dd.get("size_multiplier", 1.0)

        risk_pct = self.max_risk_pct * size_mult
        sizing = self.calc_position_size(entry, stop_loss, risk_pct)

        return {
            "approved": True,
            "position_size": sizing,
            "correlation_warning": corr.get("correlated", False),
            "correlation_note": corr.get("warning"),
            "size_multiplier": size_mult,
            "notes": dd.get("reason"),
        }
