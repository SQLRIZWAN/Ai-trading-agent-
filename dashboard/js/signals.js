/**
 * signals.js — Real-time signal display (spot + futures).
 */

import { AppState, formatPrice, timeAgo, showToast } from './app.js';

const COIN_ICONS = {
  BTC: '₿', ETH: 'Ξ', SOL: '◎', PI: 'π', GOLD: '🥇', SILVER: '🥈'
};

export function renderSignals(containerId, type = 'spot') {
  const container = document.getElementById(containerId);
  if (!container) return;

  const coins = type === 'futures' ? ['BTC', 'ETH', 'SOL'] : ['BTC', 'ETH', 'SOL', 'PI', 'GOLD', 'SILVER'];
  container.innerHTML = '';

  coins.forEach(coin => {
    const signalData = AppState.signals[coin] || {};
    const signal = type === 'spot'
      ? signalData.spot_latest
      : signalData.futures_latest;

    if (!signal) {
      container.appendChild(buildSkeletonCard());
      return;
    }

    container.appendChild(buildSignalCard(coin, signal, type));
  });
}

function buildSignalCard(coin, signal, type) {
  const div = document.createElement('div');
  const sig = (signal.signal || 'HOLD').toLowerCase();
  div.className = `card signal-card ${sig} fade-in`;

  const isFutures = type === 'futures';
  const lev = signal.recommended_leverage || 1;
  const conf = signal.confidence || 0;
  const entry = signal.entry_price || 0;
  const sl = signal.stop_loss || 0;
  const tp1 = signal.take_profit_1 || 0;
  const tp2 = signal.take_profit_2 || 0;
  const liq = signal.liquidation_price_at_leverage || 0;
  const funding = signal.funding_rate_analysis?.rate_pct || 0;
  const rr = isFutures ? (signal.risk_reward_with_leverage || signal.risk_reward || 0) : (signal.risk_reward || 0);

  const badgeClass = {
    buy: 'badge-buy', sell: 'badge-sell', hold: 'badge-hold',
    long: 'badge-long', short: 'badge-short', no_trade: 'badge-hold'
  }[sig] || 'badge-hold';

  div.innerHTML = `
    <div class="signal-header">
      <span class="signal-coin">${COIN_ICONS[coin] || ''} ${coin}</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="signal-badge ${badgeClass}">${signal.signal || 'HOLD'}</span>
        ${isFutures ? `<span class="badge-futures">FUTURES</span>` : ''}
      </div>
    </div>
    <div class="confidence-row">
      <div class="confidence-bar">
        <div class="confidence-fill" style="width:${conf}%"></div>
      </div>
      <span class="confidence-pct">${conf}%</span>
    </div>
    <div class="signal-levels">
      <div class="level-item">
        <span class="level-label">Entry</span>
        <span class="level-value">${formatPrice(entry, coin)}</span>
      </div>
      <div class="level-item">
        <span class="level-label">Stop Loss</span>
        <span class="level-value red">${formatPrice(sl, coin)}</span>
      </div>
      <div class="level-item">
        <span class="level-label">TP1</span>
        <span class="level-value green">${formatPrice(tp1, coin)}</span>
      </div>
      <div class="level-item">
        <span class="level-label">TP2</span>
        <span class="level-value green">${formatPrice(tp2, coin)}</span>
      </div>
    </div>
    ${isFutures ? `
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
      <span class="leverage-badge">⚡ ${lev}x</span>
      <span class="liq-indicator">💀 Liq: ${formatPrice(liq, coin)}</span>
      <span style="font-size:11px;color:var(--text-muted)">
        Funding: <span class="${funding >= 0 ? 'funding-positive' : 'funding-negative'}">${funding > 0 ? '+' : ''}${funding.toFixed(4)}%</span>
      </span>
    </div>` : ''}
    <div style="margin-top:8px;display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);">
      <span>R:R ${rr.toFixed(1)}</span>
      <span>${timeAgo(signal.generated_at || new Date().toISOString())}</span>
    </div>
    ${signal.reasons?.length ? `
    <div style="margin-top:10px;font-size:11px;color:var(--text-secondary);">
      ${signal.reasons.slice(0,2).map(r => `<div>• ${r}</div>`).join('')}
    </div>` : ''}
  `;

  return div;
}

function buildSkeletonCard() {
  const div = document.createElement('div');
  div.className = 'card signal-card';
  div.innerHTML = `
    <div class="skeleton" style="height:16px;width:60%;margin-bottom:12px;"></div>
    <div class="skeleton" style="height:8px;margin-bottom:10px;"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      ${[...Array(4)].map(() => `<div class="skeleton" style="height:32px;"></div>`).join('')}
    </div>
  `;
  return div;
}

// Signal stats panel
export function renderSignalStats(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  let total = 0, highConf = 0, buy = 0, sell = 0;
  Object.values(AppState.signals).forEach(data => {
    const s = data.spot_latest;
    if (!s) return;
    total++;
    if ((s.confidence || 0) >= 75) highConf++;
    if (s.signal === 'BUY') buy++;
    if (s.signal === 'SELL') sell++;
  });

  container.innerHTML = `
    <div class="grid-4col">
      <div class="stat-card card">
        <div class="label">Total Signals</div>
        <div class="value blue">${total}</div>
        <div class="sub">active today</div>
      </div>
      <div class="stat-card card">
        <div class="label">High Confidence</div>
        <div class="value green">${highConf}</div>
        <div class="sub">≥75% confidence</div>
      </div>
      <div class="stat-card card">
        <div class="label">Buy Signals</div>
        <div class="value green">${buy}</div>
        <div class="sub">spot + futures</div>
      </div>
      <div class="stat-card card">
        <div class="label">Sell Signals</div>
        <div class="value red">${sell}</div>
        <div class="sub">spot + futures</div>
      </div>
    </div>
  `;
}
