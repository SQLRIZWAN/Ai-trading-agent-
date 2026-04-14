"""
fetch_onchain_data.py
Fetches on-chain metrics from Etherscan, BscScan, Solscan, and Moralis.
Stores in Firestore: onchain_data/{chain}/latest
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("fetch_onchain_data")

ETHERSCAN_BASE = "https://api.etherscan.io/api"
BSCSCAN_BASE = "https://api.bscscan.com/api"
SOLSCAN_BASE = "https://public-api.solscan.io"
MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"

WHALE_THRESHOLD_ETH = 500       # ETH transfer threshold for whale tracking
WHALE_THRESHOLD_BNB = 5000      # BNB transfer threshold
WHALE_THRESHOLD_SOL = 100_000   # SOL transfer threshold


# ─── Etherscan ───────────────────────────────────────────────────────────────

def fetch_eth_gas() -> dict:
    """Current Ethereum gas prices in Gwei."""
    try:
        resp = requests.get(ETHERSCAN_BASE, params={
            "module": "gastracker",
            "action": "gasoracle",
            "apikey": Config.ETHERSCAN_API_KEY,
        }, timeout=10)
        resp.raise_for_status()
        r = resp.json().get("result", {})
        return {
            "safe_gas": int(r.get("SafeGasPrice", 0)),
            "propose_gas": int(r.get("ProposeGasPrice", 0)),
            "fast_gas": int(r.get("FastGasPrice", 0)),
            "base_fee": float(r.get("suggestBaseFee", 0)),
        }
    except Exception as exc:
        logger.warning("ETH gas fetch failed: %s", exc)
        return {}


def fetch_eth_stats() -> dict:
    """ETH supply stats."""
    try:
        resp = requests.get(ETHERSCAN_BASE, params={
            "module": "stats",
            "action": "ethsupply2",
            "apikey": Config.ETHERSCAN_API_KEY,
        }, timeout=10)
        resp.raise_for_status()
        r = resp.json().get("result", {})
        return {
            "eth_supply": int(r.get("EthSupply", 0)),
            "eth2_staking": int(r.get("Eth2Staking", 0)),
            "burnt_fees": int(r.get("BurntFees", 0)),
        }
    except Exception as exc:
        logger.warning("ETH stats fetch failed: %s", exc)
        return {}


def fetch_eth_whale_txns() -> list:
    """Recent large ETH transfers."""
    try:
        resp = requests.get(ETHERSCAN_BASE, params={
            "module": "account",
            "action": "txlist",
            "address": "0x00000000219ab540356cbb839cbe05303d7705fa",  # ETH2 deposit contract
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 20,
            "sort": "desc",
            "apikey": Config.ETHERSCAN_API_KEY,
        }, timeout=10)
        resp.raise_for_status()
        txns = resp.json().get("result", [])
        whales = []
        for tx in txns[:10]:
            value_eth = int(tx.get("value", 0)) / 1e18
            if value_eth >= WHALE_THRESHOLD_ETH:
                whales.append({
                    "hash": tx["hash"],
                    "from": tx["from"],
                    "to": tx["to"],
                    "value_eth": round(value_eth, 4),
                    "timestamp": int(tx["timeStamp"]),
                })
        return whales
    except Exception as exc:
        logger.warning("ETH whale txns failed: %s", exc)
        return []


# ─── BscScan ─────────────────────────────────────────────────────────────────

def fetch_bsc_stats() -> dict:
    """BSC network stats."""
    try:
        resp = requests.get(BSCSCAN_BASE, params={
            "module": "stats",
            "action": "bnbsupply",
            "apikey": Config.BSCSCAN_API_KEY,
        }, timeout=10)
        resp.raise_for_status()
        return {"bnb_supply": resp.json().get("result", "0")}
    except Exception as exc:
        logger.warning("BSC stats failed: %s", exc)
        return {}


# ─── Solscan ─────────────────────────────────────────────────────────────────

def fetch_sol_stats() -> dict:
    """Solana network stats from Solscan."""
    try:
        headers = {}
        if Config.SOLSCAN_API_KEY:
            headers["token"] = Config.SOLSCAN_API_KEY
        resp = requests.get(
            f"{SOLSCAN_BASE}/chaininfo",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json().get("data", {})
        return {
            "block_height": d.get("blockHeight", 0),
            "current_epoch": d.get("currentEpoch", 0),
            "absolute_slot": d.get("absoluteSlot", 0),
            "transaction_count": d.get("transactionCount", 0),
        }
    except Exception as exc:
        logger.warning("Solscan stats failed: %s", exc)
        return {}


# ─── Moralis ─────────────────────────────────────────────────────────────────

def fetch_moralis_token_price(address: str, chain: str = "eth") -> dict:
    """Get token price via Moralis."""
    if not Config.MORALIS_API_KEY:
        return {}
    try:
        headers = {"X-API-Key": Config.MORALIS_API_KEY}
        resp = requests.get(
            f"{MORALIS_BASE}/erc20/{address}/price",
            params={"chain": chain},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return {
            "price_usd": d.get("usdPrice", 0),
            "price_change_24h": d.get("24hrPercentChange", 0),
        }
    except Exception as exc:
        logger.warning("Moralis price fetch failed: %s", exc)
        return {}


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    logger.info("=== fetch_onchain_data START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Ethereum
    eth_doc = {
        "gas": fetch_eth_gas(),
        "stats": fetch_eth_stats(),
        "whale_txns": fetch_eth_whale_txns(),
        "updated_at": now_iso,
    }
    set_doc("onchain_data", "ETH", {"latest": eth_doc})
    logger.info("ETH on-chain stored: gas=%s", eth_doc["gas"].get("fast_gas"))

    # BSC
    bsc_doc = {
        "stats": fetch_bsc_stats(),
        "updated_at": now_iso,
    }
    set_doc("onchain_data", "BNB", {"latest": bsc_doc})
    logger.info("BSC on-chain stored")

    # Solana
    sol_doc = {
        "stats": fetch_sol_stats(),
        "updated_at": now_iso,
    }
    set_doc("onchain_data", "SOL", {"latest": sol_doc})
    logger.info("SOL on-chain stored: height=%s", sol_doc["stats"].get("block_height"))

    log_to_firestore(db, "INFO", "fetch_onchain_data", "On-chain data updated")
    logger.info("=== fetch_onchain_data DONE ===")


if __name__ == "__main__":
    run()
