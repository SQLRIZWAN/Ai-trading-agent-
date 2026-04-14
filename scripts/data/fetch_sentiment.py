"""
fetch_sentiment.py
Fetches social/sentiment data from LunarCrush, CryptoPanic, and Santiment.
Computes an aggregated sentiment score (0–100) per coin.
Stores in Firestore: sentiment/{coin}/latest
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import db, set_doc
from scripts.utils.logger import get_logger, log_to_firestore

logger = get_logger("fetch_sentiment")

LUNARCRUSH_BASE = "https://lunarcrush.com/api4/public"
CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1"
SANTIMENT_BASE = "https://api.santiment.net/graphql"

COIN_SLUGS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "PI": "pi-network",
    "GOLD": None,
    "SILVER": None,
}

COIN_CURRENCIES = {
    "BTC": "BTC",
    "ETH": "ETH",
    "SOL": "SOL",
}


# ─── LunarCrush ──────────────────────────────────────────────────────────────

def fetch_lunarcrush(symbol: str) -> dict:
    """Galaxy Score, social volume, sentiment from LunarCrush."""
    if not Config.LUNARCRUSH_API_KEY:
        return {}
    try:
        headers = {"Authorization": f"Bearer {Config.LUNARCRUSH_API_KEY}"}
        resp = requests.get(
            f"{LUNARCRUSH_BASE}/coins/{symbol}/v1",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json().get("data", {})
        return {
            "galaxy_score": d.get("galaxy_score", 0),
            "alt_rank": d.get("alt_rank", 0),
            "social_volume_24h": d.get("social_volume_24h", 0),
            "social_score": d.get("social_score", 0),
            "social_contributors": d.get("social_contributors", 0),
            "sentiment": d.get("sentiment", 0),
            "bullish_sentiment": d.get("bullish_sentiment", 0),
            "bearish_sentiment": d.get("bearish_sentiment", 0),
        }
    except Exception as exc:
        logger.warning("LunarCrush %s failed: %s", symbol, exc)
        return {}


# ─── CryptoPanic ─────────────────────────────────────────────────────────────

def fetch_cryptopanic(currencies: str) -> list:
    """Latest news headlines with sentiment tags."""
    if not Config.CRYPTOPANIC_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{CRYPTOPANIC_BASE}/posts/",
            params={
                "auth_token": Config.CRYPTOPANIC_API_KEY,
                "currencies": currencies,
                "filter": "hot",
                "public": "true",
                "kind": "news",
            },
            timeout=15,
        )
        resp.raise_for_status()
        posts = resp.json().get("results", [])
        result = []
        for p in posts[:10]:
            result.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "published_at": p.get("published_at", ""),
                "sentiment": _parse_sentiment(p),
                "votes": p.get("votes", {}),
            })
        return result
    except Exception as exc:
        logger.warning("CryptoPanic %s failed: %s", currencies, exc)
        return []


def _parse_sentiment(post: dict) -> str:
    """Determine sentiment from post metadata."""
    votes = post.get("votes", {})
    bullish = votes.get("bullish", 0) + votes.get("liked", 0)
    bearish = votes.get("bearish", 0) + votes.get("disliked", 0)
    if bullish > bearish * 1.5:
        return "bullish"
    if bearish > bullish * 1.5:
        return "bearish"
    return "neutral"


# ─── Santiment ───────────────────────────────────────────────────────────────

def fetch_santiment_social_volume(slug: str) -> dict:
    """Social volume and dev activity from Santiment GraphQL API."""
    if not Config.SANTIMENT_API_KEY or not slug:
        return {}
    query = """
    {
      socialVolume(slug: "%s", from: "utc_now-1d", to: "utc_now", interval: "1d",
                   socialVolumeType: TELEGRAM_CHATS_OVERVIEW) {
        datetime
        value
      }
      devActivity(slug: "%s", from: "utc_now-30d", to: "utc_now", interval: "1d") {
        datetime
        value
      }
    }
    """ % (slug, slug)
    try:
        resp = requests.post(
            SANTIMENT_BASE,
            json={"query": query},
            headers={"Authorization": f"Apikey {Config.SANTIMENT_API_KEY}"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        sv = data.get("socialVolume", [])
        da = data.get("devActivity", [])
        return {
            "social_volume_24h": sv[-1]["value"] if sv else 0,
            "dev_activity_30d": sum(d["value"] for d in da),
        }
    except Exception as exc:
        logger.warning("Santiment %s failed: %s", slug, exc)
        return {}


# ─── Aggregate ───────────────────────────────────────────────────────────────

def compute_aggregate_score(lc: dict, news: list, san: dict) -> int:
    """
    Weighted sentiment score 0–100.
    LunarCrush galaxy_score contributes 50%, news 30%, Santiment 20%.
    """
    score = 50  # neutral default

    # LunarCrush — galaxy_score is already 0-100
    if lc:
        galaxy = lc.get("galaxy_score", 50)
        sentiment_ratio = lc.get("bullish_sentiment", 50) / 100.0
        lc_score = galaxy * 0.6 + sentiment_ratio * 100 * 0.4
        score = score * 0.0 + lc_score * 0.5 + 50 * 0.5  # blend

    # News sentiment
    if news:
        bullish_count = sum(1 for n in news if n["sentiment"] == "bullish")
        bearish_count = sum(1 for n in news if n["sentiment"] == "bearish")
        total = len(news)
        if total:
            news_score = ((bullish_count - bearish_count) / total) * 50 + 50
            score = score * 0.7 + news_score * 0.3

    return max(0, min(100, int(score)))


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    logger.info("=== fetch_sentiment START ===")
    now_iso = datetime.now(timezone.utc).isoformat()

    for coin in ["BTC", "ETH", "SOL"]:
        slug = COIN_SLUGS.get(coin)
        symbol = COIN_CURRENCIES.get(coin, coin)

        lc = fetch_lunarcrush(symbol)
        news = fetch_cryptopanic(symbol)
        san = fetch_santiment_social_volume(slug) if slug else {}
        agg_score = compute_aggregate_score(lc, news, san)

        doc = {
            "aggregate_score": agg_score,
            "lunarcrush": lc,
            "recent_news": news[:5],
            "santiment": san,
            "sentiment_label": "bullish" if agg_score > 60 else ("bearish" if agg_score < 40 else "neutral"),
            "updated_at": now_iso,
        }
        set_doc("sentiment", coin, {"latest": doc})
        logger.info("Sentiment %s: score=%s (%s)", coin, agg_score, doc["sentiment_label"])

    log_to_firestore(db, "INFO", "fetch_sentiment", "Sentiment data updated")
    logger.info("=== fetch_sentiment DONE ===")


if __name__ == "__main__":
    run()
