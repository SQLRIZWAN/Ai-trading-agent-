"""
demo_engine.py — Paper/Demo trading engine.
Simulates spot and futures trades using real market prices with virtual balance.
Run with --mode execute to process pending demo signals.
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.alerts.telegram_bot import TelegramBot
from scripts.trading.exchange_connector import ExchangeConnector
from scripts.utils.config import Config
from scripts.utils.firebase_client import db, get_doc, set_doc, add_doc, get_collection
from scripts.utils.logger import get_logger

logger = get_logger("demo_engine")

BINANCE_BASE = "https://api.binance.com/api/v3"


class DemoEngine:
    def __init__(self):
        self.telegram = TelegramBot()
        self.min_confidence = Config.MIN_DEMO_CONFIDENCE

    def get_current_price(self, coin: str) -> float:
        """Fetch live price from Binance public API."""
        pairs = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
        pair = pairs.get(coin)
        if not pair:
            # Fallback to Firestore cached price
            doc = get_doc("market_data", coin) or {}
            return doc.get("latest", {}).get("price", 0)
        try:
            resp = requests.get(
                f"{BINANCE_BASE}/ticker/price",
                params={"symbol": pair},
                timeout=8,
            )
            return float(resp.json().get("price", 0))
        except Exception:
            doc = get_doc("market_data", coin) or {}
            return doc.get("latest", {}).get("price", 0)

    def execute_all_users(self):
        """Execute demo trades for all users with demo mode enabled."""
        users = get_collection("users")
        for user in users:
            uid = user.get("id")
            settings = user.get("trading_settings", {})

            demo_spot = settings.get("demo_spot_enabled", False)
            demo_futures = settings.get("demo_futures_enabled", False)

            if not (demo_spot or demo_futures):
                continue

            try:
                self._execute_for_user(uid, demo_spot, demo_futures)
            except Exception as exc:
                logger.error("Demo execution failed for user %s: %s", uid, exc)

    def _execute_for_user(self, uid: str, spot_enabled: bool, futures_enabled: bool):
        """Process latest signals and execute as demo trades for one user."""
        assets = ["BTC", "ETH", "SOL"]

        for coin in assets:
            current_price = self.get_current_price(coin)

            # Check + update open demo positions first
            self._update_open_positions(uid, coin, current_price)

            # Execute new spot demo trade
            if spot_enabled:
                signal_doc = get_doc("signals", coin) or {}
                signal = signal_doc.get("spot_latest", {})
                if (signal.get("signal") in ("BUY", "SELL")
                        and signal.get("confidence", 0) >= self.min_confidence
                        and signal.get("status") == "active"):
                    self._open_demo_spot(uid, coin, signal, current_price)

            # Execute new futures demo trade
            if futures_enabled:
                signal_doc = get_doc("signals", coin) or {}
                signal = signal_doc.get("futures_latest", {})
                if (signal.get("signal") in ("LONG", "SHORT")
                        and signal.get("confidence", 0) >= self.min_confidence
                        and signal.get("status") == "active"):
                    self._open_demo_futures(uid, coin, signal, current_price)

    def _open_demo_spot(self, uid: str, coin: str, signal: dict, current_price: float):
        """Open a demo spot position."""
        # Check if already in a spot position for this coin
        demo_acc = get_doc("demo_accounts", uid) or {}
        existing = [p for p in demo_acc.get("spot_positions", []) if p.get("coin") == coin]
        if existing:
            return  # Already have a position

        side = "buy" if signal["signal"] == "BUY" else "sell"
        risk_pct = demo_acc.get("settings", {}).get("risk_per_trade_pct", 2) / 100
        balance_usdt = demo_acc.get("balance", {}).get("USDT", {}).get("free", 0)

        entry_price = current_price
        sl = signal.get("stop_loss", entry_price * 0.98)
        tp1 = signal.get("take_profit_1", entry_price * 1.02)
        tp2 = signal.get("take_profit_2", entry_price * 1.04)
        tp3 = signal.get("take_profit_3", entry_price * 1.06)

        sl_distance = abs(entry_price - sl)
        if sl_distance == 0:
            return

        risk_amount = balance_usdt * risk_pct
        quantity = risk_amount / sl_distance
        cost = quantity * entry_price

        if cost > balance_usdt:
            quantity = balance_usdt * 0.02 / entry_price  # fallback: use 2% of balance
            cost = quantity * entry_price

        position = {
            "id": f"demo_spot_{int(time.time() * 1000)}",
            "coin": coin,
            "side": side,
            "entry_price": entry_price,
            "current_price": entry_price,
            "quantity": quantity,
            "cost": cost,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": tp3,
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "pnl_usdt": 0,
            "pnl_pct": 0,
            "status": "open",
            "signal_confidence": signal.get("confidence"),
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "type": "demo_spot",
        }

        # Update demo account
        spot_positions = demo_acc.get("spot_positions", [])
        spot_positions.append(position)
        # Deduct USDT
        usdt = demo_acc.get("balance", {}).get("USDT", {"free": 0, "used": 0, "total": 0})
        usdt["free"] = max(0, usdt["free"] - cost)
        usdt["used"] = usdt.get("used", 0) + cost

        set_doc("demo_accounts", uid, {
            "spot_positions": spot_positions,
            "balance": {**demo_acc.get("balance", {}), "USDT": usdt},
        }, merge=True)

        # Log trade
        trade_record = {**position, "user_id": uid, "is_demo": True}
        add_doc(f"trades/{uid}/demo_history", trade_record)

        self.telegram.send_trade_executed({**position, "is_demo": True, "trading_mode": "spot"})
        logger.info("Demo SPOT opened: %s %s %s qty=%.6f entry=$%.2f",
                    uid, side.upper(), coin, quantity, entry_price)

    def _open_demo_futures(self, uid: str, coin: str, signal: dict, current_price: float):
        """Open a demo futures position."""
        demo_acc = get_doc("demo_accounts", uid) or {}
        existing = [p for p in demo_acc.get("futures_positions", []) if p.get("coin") == coin]
        if existing:
            return

        direction = signal["signal"]  # LONG or SHORT
        side = "buy" if direction == "LONG" else "sell"
        leverage = min(signal.get("recommended_leverage", 5), demo_acc.get("settings", {}).get("max_leverage", 10))
        margin_mode = signal.get("margin_mode", "isolated")
        risk_pct = demo_acc.get("settings", {}).get("risk_per_trade_pct", 2) / 100
        balance_usdt = demo_acc.get("balance", {}).get("USDT", {}).get("free", 0)

        entry_price = current_price
        sl = signal.get("stop_loss", entry_price * 0.98)
        tp1 = signal.get("take_profit_1", entry_price * 1.02)
        tp2 = signal.get("take_profit_2", entry_price * 1.04)
        tp3 = signal.get("take_profit_3", entry_price * 1.06)

        sl_distance = abs(entry_price - sl)
        if sl_distance == 0:
            return

        risk_amount = balance_usdt * risk_pct
        quantity = (risk_amount * leverage) / sl_distance
        notional = quantity * entry_price
        margin = notional / leverage
        liq_price = ExchangeConnector._calc_liq_price(entry_price, leverage, side)

        if margin > balance_usdt * 0.15:  # Max 15% margin per trade
            margin = balance_usdt * 0.15
            notional = margin * leverage
            quantity = notional / entry_price

        position = {
            "id": f"demo_fut_{int(time.time() * 1000)}",
            "coin": coin,
            "symbol": f"{coin}/USDT",
            "side": direction.lower(),
            "entry_price": entry_price,
            "current_price": entry_price,
            "quantity": quantity,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "margin_used": margin,
            "notional_value": notional,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": tp3,
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "liquidation_price": liq_price,
            "unrealized_pnl": 0,
            "unrealized_pnl_pct": 0,
            "funding_paid": 0,
            "status": "open",
            "signal_confidence": signal.get("confidence"),
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "type": "demo_futures",
        }

        futures_positions = demo_acc.get("futures_positions", [])
        futures_positions.append(position)
        usdt = demo_acc.get("balance", {}).get("USDT", {"free": 0, "used": 0, "total": 0})
        usdt["free"] = max(0, usdt["free"] - margin)
        usdt["used"] = usdt.get("used", 0) + margin

        set_doc("demo_accounts", uid, {
            "futures_positions": futures_positions,
            "balance": {**demo_acc.get("balance", {}), "USDT": usdt},
        }, merge=True)

        add_doc(f"trades/{uid}/demo_history", {**position, "user_id": uid, "is_demo": True})
        self.telegram.send_trade_executed({
            **position, "is_demo": True, "trading_mode": "futures",
            "entry_price": entry_price, "stop_loss": sl, "take_profit_1": tp1,
        })
        logger.info("Demo FUTURES opened: %s %s %s lev=%dx qty=%.6f margin=$%.2f liq=$%.2f",
                    uid, direction, coin, leverage, quantity, margin, liq_price)

    def _update_open_positions(self, uid: str, coin: str, current_price: float):
        """Update PnL and check SL/TP for all open demo positions for a coin."""
        demo_acc = get_doc("demo_accounts", uid)
        if not demo_acc:
            return

        # ── Spot positions ──
        spot_positions = demo_acc.get("spot_positions", [])
        updated_spot = []
        for pos in spot_positions:
            if pos.get("coin") != coin or pos.get("status") != "open":
                updated_spot.append(pos)
                continue

            pos = self._update_spot_pnl(pos, current_price)
            close_reason = self._check_sl_tp_spot(pos, current_price)
            if close_reason:
                pos = self._close_spot_position(uid, pos, current_price, close_reason)
            else:
                updated_spot.append(pos)

        # ── Futures positions ──
        fut_positions = demo_acc.get("futures_positions", [])
        updated_fut = []
        for pos in fut_positions:
            if pos.get("coin") != coin or pos.get("status") != "open":
                updated_fut.append(pos)
                continue

            pos = self._update_futures_pnl(pos, current_price)
            close_reason = self._check_sl_tp_futures(pos, current_price)
            if close_reason:
                pos = self._close_futures_position(uid, pos, current_price, close_reason)
            else:
                updated_fut.append(pos)

        set_doc("demo_accounts", uid, {
            "spot_positions": updated_spot,
            "futures_positions": updated_fut,
        }, merge=True)

    def _update_spot_pnl(self, pos: dict, current_price: float) -> dict:
        side = pos.get("side")
        entry = pos.get("entry_price", current_price)
        qty = pos.get("quantity", 0)
        pnl = (current_price - entry) * qty if side == "buy" else (entry - current_price) * qty
        pos["current_price"] = current_price
        pos["pnl_usdt"] = round(pnl, 4)
        pos["pnl_pct"] = round(pnl / (entry * qty) * 100, 2) if entry and qty else 0
        return pos

    def _update_futures_pnl(self, pos: dict, current_price: float) -> dict:
        side = pos.get("side")  # long or short
        entry = pos.get("entry_price", current_price)
        qty = pos.get("quantity", 0)
        leverage = pos.get("leverage", 1)
        if side == "long":
            pnl = (current_price - entry) * qty
        else:
            pnl = (entry - current_price) * qty
        margin = pos.get("margin_used", 1)
        pos["current_price"] = current_price
        pos["unrealized_pnl"] = round(pnl, 4)
        pos["unrealized_pnl_pct"] = round(pnl / margin * 100, 2) if margin else 0
        return pos

    def _check_sl_tp_spot(self, pos: dict, price: float) -> str | None:
        side = pos.get("side")
        sl = pos.get("stop_loss")
        tp1 = pos.get("take_profit_1")
        tp2 = pos.get("take_profit_2")
        tp3 = pos.get("take_profit_3")

        if side == "buy":
            if sl and price <= sl:
                return "stop_loss"
            if tp3 and price >= tp3 and not pos.get("tp3_hit"):
                return "take_profit_3"
            if tp2 and price >= tp2 and not pos.get("tp2_hit"):
                return "take_profit_2"
            if tp1 and price >= tp1 and not pos.get("tp1_hit"):
                return "take_profit_1"
        elif side == "sell":
            if sl and price >= sl:
                return "stop_loss"
            if tp3 and price <= tp3 and not pos.get("tp3_hit"):
                return "take_profit_3"
        return None

    def _check_sl_tp_futures(self, pos: dict, price: float) -> str | None:
        side = pos.get("side")  # long or short
        sl = pos.get("stop_loss")
        tp1 = pos.get("take_profit_1")
        liq = pos.get("liquidation_price")

        if side == "long":
            if liq and price <= liq:
                return "liquidated"
            if sl and price <= sl:
                return "stop_loss"
            if tp1 and price >= tp1 and not pos.get("tp1_hit"):
                return "take_profit_1"
        elif side == "short":
            if liq and price >= liq:
                return "liquidated"
            if sl and price >= sl:
                return "stop_loss"
            if tp1 and price <= tp1 and not pos.get("tp1_hit"):
                return "take_profit_1"
        return None

    def _close_spot_position(self, uid: str, pos: dict, price: float, reason: str) -> dict:
        pos["status"] = "closed"
        pos["close_price"] = price
        pos["close_reason"] = reason
        pos["closed_at"] = datetime.now(timezone.utc).isoformat()

        pnl = pos.get("pnl_usdt", 0)
        self._update_demo_stats(uid, pnl, pos.get("cost", 0), "spot")
        self.telegram.send_trade_closed({**pos, "is_demo": True})
        logger.info("Demo SPOT closed: %s %s reason=%s pnl=$%.2f", uid, pos["coin"], reason, pnl)
        return pos

    def _close_futures_position(self, uid: str, pos: dict, price: float, reason: str) -> dict:
        pos["status"] = "closed"
        pos["close_price"] = price
        pos["close_reason"] = reason
        pos["closed_at"] = datetime.now(timezone.utc).isoformat()

        pnl = pos.get("unrealized_pnl", 0)
        margin = pos.get("margin_used", 0)

        # Return margin (minus loss if any)
        returned_margin = max(0, margin + pnl) if reason == "liquidated" else margin + pnl
        self._return_demo_margin(uid, returned_margin)
        self._update_demo_stats(uid, pnl, margin, "futures")
        self.telegram.send_trade_closed({**pos, "is_demo": True, "pnl_usdt": pnl, "pnl_percent": pos.get("unrealized_pnl_pct", 0)})
        logger.info("Demo FUTURES closed: %s %s reason=%s pnl=$%.2f", uid, pos["coin"], reason, pnl)
        return pos

    def _update_demo_stats(self, uid: str, pnl: float, invested: float, trade_type: str):
        try:
            doc = get_doc("demo_accounts", uid) or {}
            stats = doc.get("stats", {})
            total = stats.get("total_trades", 0) + 1
            winning = stats.get("winning_trades", 0) + (1 if pnl > 0 else 0)
            losing = stats.get("losing_trades", 0) + (1 if pnl <= 0 else 0)
            total_pnl = stats.get("total_pnl_usdt", 0) + pnl
            init_bal = doc.get("initial_balance", Config.DEMO_INITIAL_BALANCE)

            set_doc("demo_accounts", uid, {"stats": {
                "total_trades": total,
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate": round(winning / total * 100, 1) if total else 0,
                "total_pnl_usdt": round(total_pnl, 2),
                "total_pnl_pct": round(total_pnl / init_bal * 100, 2) if init_bal else 0,
            }}, merge=True)
        except Exception as exc:
            logger.error("Stats update failed for %s: %s", uid, exc)

    def _return_demo_margin(self, uid: str, amount: float):
        try:
            doc = get_doc("demo_accounts", uid) or {}
            usdt = doc.get("balance", {}).get("USDT", {"free": 0, "used": 0, "total": 0})
            usdt["free"] = usdt.get("free", 0) + amount
            usdt["used"] = max(0, usdt.get("used", 0) - amount)
            set_doc("demo_accounts", uid, {"balance": {**doc.get("balance", {}), "USDT": usdt}}, merge=True)
        except Exception as exc:
            logger.error("Return margin failed for %s: %s", uid, exc)


def run_execute():
    logger.info("=== demo_engine EXECUTE START ===")
    engine = DemoEngine()
    engine.execute_all_users()
    logger.info("=== demo_engine EXECUTE DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["execute"], default="execute")
    args = parser.parse_args()

    if args.mode == "execute":
        run_execute()
