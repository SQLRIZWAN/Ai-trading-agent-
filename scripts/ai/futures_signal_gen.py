"""
futures_signal_gen.py — Futures signal generation for BTC, ETH, SOL.
Generates LONG/SHORT signals with leverage recommendations.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.ai.gemini_analyzer import GeminiAnalyzer
from scripts.alerts.telegram_bot import TelegramBot
from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc, add_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("futures_signal_gen")

FUTURES_ASSETS = ["BTC", "ETH", "SOL"]


def run():
    logger.info("=== futures_signal_gen START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    analyzer = GeminiAnalyzer()
    telegram = TelegramBot()

    for coin in FUTURES_ASSETS:
        logger.info("Analyzing %s (futures)...", coin)
        try:
            signal_data = analyzer.analyze_futures(coin)
            if not signal_data:
                logger.warning("%s: No futures signal from Gemini", coin)
                continue

            confidence = signal_data.get("confidence", 0)
            signal = signal_data.get("signal", "NO_TRADE")

            signal_data["generated_at"] = now_iso
            signal_data["signal_type"] = "futures"
            signal_data["status"] = "active" if confidence >= 70 else "low_confidence"

            set_doc("signals", coin, {"futures_latest": signal_data})
            add_doc(f"signals/{coin}/futures_history", signal_data)

            logger.info(
                "%s futures signal: %s (conf=%s%% lev=%sx)",
                coin, signal, confidence,
                signal_data.get("recommended_leverage", "?")
            )

            if confidence >= 70 and signal in ("LONG", "SHORT"):
                telegram.send_futures_signal(signal_data)

        except Exception as exc:
            logger.error("Futures signal failed for %s: %s", coin, exc)
            log_to_firestore(db, "ERROR", "futures_signal_gen", f"{coin} failed: {exc}")

    log_to_firestore(db, "INFO", "futures_signal_gen", "Futures signals generated")
    logger.info("=== futures_signal_gen DONE ===")


if __name__ == "__main__":
    run()
