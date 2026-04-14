"""
order_manager.py — Place, cancel, and manage SL/TP orders on exchanges.
Wraps ExchangeConnector with retry logic and order tracking in Firestore.
"""

import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.trading.exchange_connector import ExchangeConnector
from scripts.utils.firebase_client import add_doc, set_doc
from scripts.utils.logger import get_logger

logger = get_logger("order_manager")

MAX_RETRIES = 3
RETRY_DELAY = 2


class OrderManager:
    def __init__(self, connector: ExchangeConnector, user_id: str):
        self.cx = connector
        self.user_id = user_id

    def open_trade(
        self,
        coin: str,
        symbol: str,
        side: str,
        amount: float,
        entry_price: float,
        stop_loss: float,
        take_profits: list,
        leverage: int = 1,
        is_futures: bool = False,
        margin_mode: str = "isolated",
        signal: dict = None,
    ) -> dict | None:
        """
        Place entry order + SL + TP orders in sequence.
        Returns trade record saved to Firestore.
        """
        mode = self.cx.trading_mode
        is_demo = self.cx.is_demo

        # 1. Set leverage and margin mode for futures
        if is_futures and leverage > 1:
            self.cx.set_margin_mode(symbol, margin_mode)
            self.cx.set_leverage(symbol, leverage)

        # 2. Place entry order
        entry_order = self._place_with_retry(
            lambda: (
                self.cx.place_futures_order(symbol, side, amount, entry_price, leverage)
                if is_futures
                else self.cx.place_spot_order(symbol, side, amount, entry_price)
            )
        )

        if not entry_order:
            logger.error("Entry order failed for %s %s", coin, side)
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        close_side = "sell" if side == "buy" else "buy"

        # 3. Place stop-loss order
        sl_order = self._place_with_retry(
            lambda: (
                self.cx.place_futures_order(symbol, close_side, amount, stop_loss, leverage, reduce_only=True)
                if is_futures
                else self.cx.place_spot_order(symbol, close_side, amount, stop_loss)
            )
        )

        # 4. Place take-profit orders
        tp_orders = []
        tp_amounts = self._split_tp_amounts(amount, len(take_profits))
        for tp_price, tp_amount in zip(take_profits, tp_amounts):
            tp_order = self._place_with_retry(
                lambda p=tp_price, a=tp_amount: (
                    self.cx.place_futures_order(symbol, close_side, a, p, leverage, reduce_only=True)
                    if is_futures
                    else self.cx.place_spot_order(symbol, close_side, a, p)
                )
            )
            if tp_order:
                tp_orders.append(tp_order)

        # 5. Build trade record
        liq_price = ExchangeConnector._calc_liq_price(entry_price, leverage, side) if is_futures else None

        trade_record = {
            "coin": coin,
            "symbol": symbol,
            "exchange": self.cx.exchange_name,
            "trading_mode": mode,
            "side": side,
            "is_futures": is_futures,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "entry_price": entry_price,
            "quantity": amount,
            "stop_loss": stop_loss,
            "take_profits": take_profits,
            "liquidation_price": liq_price,
            "entry_order_id": entry_order.get("id"),
            "sl_order_id": sl_order.get("id") if sl_order else None,
            "tp_order_ids": [o.get("id") for o in tp_orders],
            "status": "open",
            "pnl_usdt": 0,
            "pnl_percent": 0,
            "is_demo": is_demo,
            "signal_confidence": signal.get("confidence") if signal else None,
            "opened_at": now_iso,
            "closed_at": None,
            "close_reason": None,
            "user_id": self.user_id,
        }

        # 6. Save to Firestore
        doc_id = add_doc(f"trades/{self.user_id}/live_history" if not is_demo else f"trades/{self.user_id}/demo_history", trade_record)
        trade_record["id"] = doc_id
        logger.info(
            "Trade opened: %s %s %s @ $%.2f SL=$%.2f TP=%s lev=%dx demo=%s",
            side.upper(), amount, coin, entry_price, stop_loss,
            [round(t, 2) for t in take_profits], leverage, is_demo,
        )
        return trade_record

    def close_trade(self, trade: dict, current_price: float, reason: str) -> dict:
        """Close an open trade at current_price."""
        symbol = trade.get("symbol")
        side = trade.get("side")
        amount = trade.get("quantity")
        is_futures = trade.get("is_futures", False)
        leverage = trade.get("leverage", 1)
        is_demo = trade.get("is_demo", False)

        close_side = "sell" if side == "buy" else "buy"

        if is_futures:
            self.cx.place_futures_order(symbol, close_side, amount, reduce_only=True)
        else:
            self.cx.place_spot_order(symbol, close_side, amount)

        # Calculate PnL
        entry = trade.get("entry_price", current_price)
        if side == "buy":
            pnl = (current_price - entry) * amount
        else:
            pnl = (entry - current_price) * amount
        pnl_pct = (pnl / (entry * amount) * 100) if entry and amount else 0

        now_iso = datetime.now(timezone.utc).isoformat()
        trade["status"] = "closed"
        trade["close_price"] = current_price
        trade["close_reason"] = reason
        trade["pnl_usdt"] = round(pnl, 4)
        trade["pnl_percent"] = round(pnl_pct, 2)
        trade["closed_at"] = now_iso

        # Update in Firestore
        collection = f"trades/{self.user_id}/live_history" if not is_demo else f"trades/{self.user_id}/demo_history"
        if trade.get("id"):
            set_doc(collection, trade["id"], trade)

        logger.info("Trade closed: %s reason=%s pnl=$%.2f (%.2f%%)",
                    trade.get("coin"), reason, pnl, pnl_pct)
        return trade

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _place_with_retry(self, order_fn) -> dict | None:
        for attempt in range(MAX_RETRIES):
            try:
                result = order_fn()
                if result:
                    return result
            except Exception as exc:
                logger.warning("Order attempt %d failed: %s", attempt + 1, exc)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        return None

    @staticmethod
    def _split_tp_amounts(total_amount: float, num_tps: int) -> list:
        """Split total position across TPs (25/50/25 default for 3 TPs)."""
        if num_tps == 3:
            return [total_amount * 0.25, total_amount * 0.50, total_amount * 0.25]
        if num_tps == 2:
            return [total_amount * 0.50, total_amount * 0.50]
        return [total_amount]
