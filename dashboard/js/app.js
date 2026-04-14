/**
 * app.js — Main app state, real-time listeners, routing, helpers.
 */

import { db, auth } from './firebase-config.js';
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

// Safe imports for Firestore (may be stub in preview mode)
let _doc, _onSnapshot, _collection;
try {
  const fs = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js");
  _doc        = fs.doc;
  _onSnapshot = fs.onSnapshot;
  _collection = fs.collection;
} catch(e) {
  _doc = _onSnapshot = _collection = null;
}

// ─── Mock data for preview mode ───────────────────────────
const MOCK_SIGNALS = {
  BTC:    { spot_latest: { coin:'BTC', signal:'BUY',   confidence:87, entry_price:67200, stop_loss:65800, take_profit_1:69000, take_profit_2:71500, take_profit_3:74000, risk_reward:3.2, timeframe:'swing', timeframe_duration:'1-7 days', reasons:['Bullish divergence on 4H RSI','Whale accumulation detected','Social score above 80'], risks:['$69K resistance zone','Elevated funding rate'], generated_at: new Date().toISOString(), status:'active' }, futures_latest: { coin:'BTC', signal:'LONG', confidence:85, entry_price:67200, stop_loss:66500, take_profit_1:68500, take_profit_2:70000, take_profit_3:72000, recommended_leverage:5, margin_mode:'isolated', liquidation_price_at_leverage:53900, risk_reward:2.8, risk_reward_with_leverage:4.1, position_size_pct:10, timeframe_duration:'1-7 days', funding_rate_analysis:{rate_pct:0.012, sentiment:'positive'}, oi_analysis:{trend:'rising'}, reasons:['Strong support bounce at $66.8K','OI rising with price','Funding not extreme'], risks:['$69K resistance cluster','Potential reversal if $66K breaks'], generated_at: new Date().toISOString() } },
  ETH:    { spot_latest: { coin:'ETH', signal:'HOLD',  confidence:52, entry_price:3350, stop_loss:3200, take_profit_1:3500, take_profit_2:3650, take_profit_3:3800, risk_reward:2.0, timeframe:'swing', timeframe_duration:'1-7 days', reasons:['Neutral RSI at 50','Awaiting BTC direction'], risks:['$3,200 support test'], generated_at: new Date().toISOString(), status:'active' }, futures_latest: { coin:'ETH', signal:'SHORT', confidence:78, entry_price:3400, stop_loss:3520, take_profit_1:3250, take_profit_2:3100, take_profit_3:2950, recommended_leverage:3, margin_mode:'isolated', liquidation_price_at_leverage:4500, risk_reward:2.5, risk_reward_with_leverage:3.8, position_size_pct:8, timeframe_duration:'4h-2d', funding_rate_analysis:{rate_pct:0.025, sentiment:'positive'}, oi_analysis:{trend:'falling'}, reasons:['OI falling with price','High funding favours shorts','Key resistance at $3,400'], risks:['BTC pump could drag ETH up'], generated_at: new Date().toISOString() } },
  SOL:    { spot_latest: { coin:'SOL', signal:'BUY',   confidence:76, entry_price:178, stop_loss:168, take_profit_1:188, take_profit_2:198, take_profit_3:210, risk_reward:2.5, timeframe:'swing', timeframe_duration:'3-7 days', reasons:['Breakout from consolidation','Network activity increasing'], risks:['Crypto market correction risk'], generated_at: new Date().toISOString(), status:'active' }, futures_latest: { coin:'SOL', signal:'LONG', confidence:73, entry_price:178, stop_loss:172, take_profit_1:188, take_profit_2:198, take_profit_3:210, recommended_leverage:3, margin_mode:'isolated', liquidation_price_at_leverage:120, risk_reward:2.3, risk_reward_with_leverage:3.5, position_size_pct:7, timeframe_duration:'2-5 days', funding_rate_analysis:{rate_pct:-0.005, sentiment:'negative'}, oi_analysis:{trend:'rising'}, reasons:['Funding negative = bullish setup','OI rising = genuine buying'], risks:['Liquidity cluster above $185'], generated_at: new Date().toISOString() } },
  PI:     { spot_latest: { coin:'PI',   signal:'HOLD',  confidence:60, entry_price:42.5, stop_loss:38, take_profit_1:48, take_profit_2:55, take_profit_3:65, risk_reward:2.2, timeframe:'position', timeframe_duration:'1-4 weeks', reasons:['Not yet listed on major exchanges','Analysis only mode'], risks:['Exchange listing uncertainty'], generated_at: new Date().toISOString(), status:'active' } },
  GOLD:   { spot_latest: { coin:'GOLD', signal:'BUY',   confidence:79, entry_price:2380, stop_loss:2330, take_profit_1:2430, take_profit_2:2480, take_profit_3:2540, risk_reward:2.8, timeframe:'swing', timeframe_duration:'1-2 weeks', reasons:['USD weakening','Inflation hedge demand','Geopolitical risk premium'], risks:['Fed hawkish surprise'], generated_at: new Date().toISOString(), status:'active' } },
  SILVER: { spot_latest: { coin:'SILVER',signal:'HOLD', confidence:55, entry_price:31.2, stop_loss:29.5, take_profit_1:33, take_profit_2:35, take_profit_3:38, risk_reward:2.1, timeframe:'swing', timeframe_duration:'1-2 weeks', reasons:['Follows Gold with lag','Industrial demand steady'], risks:['Stronger USD risk'], generated_at: new Date().toISOString(), status:'active' } },
};

