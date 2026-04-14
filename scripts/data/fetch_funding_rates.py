"""
fetch_funding_rates.py
Fetches futures funding rates, open interest, and long/short ratios.
Stores in Firestore: market_data/{coin}/futures_data
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.firebase_client import set_doc
from scripts.utils.logger import get_logger

logger = get_logger("fetch_funding_rates")

BINANCE_FUTURES_BASE = "https://fapi.binance.com/fapi/v1"

FUTURES_PAIRS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}


def fetch_funding_rate(symbol: str) -> dict:
    """Current + next funding rate."""
    try:
        resp = requests.get(
            f"{BINANCE_FUTURES_BASE}/premiumIndex",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        rate = float(d.get("lastFundingRate", 0))
        return {
            "funding_rate": rate,
            "funding_rate_pct": round(rate * 100, 4),
            "funding_sentiment": "positive" if rate > 0 else ("negative" if rate < 0 else "neutral"),
            "funding_extreme": abs(rate) > 0.001,  # >0.1% is considered extreme
            "next_funding_time": d.get("nextFundingTime", 0),
            "mark_price": float(d.get("markPrice", 0)),
            "index_price": float(d.get("indexPrice", 0)),
        }
    except Exception as exc:
        logger.warning("Funding rate %s failed: %s", symbol, exc)
        return {}


def fetch_open_interest(symbol: str) -> dict:
    """Current open interest."""
    try:
        resp = requests.get(
            f"{BINANCE_FUTURES_BASE}/openInterest",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return {
            "open_interest": float(d.get("openInterest", 0)),
            "open_interest_value": float(d.get("openInterest", 0)),
        }
    except Exception as exc:
        logger.warning("Open interest %s failed: %s", symbol, exc)
        return {}


def fetch_open_interest_hist(symbol: str) -> list:
    """Historical OI over last 24 hours."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/futures/data/openInterestHist",
            params={"symbol": symbol, "period": "1h", "limit": 24},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "timestamp": int(d["timestamp"]),
                "sum_open_interest": float(d["sumOpenInterest"]),
                "sum_open_interest_value": float(d["sumOpenInterestValue"]),
            }
            for d in data
        ]
    except Exception as exc:
        logger.warning("OI hist %s failed: %s", symbol, exc)
        return []


def fetch_long_short_ratio(symbol: str) -> dict:
    """Global long/short account ratio."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": "1h", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            d = data[-1]
            ratio = float(d.get("longShortRatio", 1))
            return {
                "long_account_ratio": float(d.get("longAccount", 0)),
                "short_account_ratio": float(d.get("shortAccount", 0)),
                "long_short_ratio": ratio,
                "sentiment": "long_heavy" if ratio > 1.3 else ("short_heavy" if ratio < 0.7 else "balanced"),
            }
        return {}
    except Exception as exc:
        logger.warning("Long/Short ratio %s failed: %s", symbol, exc)
        return {}


def fetch_liquidations(symbol: str) -> dict:
    """Recent liquidation stats (approximation via OI change)."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": "1h", "limit": 24},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            buy_vol = sum(float(d.get("buyVol", 0)) for d in data)
            sell_vol = sum(float(d.get("sellVol", 0)) for d in data)
            return {
                "taker_buy_vol_24h": buy_vol,
                "taker_sell_vol_24h": sell_vol,
                "taker_ratio": round(buy_vol / sell_vol, 3) if sell_vol else 0,
            }
        return {}
    except Exception as exc:
        logger.warning("Liquidations %s failed: %s", symbol, exc)
        return {}


def run():
    logger.info("=== fetch_funding_rates START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    for coin, pair in FUTURES_PAIRS.items():
        funding = fetch_funding_rate(pair)
        oi = fetch_open_interest(pair)
        oi_hist = fetch_open_interest_hist(pair)
        ls_ratio = fetch_long_short_ratio(pair)
        liq = fetch_liquidations(pair)

        # Determine OI trend
        oi_trend = "flat"
        if len(oi_hist) >= 6:
            recent_oi = sum(d["sum_open_interest"] for d in oi_hist[-3:]) / 3
            older_oi = sum(d["sum_open_interest"] for d in oi_hist[:3]) / 3
            if recent_oi > older_oi * 1.02:
                oi_trend = "rising"
            elif recent_oi < older_oi * 0.98:
                oi_trend = "falling"

        doc = {
            "funding": funding,
            "open_interest": {**oi, "trend": oi_trend, "history_24h": oi_hist[-12:]},
            "long_short": ls_ratio,
            "liquidations": liq,
            "updated_at": now_iso,
        }
        set_doc("market_data", coin, {"futures_data": doc})
        logger.info(
            "%s futures: funding=%.4f%% OI_trend=%s LS=%.2f",
            coin,
            funding.get("funding_rate_pct", 0),
            oi_trend,
            ls_ratio.get("long_short_ratio", 1),
        )

    logger.info("=== fetch_funding_rates DONE ===")


if __name__ == "__main__":
    run()
