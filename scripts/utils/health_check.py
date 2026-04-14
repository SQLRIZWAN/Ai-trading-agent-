"""
health_check.py — Verifies all critical APIs are reachable.
Sends Telegram alert if any service is down.
"""

import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc
from scripts.utils.logger import get_logger

logger = get_logger("health_check")

CHECKS = {
    "CoinGecko": "https://api.coingecko.com/api/v3/ping",
    "Binance": "https://api.binance.com/api/v3/ping",
    "Binance Futures": "https://fapi.binance.com/fapi/v1/ping",
    "Alpha Vantage": f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey={Config.ALPHA_VANTAGE_API_KEY}",
}


def check_api(name: str, url: str) -> dict:
    start = time.time()
    try:
        resp = requests.get(url, timeout=10)
        latency = round((time.time() - start) * 1000, 1)
        status = "ok" if resp.status_code < 400 else "error"
        return {"name": name, "status": status, "latency_ms": latency, "http_code": resp.status_code}
    except Exception as exc:
        return {"name": name, "status": "down", "error": str(exc), "latency_ms": -1}


def check_firebase() -> dict:
    start = time.time()
    try:
        db.collection("_health").document("ping").set({"ts": time.time()})
        latency = round((time.time() - start) * 1000, 1)
        return {"name": "Firebase", "status": "ok", "latency_ms": latency}
    except Exception as exc:
        return {"name": "Firebase", "status": "down", "error": str(exc)}


def send_telegram_alert(message: str):
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": Config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def run():
    logger.info("=== health_check START ===")
    now_iso = datetime.now(timezone.utc).isoformat()
    results = []

    for name, url in CHECKS.items():
        result = check_api(name, url)
        results.append(result)
        icon = "✅" if result["status"] == "ok" else "❌"
        logger.info("%s %s: %s (%sms)", icon, name, result["status"], result.get("latency_ms"))

    fb = check_firebase()
    results.append(fb)

    down_services = [r["name"] for r in results if r["status"] != "ok"]

    health_doc = {
        "checks": results,
        "all_ok": len(down_services) == 0,
        "down_services": down_services,
        "checked_at": now_iso,
    }
    set_doc("system", "health", health_doc)

    if down_services:
        msg = f"⚠️ <b>AI Trading Agent — Health Alert</b>\n\nDown services:\n" + "\n".join(f"• {s}" for s in down_services)
        send_telegram_alert(msg)
        logger.warning("DOWN services: %s", down_services)
    else:
        logger.info("All systems operational")

    logger.info("=== health_check DONE ===")


if __name__ == "__main__":
    run()