const MOCK_PRICES = {
  BTC:    { price:67200,  change_24h: 2.5,  high_24h:68100, low_24h:65900, volume_24h:28000000000 },
  ETH:    { price:3350,   change_24h: 1.8,  high_24h:3420,  low_24h:3280,  volume_24h:12000000000 },
  SOL:    { price:178.5,  change_24h:-0.3,  high_24h:182,   low_24h:175,   volume_24h:2500000000  },
  PI:     { price:42.50,  change_24h: 5.2,  high_24h:44,    low_24h:40,    volume_24h:500000000   },
  GOLD:   { price:2380,   change_24h: 0.1,  high_24h:2385,  low_24h:2370,  volume_24h:0           },
  SILVER: { price:31.20,  change_24h:-0.2,  high_24h:31.5,  low_24h:30.9,  volume_24h:0           },
};

const IS_PREVIEW = !(_doc && _onSnapshot);

// ─── App State ────────────────────────────────────────────
export const AppState = {
  mode:        localStorage.getItem('tradingMode') || 'live',
  user:        null,
  prices:      IS_PREVIEW ? { ...MOCK_PRICES }   : {},
  signals:     IS_PREVIEW ? { ...MOCK_SIGNALS }  : {},
  portfolio:   {},
  demoAccount: IS_PREVIEW ? {
    balance:          { USDT: { free: 8540, used: 1460, total: 10000 } },
    initial_balance:  10000,
    spot_positions:   [
      { id:'p1', coin:'BTC', side:'buy', entry_price:66800, current_price:67200, quantity:0.02, pnl_usdt:8.00, pnl_pct:0.60, stop_loss:65800, take_profit_1:69000, status:'open', type:'demo_spot' },
      { id:'p2', coin:'ETH', side:'buy', entry_price:3280,  current_price:3350,  quantity:0.5,  pnl_usdt:35.00,pnl_pct:2.13, stop_loss:3200,  take_profit_1:3500,  status:'open', type:'demo_spot' },
    ],
    futures_positions: [
      { id:'p3', coin:'SOL', symbol:'SOL/USDT', side:'long', entry_price:175, current_price:178.5, quantity:10, leverage:5, margin_used:350, notional_value:1750, liquidation_price:120, unrealized_pnl:35, unrealized_pnl_pct:10.0, stop_loss:172, take_profit_1:188, funding_paid:-0.80, status:'open', type:'demo_futures' },
    ],
    stats: { total_trades:47, winning_trades:30, losing_trades:17, win_rate:63.8, total_pnl_usdt:2340.5, total_pnl_pct:23.4, max_drawdown_pct:8.2, best_trade_pct:45.2, worst_trade_pct:-12.5 },
  } : {},
};

// ─── Mode Switcher ────────────────────────────────────────
export function setMode(mode) {
  AppState.mode = mode;
  localStorage.setItem('tradingMode', mode);
  document.querySelectorAll('.mode-badge').forEach(el => {
    el.classList.toggle('live', mode === 'live');
    el.classList.toggle('demo', mode === 'demo');
    const lbl = el.querySelector('.mode-label');
    if (lbl) lbl.textContent = mode === 'live' ? 'LIVE' : 'DEMO';
  });
  document.dispatchEvent(new CustomEvent('modeChanged', { detail: { mode } }));
  showToast(`Switched to ${mode === 'live' ? 'Live' : 'Demo'} mode`, 'info');
}

