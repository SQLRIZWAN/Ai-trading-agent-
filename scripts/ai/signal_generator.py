"""
signal_generator.py — Spot signal generation for all assets.
Runs Gemini AI analysis, applies confidence filter, stores signals to Firestore,
and sends Telegram alerts.
"""

import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from scripts.ai.gemini_analyzer import GeminiAnalyzer
from scripts.alerts.telegram_bot import TelegramBot
from scripts.utils.config import Config
from scripts.utils.firebase_client import db, get_doc, set_doc, add_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("signal_generator")

ASSETS = Config.CRYPTO_ASSETS + Config.TRADITIONAL_ASSETS


def run():
    logger.info("=== signal_generator (SPOT) START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    analyzer = GeminiAnalyzer()
    telegram = TelegramBot()
    min_confidence = Config.MIN_SIGNAL_CONFIDENCE

    for coin in ASSETS:
        logger.info("Analyzing %s (spot)...", coin)
        try:
            signal_data = analyzer.analyze_spot(coin)
            if not signal_data:
                logger.warning("%s: No signal returned from Gemini", coin)
                continue

            confidence = signal_data.get("confidence", 0)
            signal = signal_data.get("signal", "HOLD")

            # Enrich with metadata
            signal_data["generated_at"] = now_iso
            signal_data["signal_type"] = "spot"
            signal_data["status"] = "active" if confidence >= min_confidence else "low_confidence"

            # Store latest signal
            set_doc("signals", coin, {"spot_latest": signal_data})

            # Store in history
            add_doc(f"signals/{coin}/spot_history", signal_data)

            logger.info(
                "%s spot signal: %s (conf=%s%%) status=%s",
                coin, signal, confidence, signal_data["status"]
            )

            # Send Telegram alert only for high-confidence actionable signals
            if confidence >= min_confidence and signal in ("BUY", "SELL"):
                telegram.send_spot_signal(signal_data)

        except Exception as exc:
            logger.error("Signal generation failed for %s: %s", coin, exc)
            log_to_firestore(db, "ERROR", "signal_generator", f"{coin} failed: {exc}")

    log_to_firestore(db, "INFO", "signal_generator", "Spot signals generated", {"assets": ASSETS})
    logger.info("=== signal_generator DONE ===")


if __name__ == "__main__":
    run()
