/**
 * app.js — Main app logic, mode switcher, router, and real-time listeners.
 */

import { db, auth } from './firebase-config.js';
import {
  collection, doc, onSnapshot, getDoc, setDoc, query, limit, orderBy
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

// ─── App State ────────────────────────────────────────────
export const AppState = {
  mode: localStorage.getItem('tradingMode') || 'live', // 'live' | 'demo'
  user: null,
  prices: {},
  signals: {},
  portfolio: {},
  demoAccount: {},
};

// ─── Mode Switcher ────────────────────────────────────────
export function setMode(mode) {
  AppState.mode = mode;
  localStorage.setItem('tradingMode', mode);
  document.querySelectorAll('.mode-badge').forEach(el => {
    el.classList.toggle('live', mode === 'live');
    el.classList.toggle('demo', mode === 'demo');
    el.querySelector('.mode-label').textContent = mode === 'live' ? 'LIVE' : 'DEMO';
  });
  document.dispatchEvent(new CustomEvent('modeChanged', { detail: { mode } }));
  showToast(`Switched to ${mode === 'live' ? 'Live' : 'Demo'} mode`, 'info');
}

// ─── Toast Notifications ─────────────────────────────────
export function showToast(message, type = 'info', duration = 3000) {
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
  COINS.forEach(coin => {
    const docRef = doc(db, 'market_data', coin);
    onSnapshot(docRef, snap => {
      if (snap.exists()) {
        const data = snap.data().latest || {};
        AppState.prices[coin] = data;
        updateTickerItem(coin, data);
      }
    });
  });
}

function updateTickerItem(coin, data) {
  const el = document.getElementById(`ticker-${coin}`);
  if (!el) return;
  const priceEl = el.querySelector('.ticker-price');
  const changeEl = el.querySelector('.ticker-change');
  if (priceEl) priceEl.textContent = formatPrice(data.price, coin);
  if (changeEl) {
    const ch = data.change_24h || 0;
    changeEl.textContent = `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%`;
    changeEl.className = `ticker-change ${ch >= 0 ? 'up' : 'down'}`;
  }
}

// ─── Real-time signal listener ────────────────────────────
export function startSignalListener(onUpdate) {
  COINS.forEach(coin => {
    const docRef = doc(db, 'signals', coin);
    onSnapshot(docRef, snap => {
      if (snap.exists()) {
        const data = snap.data();
        AppState.signals[coin] = data;
        if (onUpdate) onUpdate(coin, data);
      }
    });
  });
}

// ─── Portfolio listener ───────────────────────────────────
export function startPortfolioListener(uid, onUpdate) {
  if (!uid) return;
  const docRef = doc(db, 'portfolio', uid);
  onSnapshot(docRef, snap => {
    if (snap.exists()) {
      AppState.portfolio = snap.data();
      if (onUpdate) onUpdate(AppState.portfolio);
    }
  });
}

// ─── Demo account listener ────────────────────────────────
export function startDemoListener(uid, onUpdate) {
  if (!uid) return;
  const docRef = doc(db, 'demo_accounts', uid);
  onSnapshot(docRef, snap => {
    if (snap.exists()) {
      AppState.demoAccount = snap.data();
      if (onUpdate) onUpdate(AppState.demoAccount);
    }
  });
}

// ─── Auth state ───────────────────────────────────────────
onAuthStateChanged(auth, user => {
  AppState.user = user;
  document.dispatchEvent(new CustomEvent('authChanged', { detail: { user } }));
});

// ─── Helpers ─────────────────────────────────────────────
export function formatPrice(price, coin) {
  if (!price) return '—';
  if (['GOLD', 'SILVER'].includes(coin)) {
    return `$${Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (coin === 'BTC' || price > 100) {
    return `$${Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `$${Number(price).toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;
}

export function formatPnl(pnl, includeSign = true) {
  const sign = pnl >= 0 ? '+' : '';
  return `${includeSign ? sign : ''}$${Math.abs(pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Navigation ───────────────────────────────────────────
export function navigateTo(page) {
  document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.navbar-nav a').forEach(el => el.classList.remove('active'));
  const section = document.getElementById(`page-${page}`);
  const navLink = document.querySelector(`[data-page="${page}"]`);
  if (section) { section.classList.add('active'); section.classList.add('fade-in'); }
  if (navLink) navLink.classList.add('active');
}

// ─── Init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  startPriceListener();

  // Mode badge click
  document.querySelectorAll('.mode-badge').forEach(badge => {
    badge.addEventListener('click', () => {
      setMode(AppState.mode === 'live' ? 'demo' : 'live');
    });
  });

  // Nav links
  document.querySelectorAll('.navbar-nav a[data-page]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(link.dataset.page);
    });
  });

  navigateTo('home');
});
