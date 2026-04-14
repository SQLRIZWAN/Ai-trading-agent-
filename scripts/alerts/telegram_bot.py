"""
telegram_bot.py — Send trading signals and alerts via Telegram Bot API.
"""

import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")

from scripts.utils.config import Config
from scripts.utils.logger import get_logger

logger = get_logger("telegram_bot")

TELEGRAM_API = "https://api.telegram.org"


class TelegramBot:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or Config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or Config.TELEGRAM_CHAT_ID
        self._base = f"{TELEGRAM_API}/bot{self.token}"

    def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token or not self.chat_id:
            logger.warning("Telegram not configured — skipping alert")
            return False
        try:
            resp = requests.post(
                f"{self._base}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            resp.raise_for_status()
            logger.info("Telegram message sent")
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    # ─── Signal formatters ────────────────────────────────────────────────

    def send_spot_signal(self, signal: dict) -> bool:
        coin = signal.get("coin", "?")
        sig = signal.get("signal", "HOLD")
        conf = signal.get("confidence", 0)
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        tp3 = signal.get("take_profit_3", 0)
        rr = signal.get("risk_reward", 0)
        tf = signal.get("timeframe_duration", "")
        reasons = signal.get("reasons", [])
        risks = signal.get("risks", [])

        # Emoji
        if sig == "BUY":
            emoji = "🟢"
            direction = "BUY"
        elif sig == "SELL":
            emoji = "🔴"
            direction = "SELL"
        else:
            emoji = "⚪"
            direction = "HOLD"

        sl_pct = round((sl - entry) / entry * 100, 2) if entry else 0
        tp1_pct = round((tp1 - entry) / entry * 100, 2) if entry else 0
        tp2_pct = round((tp2 - entry) / entry * 100, 2) if entry else 0
        tp3_pct = round((tp3 - entry) / entry * 100, 2) if entry else 0

        reasons_text = "\n".join(f"• {r}" for r in reasons[:3])
        risks_text = "\n".join(f"• {r}" for r in risks[:3])
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        msg = (
            f"{emoji} <b>{direction} SIGNAL — {coin}/USDT (SPOT)</b>\n\n"
            f"📊 Confidence: <b>{conf}%</b>\n"
            f"💰 Entry: <b>${entry:,.2f}</b>\n"
            f"🛑 Stop Loss: <b>${sl:,.2f}</b> ({sl_pct:+.1f}%)\n"
            f"🎯 TP1: <b>${tp1:,.2f}</b> ({tp1_pct:+.1f}%)\n"
            f"🎯 TP2: <b>${tp2:,.2f}</b> ({tp2_pct:+.1f}%)\n"
            f"🎯 TP3: <b>${tp3:,.2f}</b> ({tp3_pct:+.1f}%)\n"
            f"⚖️ R:R Ratio: <b>{rr:.1f}</b>\n\n"
            f"📈 Timeframe: {tf}\n\n"
            f"<b>Reasons:</b>\n{reasons_text}\n\n"
            f"<b>⚠️ Risks:</b>\n{risks_text}\n\n"
            f"🤖 AI Agent | Spot Signal | {now}"
        )
        return self._send(msg)

    def send_futures_signal(self, signal: dict) -> bool:
        coin = signal.get("coin", "?")
        sig = signal.get("signal", "NO_TRADE")
        conf = signal.get("confidence", 0)
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        tp3 = signal.get("take_profit_3", 0)
        lev = signal.get("recommended_leverage", 1)
        margin_mode = signal.get("margin_mode", "isolated")
        rr = signal.get("risk_reward_with_leverage", signal.get("risk_reward", 0))
        liq = signal.get("liquidation_price_at_leverage", 0)
        tf = signal.get("timeframe_duration", "")
        funding = signal.get("funding_rate_analysis", {})
        oi = signal.get("oi_analysis", {})
        ls = signal.get("ls_ratio", "N/A")
        reasons = signal.get("reasons", [])
        risks = signal.get("risks", [])

        if sig == "LONG":
            emoji = "🟢"
        elif sig == "SHORT":
            emoji = "🔴"
        else:
            return False  # Don't send NO_TRADE

        sl_pct = round((sl - entry) / entry * 100, 2) if entry else 0
        tp1_pct = round((tp1 - entry) / entry * 100, 2) if entry else 0
        tp2_pct = round((tp2 - entry) / entry * 100, 2) if entry else 0
        tp3_pct = round((tp3 - entry) / entry * 100, 2) if entry else 0

        reasons_text = "\n".join(f"• {r}" for r in reasons[:3])
        risks_text = "\n".join(f"• {r}" for r in risks[:3])
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        fr_pct = funding.get("rate_pct", 0)
        oi_trend = oi.get("trend", "?")

        msg = (
            f"{emoji} <b>{sig} SIGNAL — {coin}/USDT (FUTURES)</b>\n\n"
            f"📊 Confidence: <b>{conf}%</b>\n"
            f"⚡ Leverage: <b>{lev}x</b> ({margin_mode.capitalize()})\n"
            f"💰 Entry: <b>${entry:,.2f}</b>\n"
            f"🛑 Stop Loss: <b>${sl:,.2f}</b> ({sl_pct:+.2f}%)\n"
            f"🎯 TP1: <b>${tp1:,.2f}</b> ({tp1_pct:+.2f}%) — Close 25%\n"
            f"🎯 TP2: <b>${tp2:,.2f}</b> ({tp2_pct:+.2f}%) — Close 50%\n"
            f"🎯 TP3: <b>${tp3:,.2f}</b> ({tp3_pct:+.2f}%) — Close 25%\n"
            f"⚖️ R:R Ratio: <b>{rr:.1f}</b> (with leverage)\n"
            f"💀 Liquidation: <b>${liq:,.2f}</b>\n\n"
            f"📊 <b>Futures Data:</b>\n"
            f"• Funding Rate: {fr_pct:+.4f}%\n"
            f"• Open Interest: {'▲ Rising' if oi_trend == 'rising' else ('▼ Falling' if oi_trend == 'falling' else '→ Flat')}\n\n"
            f"📈 Timeframe: {tf}\n\n"
            f"<b>Reasons:</b>\n{reasons_text}\n\n"
            f"<b>⚠️ Risks:</b>\n{risks_text}\n\n"
            f"🤖 AI Agent | Futures Signal | {now}"
        )
        return self._send(msg)

    def send_trade_executed(self, trade: dict) -> bool:
        """Alert when a trade is executed (live or demo)."""
        coin = trade.get("coin", "?")
        mode = trade.get("trading_mode", "spot")
        side = trade.get("side", "buy").upper()
        entry = trade.get("entry_price", 0)
        sl = trade.get("stop_loss", 0)
        tp1 = trade.get("take_profit_1", 0)
        lev = trade.get("leverage", 1)
        margin = trade.get("margin_used", 0)
        is_demo = trade.get("is_demo", False)
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        mode_emoji = "🧪" if is_demo else "💵"
        mode_label = f"Demo {mode.title()}" if is_demo else f"Live {mode.title()}"
        lev_str = f" {lev}x" if lev > 1 else ""

        msg = (
            f"{mode_emoji} <b>TRADE EXECUTED — {coin}/USDT</b>\n\n"
            f"Mode: <b>{mode_label}{lev_str}</b>\n"
            f"💰 Entry: <b>${entry:,.2f}</b>\n"
            f"📦 Margin: <b>${margin:,.2f}</b>\n"
            f"🛑 SL: ${sl:,.2f} | 🎯 TP1: ${tp1:,.2f}\n\n"
            f"🤖 AI Agent | {now}"
        )
        return self._send(msg)

    def send_trade_closed(self, trade: dict) -> bool:
        """Alert when a trade is closed with PnL."""
        coin = trade.get("coin", "?")
        pnl = trade.get("pnl_usdt", 0)
        pnl_pct = trade.get("pnl_percent", 0)
        close_reason = trade.get("close_reason", "manual")
        is_demo = trade.get("is_demo", False)
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        mode_label = "Demo" if is_demo else "Live"

        msg = (
            f"{pnl_emoji} <b>TRADE CLOSED — {coin}/USDT ({mode_label})</b>\n\n"
            f"PnL: <b>${pnl:+,.2f}</b> ({pnl_pct:+.2f}%)\n"
            f"Reason: {close_reason}\n\n"
            f"🤖 AI Agent | {now}"
        )
        return self._send(msg)

    def send_daily_summary(self, stats: dict) -> bool:
        """Daily midnight summary."""
        live_pnl = stats.get("live_pnl_usd", 0)
        demo_pnl = stats.get("demo_pnl_usd", 0)
        live_win_rate = stats.get("live_win_rate", 0)
        total_signals = stats.get("total_signals", 0)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d UTC")

        live_emoji = "🟢" if live_pnl >= 0 else "🔴"
        demo_emoji = "🟢" if demo_pnl >= 0 else "🔴"

        msg = (
            f"📊 <b>Daily Summary — {now}</b>\n\n"
            f"{live_emoji} Live PnL: <b>${live_pnl:+,.2f}</b>\n"
            f"{demo_emoji} Demo PnL: <b>${demo_pnl:+,.2f}</b>\n"
            f"📈 Signals today: {total_signals}\n"
            f"🏆 Live Win Rate: {live_win_rate:.1f}%\n\n"
            f"🤖 AI Trading Agent"
        )
        return self._send(msg)

    def send_margin_warning(self, coin: str, margin_ratio: float, liq_price: float) -> bool:
        msg = (
            f"⚠️ <b>MARGIN WARNING — {coin}/USDT</b>\n\n"
            f"Margin Ratio: <b>{margin_ratio:.1f}%</b> (>80% danger zone)\n"
            f"Liquidation Price: <b>${liq_price:,.2f}</b>\n\n"
            f"Consider reducing position or adding margin.\n\n"
            f"🤖 AI Agent | {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        return self._send(msg)

    def send_system_alert(self, message: str) -> bool:
        return self._send(f"🚨 <b>System Alert</b>\n\n{message}")