// ─── Toast Notifications ──────────────────────────────────
export function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type} fade-in`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ─── Real-time price listener ─────────────────────────────
const COINS = ['BTC', 'ETH', 'SOL', 'PI', 'GOLD', 'SILVER'];

export function startPriceListener() {
  if (IS_PREVIEW) {
    // Seed ticker with mock data immediately
    COINS.forEach(coin => updateTickerItem(coin, MOCK_PRICES[coin] || {}));
    return;
  }
  COINS.forEach(coin => {
    try {
      const docRef = _doc(db, 'market_data', coin);
      _onSnapshot(docRef, snap => {
        if (snap.exists()) {
          const data = snap.data().latest || {};
          AppState.prices[coin] = data;
          updateTickerItem(coin, data);
        }
      });
    } catch(e) { /* Firestore not ready */ }
  });
}

function updateTickerItem(coin, data) {
  const el = document.getElementById(`ticker-${coin}`);
  if (!el) return;
  const priceEl  = el.querySelector('.ticker-price');
  const changeEl = el.querySelector('.ticker-change');
  if (priceEl)  priceEl.textContent  = formatPrice(data.price, coin);
  if (changeEl) {
    const ch = data.change_24h || 0;
    changeEl.textContent  = `${ch >= 0 ? '+' : ''}${Number(ch).toFixed(2)}%`;
    changeEl.className    = `ticker-change ${ch >= 0 ? 'up' : 'down'}`;
  }
}

// ─── Signal listener ──────────────────────────────────────
export function startSignalListener(onUpdate) {
  if (IS_PREVIEW) {
    COINS.forEach(coin => {
      if (MOCK_SIGNALS[coin]) {
        AppState.signals[coin] = MOCK_SIGNALS[coin];
        if (onUpdate) onUpdate(coin, MOCK_SIGNALS[coin]);
      }
    });
    return;
  }
  COINS.forEach(coin => {
    try {
      const docRef = _doc(db, 'signals', coin);
      _onSnapshot(docRef, snap => {
        if (snap.exists()) {
          const data = snap.data();
          AppState.signals[coin] = data;
          if (onUpdate) onUpdate(coin, data);
        }
      });
    } catch(e) {}
  });
}

// ─── Portfolio listener ───────────────────────────────────
export function startPortfolioListener(uid, onUpdate) {
  if (!uid || IS_PREVIEW) return;
  try {
    const docRef = _doc(db, 'portfolio', uid);
    _onSnapshot(docRef, snap => {
      if (snap.exists()) {
        AppState.portfolio = snap.data();
        if (onUpdate) onUpdate(AppState.portfolio);
      }
    });
  } catch(e) {}
}

// ─── Demo account listener ────────────────────────────────
export function startDemoListener(uid, onUpdate) {
  if (!uid || IS_PREVIEW) return;
  try {
    const docRef = _doc(db, 'demo_accounts', uid);
    _onSnapshot(docRef, snap => {
      if (snap.exists()) {
        AppState.demoAccount = snap.data();
        if (onUpdate) onUpdate(AppState.demoAccount);
      }
    });
  } catch(e) {}
}

// ─── Auth ─────────────────────────────────────────────────
if (auth && auth.onAuthStateChanged) {
  onAuthStateChanged(auth, user => {
    AppState.user = user;
    document.dispatchEvent(new CustomEvent('authChanged', { detail: { user } }));
  });
}

// ─── Helpers ─────────────────────────────────────────────
export function formatPrice(price, coin) {
  if (price == null || price === 0) return '—';
  const n = Number(price);
  if (['GOLD', 'SILVER', 'BTC'].includes(coin) || n > 100) {
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;
}

export function formatPnl(pnl, includeSign = true) {
  const n    = Number(pnl) || 0;
  const sign = n >= 0 ? '+' : '';
  return `${includeSign ? sign : ''}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function timeAgo(isoString) {
  if (!isoString) return '—';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  startPriceListener();
  document.querySelectorAll('.mode-badge').forEach(badge => {
    badge.addEventListener('click', () => setMode(AppState.mode === 'live' ? 'demo' : 'live'));
  });
  if (IS_PREVIEW) {
    showToast('Preview mode — configure Firebase to connect live data', 'info', 6000);
  }
});
