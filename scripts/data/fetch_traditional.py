"""
fetch_traditional.py
Fetches Gold (XAU/USD) and Silver (XAG/USD) prices from Alpha Vantage.
Stores in Firestore: market_data/GOLD/latest, market_data/SILVER/latest
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("fetch_traditional")

AV_BASE = "https://www.alphavantage.co/query"

COMMODITIES = {
    "GOLD": "XAU",
    "SILVER": "XAG",
}

FOREX_SYMBOLS = {
    "GOLD": ("XAU", "USD"),
    "SILVER": ("XAG", "USD"),
}


def fetch_av_forex(from_symbol: str, to_symbol: str) -> dict:
    """Fetch real-time exchange rate via Alpha Vantage CURRENCY_EXCHANGE_RATE."""
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_symbol,
        "to_currency": to_symbol,
        "apikey": Config.ALPHA_VANTAGE_API_KEY,
    }
    resp = requests.get(AV_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("Realtime Currency Exchange Rate", {})
    return {
        "price": float(data.get("5. Exchange Rate", 0)),
        "bid": float(data.get("8. Bid Price", 0)),
        "ask": float(data.get("9. Ask Price", 0)),
        "last_refreshed": data.get("6. Last Refreshed", ""),
        "timezone": data.get("7. Time Zone", "UTC"),
    }


def fetch_av_daily(symbol: str) -> list:
    """Fetch daily OHLCV for commodities (FX_DAILY)."""
    params = {
        "function": "FX_DAILY",
        "from_symbol": symbol,
        "to_symbol": "USD",
        "outputsize": "compact",
        "apikey": Config.ALPHA_VANTAGE_API_KEY,
    }
    try:
        resp = requests.get(AV_BASE, params=params, timeout=15)
        resp.raise_for_status()
        series = resp.json().get("Time Series FX (Daily)", {})
        result = []
        for date, ohlcv in list(series.items())[:30]:
            result.append({
                "date": date,
                "open": float(ohlcv["1. open"]),
                "high": float(ohlcv["2. high"]),
                "low": float(ohlcv["3. low"]),
                "close": float(ohlcv["4. close"]),
            })
        return result
    except Exception as exc:
        logger.warning("AV daily %s failed: %s", symbol, exc)
        return []


def run():
    logger.info("=== fetch_traditional START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    if not Config.ALPHA_VANTAGE_API_KEY:
        logger.warning("ALPHA_VANTAGE_API_KEY not set — skipping traditional assets")
        return

    for asset, (from_sym, to_sym) in FOREX_SYMBOLS.items():
        try:
            rate = fetch_av_forex(from_sym, to_sym)
            daily = fetch_av_daily(from_sym)

            doc = {
                "price": rate["price"],
                "bid": rate["bid"],
                "ask": rate["ask"],
                "daily_klines": daily,
                "updated_at": now_iso,
                "source": "alpha_vantage",
                "asset_type": "commodity",
            }
            set_doc("market_data", asset, {"latest": doc})
            logger.info("Stored %s: $%s", asset, doc["price"])
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", asset, exc)

    log_to_firestore(db, "INFO", "fetch_traditional", "Traditional assets updated")
    logger.info("=== fetch_traditional DONE ===")


if __name__ == "__main__":
    run()
