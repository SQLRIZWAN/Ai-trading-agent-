"""
futures_manager.py — Futures position management.
Handles leverage, margin modes, liquidation monitoring, partial closes, and funding.
Run with --mode monitor to check all open futures positions.
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
from scripts.utils.encryption import decrypt
from scripts.utils.firebase_client import db, get_collection, get_doc, set_doc, update_doc
from scripts.utils.logger import get_logger

logger = get_logger("futures_manager")

MARGIN_WARNING_THRESHOLD = 80  # % — alert when margin ratio exceeds this
AUTO_CLOSE_LOSS_THRESHOLD = 0.50  # 50% of margin lost → auto close


class FuturesManager:
    def __init__(self):
        self.telegram = TelegramBot()

    def monitor_all_users(self):
        """Check all users' open futures positions."""
        logger.info("Monitoring futures positions for all users...")

        users = get_collection("users")
        for user in users:
            uid = user.get("id")
            settings = user.get("trading_settings", {})

            if not settings.get("futures_enabled"):
                continue

            try:
                self._monitor_user(uid, user)
            except Exception as exc:
                logger.error("Monitor failed for user %s: %s", uid, exc)

    def _monitor_user(self, uid: str, user: dict):
        exchanges = user.get("exchanges", [])
        for ex in exchanges:
            if not ex.get("futures_enabled"):
                continue

            connector = self._build_connector(ex, uid, "futures")
            if not connector:
                continue

            positions = connector.get_positions()
            for pos in positions:
                if float(pos.get("contracts", 0)) == 0:
                    continue

                symbol = pos.get("symbol", "")
                coin = symbol.replace("/USDT:USDT", "").replace("/USDT", "")
                unrealized_pnl = float(pos.get("unrealizedPnl", 0))
                margin_used = float(pos.get("initialMargin", 1))
                margin_ratio = abs(unrealized_pnl / margin_used * 100) if unrealized_pnl < 0 else 0
                liq_price = float(pos.get("liquidationPrice", 0))

                logger.info(
                    "%s %s: PnL=%.2f margin_ratio=%.1f%% liq=$%.2f",
                    uid, symbol, unrealized_pnl, margin_ratio, liq_price
                )

                # Margin warning
                if margin_ratio >= MARGIN_WARNING_THRESHOLD:
                    self.telegram.send_margin_warning(coin, margin_ratio, liq_price)
                    logger.warning("MARGIN WARNING %s: ratio=%.1f%%", symbol, margin_ratio)

                # Auto-close if loss >= 50% of margin
                if unrealized_pnl < 0 and abs(unrealized_pnl) >= margin_used * AUTO_CLOSE_LOSS_THRESHOLD:
                    logger.warning("AUTO-CLOSE triggered for %s (loss=%s%%)", symbol, round(margin_ratio, 1))
                    self._emergency_close(connector, pos, uid)

    def _emergency_close(self, connector: ExchangeConnector, pos: dict, uid: str):
        symbol = pos.get("symbol")
        side = pos.get("side")
        contracts = float(pos.get("contracts", 0))
        # To close a LONG → place SELL; to close SHORT → place BUY
        close_side = "sell" if side == "long" else "buy"
        result = connector.place_futures_order(
            symbol, close_side, contracts, reduce_only=True
        )
        logger.info("Emergency close result: %s", result)

    def _build_connector(self, ex_config: dict, uid: str, mode: str) -> ExchangeConnector | None:
        try:
            enc_key = ex_config.get("api_key_enc", "")
            enc_secret = ex_config.get("api_secret_enc", "")
            password = Config.ENCRYPTION_KEY

            api_key = decrypt(enc_key, password) if enc_key else None
            api_secret = decrypt(enc_secret, password) if enc_secret else None
            passphrase = ex_config.get("passphrase")  # KuCoin/Bitget require this

            return ExchangeConnector(
                exchange_name=ex_config.get("exchange", "binance"),
                api_key=api_key,
                secret_key=api_secret,
                passphrase=passphrase,
                trading_mode=mode,
                user_id=uid,
            )
        except Exception as exc:
            logger.error("Failed to build connector for %s: %s", uid, exc)
            return None


def run_monitor():
    logger.info("=== futures_manager MONITOR START ===")
    mgr = FuturesManager()
    mgr.monitor_all_users()
    logger.info("=== futures_manager MONITOR DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["monitor"], default="monitor")
    args = parser.parse_args()

    if args.mode == "monitor":
        run_monitor()
