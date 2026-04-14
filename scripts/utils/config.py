"""
config.py — Environment configuration loader
Loads all secrets/env vars from GitHub Actions secrets or .env file.
"""

import os


class Config:
    # ─── Firebase ───────────────────────────────────────────────────────────
    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
    FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
    FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL", "")

    # ─── Market Data APIs ───────────────────────────────────────────────────
    COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")
    BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
    COINMARKETCAP_API_KEY = os.environ.get("COINMARKETCAP_API_KEY", "")
    ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")

    # ─── On-Chain APIs ──────────────────────────────────────────────────────
    ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
    BSCSCAN_API_KEY = os.environ.get("BSCSCAN_API_KEY", "")
    SOLSCAN_API_KEY = os.environ.get("SOLSCAN_API_KEY", "")
    MORALIS_API_KEY = os.environ.get("MORALIS_API_KEY", "")

    # ─── Sentiment APIs ─────────────────────────────────────────────────────
    LUNARCRUSH_API_KEY = os.environ.get("LUNARCRUSH_API_KEY", "")
    CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
    SANTIMENT_API_KEY = os.environ.get("SANTIMENT_API_KEY", "")

    # ─── AI ─────────────────────────────────────────────────────────────────
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    # ─── Telegram ───────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # ─── Trading ────────────────────────────────────────────────────────────
    MIN_SIGNAL_CONFIDENCE = float(os.environ.get("MIN_SIGNAL_CONFIDENCE", "75"))
    MIN_LIVE_CONFIDENCE = float(os.environ.get("MIN_LIVE_CONFIDENCE", "80"))
    MIN_DEMO_CONFIDENCE = float(os.environ.get("MIN_DEMO_CONFIDENCE", "70"))
    MAX_RISK_PER_TRADE_PCT = float(os.environ.get("MAX_RISK_PER_TRADE_PCT", "2"))
    MAX_DAILY_TRADES = int(os.environ.get("MAX_DAILY_TRADES", "10"))
    DEMO_INITIAL_BALANCE = float(os.environ.get("DEMO_INITIAL_BALANCE", "10000"))

    # ─── Assets ─────────────────────────────────────────────────────────────
    CRYPTO_ASSETS = ["BTC", "ETH", "SOL", "PI"]
    TRADITIONAL_ASSETS = ["GOLD", "SILVER"]
    ALL_ASSETS = CRYPTO_ASSETS + TRADITIONAL_ASSETS

    # ─── Encryption ─────────────────────────────────────────────────────────
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

    @classmethod
    def validate(cls):
        """Raise if critical configs are missing."""
        required = [
            ("FIREBASE_PROJECT_ID", cls.FIREBASE_PROJECT_ID),
            ("GEMINI_API_KEY", cls.GEMINI_API_KEY),
        ]
        missing = [name for name, val in required if not val]
        if missing:
            raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
