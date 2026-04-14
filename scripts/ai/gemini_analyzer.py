"""
gemini_analyzer.py — Core AI brain using Google Gemini.
Reads market/on-chain/sentiment data from Firestore and generates
structured trading signals via the Gemini API.
"""

import json
import sys
import time
from pathlib import Path
from typing import Literal

import google.generativeai as genai

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.firebase_client import get_doc
from scripts.utils.logger import get_logger

logger = get_logger("gemini_analyzer")

PROMPTS_DIR = Path("scripts/ai/prompts")


class GeminiAnalyzer:
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        logger.info("Gemini model loaded: %s", Config.GEMINI_MODEL)

    # ─── Prompt template loading ──────────────────────────────────────────

    def _load_prompt(self, filename: str) -> str:
        return (PROMPTS_DIR / filename).read_text()

    # ─── Data fetchers from Firestore ─────────────────────────────────────

    def _get_market_data(self, coin: str) -> dict:
        doc = get_doc("market_data", coin) or {}
        return doc.get("latest", {})

    def _get_onchain_data(self, coin: str) -> dict:
        chain_map = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL"}
        chain = chain_map.get(coin, coin)
        doc = get_doc("onchain_data", chain) or {}
        return doc.get("latest", {})

    def _get_sentiment(self, coin: str) -> dict:
        doc = get_doc("sentiment", coin) or {}
        return doc.get("latest", {})

    def _get_futures_data(self, coin: str) -> dict:
        doc = get_doc("market_data", coin) or {}
        return doc.get("futures_data", {})

    def _get_global_metrics(self) -> dict:
        btc = get_doc("market_data", "BTC") or {}
        return btc.get("latest", {}).get("global_metrics", {})

    # ─── Technical indicator computation ─────────────────────────────────

    def _compute_technicals(self, klines: list, interval: str = "1h") -> dict:
        """Compute RSI, MACD, BB, EMA from klines array."""
        if not klines or len(klines) < 20:
            return {}

        closes = [k["close"] for k in klines]

        # RSI-14
        rsi = self._rsi(closes, 14)

        # EMA 20/50/200
        ema20 = self._ema(closes, 20)
        ema50 = self._ema(closes, 50) if len(closes) >= 50 else None
        ema200 = self._ema(closes, 200) if len(closes) >= 200 else None

        # MACD (12, 26, 9)
        macd_line, signal_line, histogram = self._macd(closes)

        # Bollinger Bands (20, 2)
        bb_upper, bb_mid, bb_lower = self._bollinger(closes, 20, 2)

        current_price = closes[-1]
        ema_trend = "neutral"
        if ema200:
            ema_trend = "above_200" if current_price > ema200 else "below_200"

        bb_pos = "middle"
        if bb_upper and bb_lower:
            if current_price >= bb_upper:
                bb_pos = "upper_band"
            elif current_price <= bb_lower:
                bb_pos = "lower_band"

        macd_sig = "neutral"
        if macd_line and signal_line:
            if macd_line > signal_line and histogram > 0:
                macd_sig = "bullish_cross"
            elif macd_line < signal_line and histogram < 0:
                macd_sig = "bearish_cross"

        return {
            "interval": interval,
            "rsi_14": round(rsi, 2) if rsi else None,
            "ema_20": round(ema20, 4) if ema20 else None,
            "ema_50": round(ema50, 4) if ema50 else None,
            "ema_200": round(ema200, 4) if ema200 else None,
            "ema_trend": ema_trend,
            "macd_line": round(macd_line, 4) if macd_line else None,
            "macd_signal": round(signal_line, 4) if signal_line else None,
            "macd_histogram": round(histogram, 4) if histogram else None,
            "macd_interpretation": macd_sig,
            "bb_upper": round(bb_upper, 4) if bb_upper else None,
            "bb_middle": round(bb_mid, 4) if bb_mid else None,
            "bb_lower": round(bb_lower, 4) if bb_lower else None,
            "bb_position": bb_pos,
            "current_price": current_price,
        }

    @staticmethod
    def _rsi(closes: list, period: int = 14) -> float | None:
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _ema(closes: list, period: int) -> float | None:
        if len(closes) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    @staticmethod
    def _macd(closes: list) -> tuple:
        if len(closes) < 26:
            return None, None, None
        k12 = 2 / 13
        k26 = 2 / 27
        k9 = 2 / 10

        ema12 = sum(closes[:12]) / 12
        for p in closes[12:]:
            ema12 = p * k12 + ema12 * (1 - k12)

        ema26 = sum(closes[:26]) / 26
        for p in closes[26:]:
            ema26 = p * k26 + ema26 * (1 - k26)

        macd_line = ema12 - ema26

        # Signal line: 9-period EMA of MACD (approximate with last value)
        signal_line = macd_line * k9 + macd_line * (1 - k9)  # simplified
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def _bollinger(closes: list, period: int = 20, std_dev: float = 2) -> tuple:
        if len(closes) < period:
            return None, None, None
        window = closes[-period:]
        mid = sum(window) / period
        variance = sum((x - mid) ** 2 for x in window) / period
        std = variance ** 0.5
        return mid + std_dev * std, mid, mid - std_dev * std

    # ─── Main analysis methods ────────────────────────────────────────────

    def analyze_spot(self, coin: str) -> dict | None:
        """Run Gemini analysis for spot signal."""
        market = self._get_market_data(coin)
        onchain = self._get_onchain_data(coin)
        sentiment = self._get_sentiment(coin)
        global_metrics = self._get_global_metrics()

        klines_1h = market.get("klines", {}).get("1h", [])
        klines_4h = market.get("klines", {}).get("4h", [])
        technicals_1h = self._compute_technicals(klines_1h, "1h")
        technicals_4h = self._compute_technicals(klines_4h, "4h")

        template = self._load_prompt("spot_signal.txt")
        prompt = template.replace("{COIN}", coin).replace(
            "{PRICE_DATA}", json.dumps({
                "current_price": market.get("price"),
                "change_24h": market.get("change_24h"),
                "change_7d": market.get("change_7d"),
                "high_24h": market.get("high_24h"),
                "low_24h": market.get("low_24h"),
                "volume_24h": market.get("volume_24h"),
            }, indent=2)
        ).replace(
            "{TECHNICAL_INDICATORS}", json.dumps({
                "1h": technicals_1h,
                "4h": technicals_4h,
            }, indent=2)
        ).replace(
            "{ONCHAIN_DATA}", json.dumps(onchain, indent=2)
        ).replace(
            "{SENTIMENT_DATA}", json.dumps({
                "aggregate_score": sentiment.get("aggregate_score"),
                "label": sentiment.get("sentiment_label"),
                "lunarcrush_galaxy": sentiment.get("lunarcrush", {}).get("galaxy_score"),
                "recent_news_count": len(sentiment.get("recent_news", [])),
            }, indent=2)
        ).replace(
            "{GLOBAL_METRICS}", json.dumps(global_metrics, indent=2)
        )

        return self._call_gemini(coin, "spot", prompt)

    def analyze_futures(self, coin: str) -> dict | None:
        """Run Gemini analysis for futures signal."""
        market = self._get_market_data(coin)
        onchain = self._get_onchain_data(coin)
        sentiment = self._get_sentiment(coin)
        futures = self._get_futures_data(coin)
        global_metrics = self._get_global_metrics()

        klines_1h = market.get("klines", {}).get("1h", [])
        klines_4h = market.get("klines", {}).get("4h", [])
        technicals = self._compute_technicals(klines_4h or klines_1h, "4h")

        funding_data = futures.get("funding", {})
        oi_data = futures.get("open_interest", {})
        ls_data = futures.get("long_short", {})
        liq_data = futures.get("liquidations", {})

        template = self._load_prompt("futures_signal.txt")
        prompt = template.replace("{COIN}", coin).replace(
            "{PRICE_DATA}", json.dumps({
                "current_price": market.get("price"),
                "change_24h": market.get("change_24h"),
                "high_24h": market.get("high_24h"),
                "low_24h": market.get("low_24h"),
                "volume_24h": market.get("volume_24h"),
            }, indent=2)
        ).replace(
            "{TECHNICAL_INDICATORS}", json.dumps(technicals, indent=2)
        ).replace(
            "{ONCHAIN_DATA}", json.dumps(onchain, indent=2)
        ).replace(
            "{SENTIMENT_DATA}", json.dumps(sentiment.get("lunarcrush", {}), indent=2)
        ).replace(
            "{FUTURES_DATA}", json.dumps(futures, indent=2)
        ).replace(
            "{OI_TREND}", oi_data.get("trend", "unknown")
        ).replace(
            "{FUNDING_RATE}", str(funding_data.get("funding_rate", 0))
        ).replace(
            "{FUNDING_PCT}", str(funding_data.get("funding_rate_pct", 0))
        ).replace(
            "{LS_RATIO}", str(ls_data.get("long_short_ratio", 1))
        ).replace(
            "{TAKER_RATIO}", str(liq_data.get("taker_ratio", 1))
        ).replace(
            "{GLOBAL_METRICS}", json.dumps(global_metrics, indent=2)
        )

        return self._call_gemini(coin, "futures", prompt)

    def _call_gemini(self, coin: str, signal_type: str, prompt: str) -> dict | None:
        """Send prompt to Gemini and parse JSON response."""
        for attempt in range(3):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                raw = response.text.strip()
                # Strip markdown fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                result = json.loads(raw)
                logger.info(
                    "Gemini %s %s signal: %s (confidence: %s%%)",
                    signal_type, coin,
                    result.get("signal"), result.get("confidence"),
                )
                return result
            except json.JSONDecodeError as exc:
                logger.warning("Gemini JSON parse error attempt %d: %s", attempt + 1, exc)
            except Exception as exc:
                logger.warning("Gemini API error attempt %d: %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        logger.error("Gemini failed after 3 attempts for %s %s", coin, signal_type)
        return None
