"""
position_manager.py — Track open positions, update PnL, handle auto-close.
Runs every 30 minutes to refresh all portfolio data for all users.
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.alerts.telegram_bot import TelegramBot
from scripts.utils.config import Config
from scripts.utils.encryption import decrypt
from scripts.utils.firebase_client import db, get_collection, get_doc, set_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("position_manager")

BINANCE_BASE = "https://api.binance.com/api/v3"

PAIR_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}


def get_live_prices() -> dict:
    """Fetch all relevant prices in one batch call."""
    prices = {}
    symbols = list(PAIR_MAP.values())
    try:
        resp = requests.get(f"{BINANCE_BASE}/ticker/price", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for item in data:
            sym = item["symbol"]
            for coin, pair in PAIR_MAP.items():
                if sym == pair:
                    prices[coin] = float(item["price"])
    except Exception as exc:
        logger.warning("Live price fetch failed: %s", exc)
    return prices


def run():
    logger.info("=== position_manager START ===")
    telegram = TelegramBot()
    prices = get_live_prices()

    users = get_collection("users")
    for user in users:
        uid = user.get("id")
        try:
            _update_user_portfolio(uid, user, prices, telegram)
        except Exception as exc:
            logger.error("Portfolio update failed for user %s: %s", uid, exc)

    log_to_firestore(db, "INFO", "position_manager", "Portfolio updated")
    logger.info("=== position_manager DONE ===")


def _update_user_portfolio(uid: str, user: dict, prices: dict, telegram: TelegramBot):
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Live trades ───────────────────────────────────────────────────────
    live_trades_col = get_collection(f"trades/{uid}/live_history")
    open_live = [t for t in live_trades_col if t.get("status") == "open"]

    total_live_pnl = 0
    for trade in open_live:
        coin = trade.get("coin")
        price = prices.get(coin)
        if not price:
            continue

        entry = trade.get("entry_price", price)
        side = trade.get("side")
        qty = trade.get("quantity", 0)
        is_futures = trade.get("is_futures", False)
        leverage = trade.get("leverage", 1)

        if side == "buy":
            pnl = (price - entry) * qty
        else:
            pnl = (entry - price) * qty

        pnl_pct = (pnl / (entry * qty) * 100) if entry and qty else 0
        total_live_pnl += pnl

        # Update trade doc
        trade_id = trade.get("id")
        if trade_id:
            set_doc(f"trades/{uid}/live_history", trade_id, {
                "current_price": price,
                "pnl_usdt": round(pnl, 4),
                "pnl_percent": round(pnl_pct, 2),
            }, merge=True)

    # ── Demo account positions ────────────────────────────────────────────
    demo_acc = get_doc("demo_accounts", uid)
    total_demo_pnl = 0

    if demo_acc:
        # Update spot positions PnL
        spot_positions = demo_acc.get("spot_positions", [])
        for pos in spot_positions:
            if pos.get("status") != "open":
                continue
            coin = pos.get("coin")
            price = prices.get(coin)
            if price:
                qty = pos.get("quantity", 0)
                entry = pos.get("entry_price", price)
                side = pos.get("side")
                pnl = (price - entry) * qty if side == "buy" else (entry - price) * qty
                pos["current_price"] = price
                pos["pnl_usdt"] = round(pnl, 4)
                pos["pnl_pct"] = round(pnl / (entry * qty) * 100, 2) if entry and qty else 0
                total_demo_pnl += pnl

        # Update futures positions PnL
        fut_positions = demo_acc.get("futures_positions", [])
        for pos in fut_positions:
            if pos.get("status") != "open":
                continue
            coin = pos.get("coin")
            price = prices.get(coin)
            if price:
                qty = pos.get("quantity", 0)
                entry = pos.get("entry_price", price)
                side = pos.get("side")
                margin = pos.get("margin_used", 1)
                pnl = (price - entry) * qty if side == "long" else (entry - price) * qty
                pos["current_price"] = price
                pos["unrealized_pnl"] = round(pnl, 4)
                pos["unrealized_pnl_pct"] = round(pnl / margin * 100, 2) if margin else 0
                total_demo_pnl += pnl

        # Persist updated positions
        set_doc("demo_accounts", uid, {
            "spot_positions": spot_positions,
            "futures_positions": fut_positions,
            "last_updated": now_iso,
        }, merge=True)

    # ── Portfolio summary ─────────────────────────────────────────────────
    demo_balance = demo_acc.get("balance", {}).get("USDT", {}).get("total", 0) if demo_acc else 0
    demo_initial = demo_acc.get("initial_balance", Config.DEMO_INITIAL_BALANCE) if demo_acc else Config.DEMO_INITIAL_BALANCE
    demo_pnl_pct = ((demo_balance - demo_initial) / demo_initial * 100) if demo_initial else 0

    portfolio_summary = {
        "live_pnl_usdt": round(total_live_pnl, 2),
        "demo_pnl_usdt": round(total_demo_pnl, 2),
        "demo_balance": round(demo_balance, 2),
        "demo_pnl_pct": round(demo_pnl_pct, 2),
        "open_live_trades": len(open_live),
        "open_demo_spot": len([p for p in (demo_acc or {}).get("spot_positions", []) if p.get("status") == "open"]),
        "open_demo_futures": len([p for p in (demo_acc or {}).get("futures_positions", []) if p.get("status") == "open"]),
        "updated_at": now_iso,
    }
    set_doc("portfolio", uid, portfolio_summary, merge=True)

    logger.info(
        "Portfolio %s: live_pnl=$%.2f demo_pnl=$%.2f",
        uid, total_live_pnl, total_demo_pnl
    )


if __name__ == "__main__":
    run()
