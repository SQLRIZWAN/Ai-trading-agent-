"""
fetch_orderbook.py
Fetches order-book depth snapshots from Binance/Bitget.
Stores bid/ask walls in Firestore: market_data/{coin}/orderbook
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import set_doc
from scripts.utils.logger import get_logger

logger = get_logger("fetch_orderbook")

BINANCE_BASE = "https://api.binance.com/api/v3"

PAIRS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}

DEPTH_LIMIT = 20  # Top 20 bid/ask levels


def fetch_orderbook(symbol: str) -> dict:
    """Fetch L2 order book from Binance."""
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/depth",
            params={"symbol": symbol, "limit": DEPTH_LIMIT},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()

        bids = [{"price": float(b[0]), "qty": float(b[1])} for b in raw["bids"]]
        asks = [{"price": float(a[0]), "qty": float(a[1])} for a in raw["asks"]]

        total_bid_qty = sum(b["qty"] for b in bids)
        total_ask_qty = sum(a["qty"] for a in asks)
        bid_ask_ratio = round(total_bid_qty / total_ask_qty, 3) if total_ask_qty else 0

        # Detect large walls (top 3 size outliers)
        bid_wall = sorted(bids, key=lambda x: x["qty"], reverse=True)[:3]
        ask_wall = sorted(asks, key=lambda x: x["qty"], reverse=True)[:3]

        return {
            "bids": bids,
            "asks": asks,
            "bid_ask_ratio": bid_ask_ratio,
            "bid_wall": bid_wall,
            "ask_wall": ask_wall,
            "spread": round(asks[0]["price"] - bids[0]["price"], 4) if bids and asks else 0,
            "mid_price": round((asks[0]["price"] + bids[0]["price"]) / 2, 2) if bids and asks else 0,
            "last_update_id": raw.get("lastUpdateId", 0),
        }
    except Exception as exc:
        logger.warning("Orderbook %s failed: %s", symbol, exc)
        return {}


def run():
    logger.info("=== fetch_orderbook START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    for coin, pair in PAIRS.items():
        ob = fetch_orderbook(pair)
        if ob:
            ob["updated_at"] = now_iso
            set_doc("market_data", coin, {"orderbook": ob})
            logger.info(
                "%s orderbook: spread=%.4f bid/ask=%.3f",
                coin, ob["spread"], ob["bid_ask_ratio"],
            )

    logger.info("=== fetch_orderbook DONE ===")


if __name__ == "__main__":
    run()
