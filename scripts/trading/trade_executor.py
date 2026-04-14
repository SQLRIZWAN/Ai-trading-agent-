"""
trade_executor.py — Auto-execute live trades (spot + futures) for all users.
Reads latest signals, validates confidence, checks user settings, places orders.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.ai.risk_calculator import RiskCalculator
from scripts.alerts.telegram_bot import TelegramBot
from scripts.trading.exchange_connector import ExchangeConnector
from scripts.trading.order_manager import OrderManager
from scripts.utils.config import Config
from scripts.utils.encryption import decrypt
from scripts.utils.firebase_client import db, get_collection, get_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("trade_executor")

ASSETS = ["BTC", "ETH", "SOL"]
PAIR_MAP = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
}


def run():
    logger.info("=== trade_executor START ===")
    telegram = TelegramBot()
    users = get_collection("users")

    for user in users:
        uid = user.get("id")
        settings = user.get("trading_settings", {})

        if not settings.get("auto_trade_enabled"):
            continue

        spot_enabled = settings.get("spot_enabled", False)
        futures_enabled = settings.get("futures_enabled", False)

        if not (spot_enabled or futures_enabled):
            continue

        logger.info("Processing user %s (spot=%s futures=%s)", uid, spot_enabled, futures_enabled)

        # Get user's portfolio to check balance and daily PnL
        portfolio = get_doc("portfolio", uid) or {}
        daily_pnl_pct = portfolio.get("daily_pnl_pct", 0)
        account_balance = portfolio.get("total_balance_usdt", 1000)

        risk_calc = RiskCalculator(account_balance)
        dd_check = risk_calc.check_daily_drawdown(daily_pnl_pct)

        if not dd_check["can_trade"]:
            logger.warning("User %s: %s", uid, dd_check["reason"])
            telegram.send_system_alert(f"User {uid}: {dd_check['reason']}")
            continue

        size_mult = dd_check.get("size_multiplier", 1.0)

        # Get current open positions for correlation check
        open_trades = get_doc(f"portfolio/{uid}/summary", "open_trades") or {"positions": []}
        open_positions = open_trades.get("positions", [])

        exchanges = user.get("exchanges", [])

        for ex_config in exchanges:
            try:
                _execute_for_exchange(
                    uid, ex_config, settings, risk_calc, size_mult,
                    open_positions, spot_enabled, futures_enabled
                )
            except Exception as exc:
                logger.error("Exchange execution failed for user %s: %s", uid, exc)
                log_to_firestore(db, "ERROR", "trade_executor", f"User {uid}: {exc}")

    logger.info("=== trade_executor DONE ===")


def _execute_for_exchange(
    uid, ex_config, settings, risk_calc, size_mult,
    open_positions, spot_enabled, futures_enabled
):
    exchange_name = ex_config.get("exchange", "binance")
    enc_key = ex_config.get("api_key_enc", "")
    enc_secret = ex_config.get("api_secret_enc", "")

    if not enc_key or not enc_secret:
        return

    api_key = decrypt(enc_key, Config.ENCRYPTION_KEY)
    api_secret = decrypt(enc_secret, Config.ENCRYPTION_KEY)
    passphrase = ex_config.get("passphrase")

    for coin in ASSETS:
        symbol = PAIR_MAP.get(coin)
        if not symbol:
            continue

        # ── Spot trading ──────────────────────────────────────────────────
        if spot_enabled and ex_config.get("spot_enabled"):
            signal_doc = get_doc("signals", coin) or {}
            signal = signal_doc.get("spot_latest", {})
            sig = signal.get("signal", "HOLD")
            confidence = signal.get("confidence", 0)

            if sig in ("BUY", "SELL") and confidence >= Config.MIN_LIVE_CONFIDENCE:
                side = "buy" if sig == "BUY" else "sell"
                entry = signal.get("entry_price", 0)
                sl = signal.get("stop_loss", 0)

                if not entry or not sl:
                    continue

                corr = risk_calc.check_correlation(coin, side, open_positions)
                if corr["correlated"]:
                    logger.warning("Correlation conflict for %s %s — skipping", coin, side)
                    continue

                sizing = risk_calc.calc_position_size(entry, sl, risk_calc.max_risk_pct * size_mult)
                amount = sizing["units"]

                connector = ExchangeConnector(
                    exchange_name, api_key, api_secret,
                    passphrase, "spot", uid
                )
                mgr = OrderManager(connector, uid)
                mgr.open_trade(
                    coin=coin,
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profits=[
                        signal.get("take_profit_1"),
                        signal.get("take_profit_2"),
                        signal.get("take_profit_3"),
                    ],
                    is_futures=False,
                    signal=signal,
                )

        # ── Futures trading ───────────────────────────────────────────────
        if futures_enabled and ex_config.get("futures_enabled"):
            signal_doc = get_doc("signals", coin) or {}
            signal = signal_doc.get("futures_latest", {})
            sig = signal.get("signal", "NO_TRADE")
            confidence = signal.get("confidence", 0)

            if sig in ("LONG", "SHORT") and confidence >= Config.MIN_LIVE_CONFIDENCE:
                side = "buy" if sig == "LONG" else "sell"
                entry = signal.get("entry_price", 0)
                sl = signal.get("stop_loss", 0)
                leverage = min(
                    signal.get("recommended_leverage", 5),
                    ex_config.get("max_leverage", 10),
                )
                margin_mode = signal.get("margin_mode", "isolated")

                if not entry or not sl:
                    continue

                sizing = risk_calc.calc_futures_position(entry, sl, leverage, risk_calc.max_risk_pct * size_mult)
                amount = sizing["units"]

                connector = ExchangeConnector(
                    exchange_name, api_key, api_secret,
                    passphrase, "futures", uid
                )
                mgr = OrderManager(connector, uid)
                mgr.open_trade(
                    coin=coin,
                    symbol=f"{symbol}:USDT",
                    side=side,
                    amount=amount,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profits=[
                        signal.get("take_profit_1"),
                        signal.get("take_profit_2"),
                        signal.get("take_profit_3"),
                    ],
                    leverage=leverage,
                    is_futures=True,
                    margin_mode=margin_mode,
                    signal=signal,
                )


if __name__ == "__main__":
    run()
