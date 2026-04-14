"""
exchange_connector.py — Unified exchange interface (Spot + Futures + Demo).
Supports: Binance, Bitget, Bybit, OKX, KuCoin via CCXT.
Demo mode simulates trades using real market prices with virtual balance.
"""

import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, get_doc, set_doc
from scripts.utils.logger import get_logger

logger = get_logger("exchange_connector")

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logger.warning("ccxt not installed — exchange connectivity unavailable")

SUPPORTED = ["binance", "bitget", "bybit", "okx", "kucoin"]
TESTNET_SUPPORTED = ["binance", "bybit"]


class ExchangeConnector:
    def __init__(
        self,
        exchange_name: str,
        api_key: str = None,
        secret_key: str = None,
        passphrase: str = None,
        trading_mode: str = "spot",  # spot | futures | demo_spot | demo_futures
        user_id: str = None,
    ):
        assert exchange_name in SUPPORTED, f"Unsupported exchange: {exchange_name}"
        self.exchange_name = exchange_name
        self.trading_mode = trading_mode
        self.user_id = user_id
        self.is_demo = trading_mode.startswith("demo")
        self.market_type = "spot" if "spot" in trading_mode else "future"

        if not CCXT_AVAILABLE:
            self.exchange = None
            return

        exchange_class = getattr(ccxt, exchange_name)
        config = {
            "enableRateLimit": True,
            "options": {"defaultType": self.market_type},
        }

        if self.is_demo and exchange_name in TESTNET_SUPPORTED:
            # Use exchange testnet for demo when available
            config["options"]["testnet"] = True
            config["apiKey"] = api_key
            config["secret"] = secret_key
        elif not self.is_demo:
            config["apiKey"] = api_key
            config["secret"] = secret_key
        # else: demo on non-testnet exchanges → use public API for prices only

        if passphrase:
            config["password"] = passphrase

        self.exchange = exchange_class(config)

    # ─── Balance ─────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        if self.is_demo and not self._has_testnet():
            return self._get_demo_balance()
        if not self.exchange:
            return {}
        try:
            raw = self.exchange.fetch_balance()
            return {k: v for k, v in raw.items() if isinstance(v, dict) and v.get("total", 0) > 0}
        except Exception as exc:
            logger.error("get_balance failed: %s", exc)
            return {}

    # ─── Market data (always uses live exchange, even in demo) ────────────

    def get_ticker(self, symbol: str) -> dict:
        if not self.exchange:
            return {}
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as exc:
            logger.warning("get_ticker %s failed: %s", symbol, exc)
            return {}

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        if not self.exchange:
            return {}
        try:
            return self.exchange.fetch_order_book(symbol, limit)
        except Exception as exc:
            logger.warning("get_orderbook %s failed: %s", symbol, exc)
            return {}

    # ─── Spot orders ──────────────────────────────────────────────────────

    def place_spot_order(
        self, symbol: str, side: str, amount: float, price: float = None
    ) -> dict:
        if self.is_demo and not self._has_testnet():
            return self._simulate_spot_order(symbol, side, amount, price)
        if not self.exchange:
            return {}
        order_type = "limit" if price else "market"
        try:
            return self.exchange.create_order(symbol, order_type, side, amount, price)
        except Exception as exc:
            logger.error("place_spot_order failed: %s", exc)
            return {}

    # ─── Futures orders ───────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        if self.is_demo and not self._has_testnet():
            return {"symbol": symbol, "leverage": leverage, "mode": "demo"}
        if not self.exchange:
            return {}
        try:
            return self.exchange.set_leverage(leverage, symbol)
        except Exception as exc:
            logger.warning("set_leverage %s %dx failed: %s", symbol, leverage, exc)
            return {}

    def set_margin_mode(self, symbol: str, mode: str = "isolated") -> dict:
        if self.is_demo and not self._has_testnet():
            return {"symbol": symbol, "margin_mode": mode, "mode": "demo"}
        if not self.exchange:
            return {}
        try:
            return self.exchange.set_margin_mode(mode, symbol)
        except Exception as exc:
            logger.warning("set_margin_mode %s failed: %s", symbol, exc)
            return {}

    def place_futures_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        leverage: int = 5,
        reduce_only: bool = False,
    ) -> dict:
        if self.is_demo and not self._has_testnet():
            return self._simulate_futures_order(symbol, side, amount, price, leverage)
        if not self.exchange:
            return {}
        self.set_leverage(symbol, leverage)
        order_type = "limit" if price else "market"
        params = {"reduceOnly": reduce_only}
        try:
            return self.exchange.create_order(symbol, order_type, side, amount, price, params)
        except Exception as exc:
            logger.error("place_futures_order failed: %s", exc)
            return {}

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        if self.is_demo and not self._has_testnet():
            return {"id": order_id, "status": "canceled", "mode": "demo"}
        if not self.exchange:
            return {}
        try:
            return self.exchange.cancel_order(order_id, symbol)
        except Exception as exc:
            logger.error("cancel_order %s failed: %s", order_id, exc)
            return {}

    def get_positions(self, symbol: str = None) -> list:
        if self.is_demo and not self._has_testnet():
            return self._get_demo_positions()
        if not self.exchange:
            return []
        try:
            symbols = [symbol] if symbol else None
            return self.exchange.fetch_positions(symbols)
        except Exception as exc:
            logger.error("get_positions failed: %s", exc)
            return []

    def get_funding_rate(self, symbol: str) -> dict:
        if not self.exchange:
            return {}
        try:
            return self.exchange.fetch_funding_rate(symbol)
        except Exception as exc:
            logger.warning("get_funding_rate %s failed: %s", symbol, exc)
            return {}

    # ─── Demo simulation ──────────────────────────────────────────────────

    def _has_testnet(self) -> bool:
        return self.exchange_name in TESTNET_SUPPORTED

    def _get_demo_balance(self) -> dict:
        if not self.user_id:
            return {}
        doc = get_doc("demo_accounts", self.user_id) or {}
        if not doc.get("balance"):
            initial = {
                "balance": {
                    "USDT": {"free": Config.DEMO_INITIAL_BALANCE, "used": 0.0, "total": Config.DEMO_INITIAL_BALANCE}
                },
                "initial_balance": Config.DEMO_INITIAL_BALANCE,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "stats": {
                    "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                    "win_rate": 0.0, "total_pnl_usdt": 0.0, "total_pnl_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                },
            }
            set_doc("demo_accounts", self.user_id, initial)
            return initial["balance"]
        return doc["balance"]

    def _get_demo_positions(self) -> list:
        if not self.user_id:
            return []
        doc = get_doc("demo_accounts", self.user_id) or {}
        return doc.get("futures_positions", [])

    def _simulate_spot_order(self, symbol: str, side: str, amount: float, price: float = None) -> dict:
        ticker = self.get_ticker(symbol)
        exec_price = price or ticker.get("last", 0)
        cost = amount * exec_price

        order = {
            "id": f"demo_{int(time.time() * 1000)}",
            "symbol": symbol,
            "side": side,
            "type": "limit" if price else "market",
            "amount": amount,
            "price": exec_price,
            "cost": cost,
            "status": "closed",
            "mode": "demo_spot",
            "timestamp": time.time(),
        }

        self._update_demo_balance_spot(side, symbol, amount, exec_price, cost)
        logger.info("Demo spot order: %s %s %s @ $%s", side.upper(), amount, symbol, exec_price)
        return order

    def _simulate_futures_order(
        self, symbol: str, side: str, amount: float, price: float = None, leverage: int = 5
    ) -> dict:
        ticker = self.get_ticker(symbol)
        exec_price = price or ticker.get("last", 0)
        notional = amount * exec_price
        margin = notional / leverage
        liq_price = self._calc_liq_price(exec_price, leverage, side)

        order = {
            "id": f"demo_fut_{int(time.time() * 1000)}",
            "symbol": symbol,
            "side": side,
            "type": "limit" if price else "market",
            "amount": amount,
            "price": exec_price,
            "leverage": leverage,
            "margin_used": margin,
            "notional_value": notional,
            "liquidation_price": liq_price,
            "status": "open",
            "mode": "demo_futures",
            "timestamp": time.time(),
        }

        self._deduct_demo_margin(margin)
        logger.info("Demo futures order: %s %s %s @ $%s (lev=%dx liq=$%s)",
                    side.upper(), amount, symbol, exec_price, leverage, round(liq_price, 2))
        return order

    @staticmethod
    def _calc_liq_price(entry: float, leverage: int, side: str) -> float:
        liq_pct = 1 / leverage
        if side == "buy":  # LONG
            return entry * (1 - liq_pct + 0.005)
        return entry * (1 + liq_pct - 0.005)  # SHORT

    def _update_demo_balance_spot(self, side: str, symbol: str, amount: float, price: float, cost: float):
        if not self.user_id:
            return
        try:
            doc = get_doc("demo_accounts", self.user_id) or {}
            balance = doc.get("balance", {})
            usdt = balance.get("USDT", {"free": 0, "used": 0, "total": 0})
            coin = symbol.replace("/USDT", "").replace("USDT", "")
            coin_bal = balance.get(coin, {"free": 0, "used": 0, "total": 0})

            if side == "buy":
                usdt["free"] -= cost
                usdt["total"] -= cost
                coin_bal["free"] = coin_bal.get("free", 0) + amount
                coin_bal["total"] = coin_bal.get("total", 0) + amount
            else:
                usdt["free"] += cost
                usdt["total"] += cost
                coin_bal["free"] = max(0, coin_bal.get("free", 0) - amount)
                coin_bal["total"] = max(0, coin_bal.get("total", 0) - amount)

            balance["USDT"] = usdt
            balance[coin] = coin_bal
            set_doc("demo_accounts", self.user_id, {"balance": balance}, merge=True)
        except Exception as exc:
            logger.error("Demo balance update failed: %s", exc)

    def _deduct_demo_margin(self, margin: float):
        if not self.user_id:
            return
        try:
            doc = get_doc("demo_accounts", self.user_id) or {}
            balance = doc.get("balance", {})
            usdt = balance.get("USDT", {"free": 0, "used": 0, "total": 0})
            usdt["free"] -= margin
            usdt["used"] = usdt.get("used", 0) + margin
            balance["USDT"] = usdt
            set_doc("demo_accounts", self.user_id, {"balance": balance}, merge=True)
        except Exception as exc:
            logger.error("Demo margin deduction failed: %s", exc)
