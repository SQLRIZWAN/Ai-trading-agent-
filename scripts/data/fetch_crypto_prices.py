"""
fetch_crypto_prices.py
Fetches BTC, ETH, SOL, PI prices + OHLCV klines from CoinGecko & Binance.
Stores results in Firestore: market_data/{coin}/latest
Runs every 5 minutes via GitHub Actions.
"""

import sys
import time
from datetime import datetime, timezone

import requests

# Allow running from repo root
sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("fetch_crypto_prices")

# ─── Constants ───────────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
BINANCE_BASE = "https://api.binance.com/api/v3"
CMC_BASE = "https://pro-api.coinmarketcap.com/v1"

COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "PI": "pi-network",  # Update if listed under different ID
}

BINANCE_PAIRS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    # PI not yet on Binance — signals only
}

KLINE_INTERVALS = ["1h", "4h", "1d"]
KLINE_LIMIT = 100


# ─── CoinGecko ───────────────────────────────────────────────────────────────

def fetch_coingecko_prices() -> dict:
    """Fetch current prices, market caps, volumes, % changes."""
    ids = ",".join(COIN_IDS.values())
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ids,
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h,7d",
    }
    headers = {}
    if Config.COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = Config.COINGECKO_API_KEY

    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = {}
    for coin in data:
        symbol = coin["symbol"].upper()
        if symbol in COIN_IDS:
            result[symbol] = {
                "price": coin["current_price"],
                "market_cap": coin["market_cap"],
                "volume_24h": coin["total_volume"],
                "change_1h": coin.get("price_change_percentage_1h_in_currency", 0),
                "change_24h": coin.get("price_change_percentage_24h", 0),
                "change_7d": coin.get("price_change_percentage_7d_in_currency", 0),
                "high_24h": coin["high_24h"],
                "low_24h": coin["low_24h"],
                "ath": coin["ath"],
                "circulating_supply": coin["circulating_supply"],
            }
    return result


# ─── CoinMarketCap ───────────────────────────────────────────────────────────

def fetch_cmc_global() -> dict:
    """Fetch global metrics: BTC dominance, total market cap, fear/greed."""
    if not Config.COINMARKETCAP_API_KEY:
        return {}
    headers = {"X-CMC_PRO_API_KEY": Config.COINMARKETCAP_API_KEY}
    try:
        resp = requests.get(
            f"{CMC_BASE}/global-metrics/quotes/latest",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()["data"]
        return {
            "btc_dominance": d.get("btc_dominance", 0),
            "eth_dominance": d.get("eth_dominance", 0),
            "total_market_cap": d["quote"]["USD"]["total_market_cap"],
            "total_volume_24h": d["quote"]["USD"]["total_volume_24h"],
            "active_cryptocurrencies": d.get("active_cryptocurrencies", 0),
        }
    except Exception as exc:
        logger.warning("CMC global fetch failed: %s", exc)
        return {}


# ─── Binance Klines ──────────────────────────────────────────────────────────

def fetch_binance_klines(symbol: str, interval: str, limit: int = KLINE_LIMIT) -> list:
    """Fetch OHLCV klines from Binance."""
    url = f"{BINANCE_BASE}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        return [
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            }
            for k in raw
        ]
    except Exception as exc:
        logger.warning("Binance klines %s/%s failed: %s", symbol, interval, exc)
        return []


def fetch_binance_ticker(symbol: str) -> dict:
    """Fetch 24h ticker stats from Binance."""
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/ticker/24hr",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return {
            "price": float(d["lastPrice"]),
            "change_24h_pct": float(d["priceChangePercent"]),
            "high_24h": float(d["highPrice"]),
            "low_24h": float(d["lowPrice"]),
            "volume_24h": float(d["volume"]),
            "quote_volume_24h": float(d["quoteVolume"]),
        }
    except Exception as exc:
        logger.warning("Binance ticker %s failed: %s", symbol, exc)
        return {}


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    logger.info("=== fetch_crypto_prices START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    cg_prices = fetch_coingecko_prices()
    global_metrics = fetch_cmc_global()

    for coin, cg_data in cg_prices.items():
        doc = {**cg_data, "updated_at": now_iso, "source": "coingecko"}

        # Enrich with Binance data if available
        pair = BINANCE_PAIRS.get(coin)
        if pair:
            ticker = fetch_binance_ticker(pair)
            if ticker:
                doc["price"] = ticker["price"]  # Binance is more real-time
                doc["binance_ticker"] = ticker

            klines = {}
            for interval in KLINE_INTERVALS:
                klines[interval] = fetch_binance_klines(pair, interval)
                time.sleep(0.2)  # Be gentle on rate limits
            doc["klines"] = klines

        doc["global_metrics"] = global_metrics

        set_doc("market_data", coin, {"latest": doc})
        logger.info("Stored %s: $%s", coin, doc.get("price", "N/A"))

    log_to_firestore(db, "INFO", "fetch_crypto_prices", "Prices updated", {"coins": list(cg_prices.keys())})
    logger.info("=== fetch_crypto_prices DONE ===")


if __name__ == "__main__":
    run()
