/**
 * futures.js — Futures trading UI panel.
 * Shows LONG/SHORT signals with leverage, liquidation, margin controls.
 */

import { AppState, formatPrice, formatPnl, showToast } from './app.js';

const COIN_ICONS = { BTC: '₿', ETH: 'Ξ', SOL: '◎' };

export function renderFuturesPanel(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <!-- Futures header info bar -->
    <div class="card" style="padding:14px 20px;margin-bottom:16px;display:flex;gap:24px;flex-wrap:wrap;">
      <div>
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Mode</div>
        <div style="font-weight:700;color:var(--accent-blue);">Perpetual Futures (USDT-M)</div>
      </div>
      <div>
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Supported Exchanges</div>
        <div style="font-weight:600;">Binance · Bybit · Bitget · OKX</div>
      </div>
      <div>
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Max Leverage</div>
        <div style="font-weight:700;color:var(--accent-gold);">20x</div>
      </div>
      <div style="margin-left:auto;">
        <div class="tabs">
          <button class="tab-btn active" onclick="switchFuturesTab(this,'signals')">Signals</button>
          <button class="tab-btn" onclick="switchFuturesTab(this,'positions')">Positions</button>
          <button class="tab-btn" onclick="switchFuturesTab(this,'funding')">Funding</button>
        </div>
      </div>
    </div>

    <!-- Signals tab -->
    <div id="futures-tab-signals">
      <div id="futures-signals-grid" class="grid-3col"></div>
    </div>

    <!-- Positions tab -->
    <div id="futures-tab-positions" style="display:none;">
      <div id="futures-positions-table"></div>
    </div>

    <!-- Funding tab -->
    <div id="futures-tab-funding" style="display:none;">
      <div id="futures-funding-table"></div>
    </div>
  `;

  renderFuturesSignals();
  renderFuturesPositions();
  renderFundingRates();
}

// ─── Futures signal cards ─────────────────────────────────
function renderFuturesSignals() {
  const grid = document.getElementById('futures-signals-grid');
  if (!grid) return;
  grid.innerHTML = '';

  ['BTC', 'ETH', 'SOL'].forEach(coin => {
    const data = AppState.signals[coin] || {};
    const sig  = data.futures_latest || null;
    grid.appendChild(buildFuturesCard(coin, sig));
  });
}

function buildFuturesCard(coin, sig) {
  const div = document.createElement('div');
  if (!sig) {
    div.className = 'card signal-card fade-in';
    div.innerHTML = `
      <div class="signal-header">
        <span class="signal-coin">${COIN_ICONS[coin]||''} ${coin}</span>
        <span class="signal-badge badge-hold">LOADING</span>
      </div>
      <div class="skeleton" style="height:60px;margin-top:12px;border-radius:8px;"></div>
    `;
    return div;
  }

  const direction  = sig.signal || 'NO_TRADE';
  const conf       = sig.confidence || 0;
  const entry      = sig.entry_price || 0;
  const sl         = sig.stop_loss || 0;
  const tp1        = sig.take_profit_1 || 0;
  const tp2        = sig.take_profit_2 || 0;
  const tp3        = sig.take_profit_3 || 0;
  const lev        = sig.recommended_leverage || 1;
  const marginMode = sig.margin_mode || 'isolated';
  const liq        = sig.liquidation_price_at_leverage || 0;
  const rr         = sig.risk_reward_with_leverage || sig.risk_reward || 0;
  const funding    = sig.funding_rate_analysis || {};
  const oi         = sig.oi_analysis || {};
  const posSize    = sig.position_size_pct || 0;
  const reasons    = sig.reasons || [];
  const risks      = sig.risks || [];

  const dirClass  = direction === 'LONG' ? 'long' : direction === 'SHORT' ? 'short' : 'hold';
  const badgeCls  = direction === 'LONG' ? 'badge-long' : direction === 'SHORT' ? 'badge-short' : 'badge-hold';
  const fr        = funding.rate_pct || 0;
  const frClass   = fr >= 0 ? 'funding-positive' : 'funding-negative';
  const oiArrow   = oi.trend === 'rising' ? '▲' : oi.trend === 'falling' ? '▼' : '→';
  const oiColor   = oi.trend === 'rising' ? 'var(--accent-green)' : oi.trend === 'falling' ? 'var(--accent-red)' : 'var(--text-muted)';

  const slPct  = entry ? ((sl  - entry) / entry * 100).toFixed(2) : 0;
  const tp1Pct = entry ? ((tp1 - entry) / entry * 100).toFixed(2) : 0;
  const tp2Pct = entry ? ((tp2 - entry) / entry * 100).toFixed(2) : 0;
  const tp3Pct = entry ? ((tp3 - entry) / entry * 100).toFixed(2) : 0;

  div.className = `card signal-card ${dirClass} fade-in`;
  div.innerHTML = `
    <div class="signal-header">
      <span class="signal-coin">${COIN_ICONS[coin]||''} ${coin}</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="signal-badge ${badgeCls}">${direction}</span>
        <span class="badge-futures">PERP</span>
      </div>
    </div>

    <!-- Confidence -->
    <div class="confidence-row">
      <div class="confidence-bar">
        <div class="confidence-fill" style="width:${conf}%"></div>
      </div>
      <span class="confidence-pct">${conf}%</span>
    </div>

    <!-- Leverage + Margin -->
    <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
      <span class="leverage-badge">⚡ ${lev}x</span>
      <span style="font-size:11px;padding:2px 8px;background:rgba(255,255,255,0.06);border-radius:4px;color:var(--text-secondary);">
        ${marginMode === 'isolated' ? '🔒 Isolated' : '🔓 Cross'}
      </span>
      <span style="font-size:11px;padding:2px 8px;background:rgba(255,215,0,0.1);border-radius:4px;color:var(--accent-gold);">
        Size: ${posSize}%
      </span>
    </div>

    <!-- Price levels -->
    <div class="signal-levels">
      <div class="level-item">
        <span class="level-label">Entry</span>
        <span class="level-value">${formatPrice(entry, coin)}</span>
      </div>
      <div class="level-item">
        <span class="level-label">Stop Loss</span>
        <span class="level-value red">${formatPrice(sl, coin)} <span style="font-size:10px;">(${slPct}%)</span></span>
      </div>
      <div class="level-item">
        <span class="level-label">TP1 (25%)</span>
        <span class="level-value green">${formatPrice(tp1, coin)} <span style="font-size:10px;">(+${tp1Pct}%)</span></span>
      </div>
      <div class="level-item">
        <span class="level-label">TP2 (50%)</span>
        <span class="level-value green">${formatPrice(tp2, coin)} <span style="font-size:10px;">(+${tp2Pct}%)</span></span>
      </div>
      <div class="level-item">
        <span class="level-label">TP3 (25%)</span>
        <span class="level-value green">${formatPrice(tp3, coin)} <span style="font-size:10px;">(+${tp3Pct}%)</span></span>
      </div>
      <div class="level-item">
        <span class="level-label">R:R Ratio</span>
        <span class="level-value blue">${Number(rr).toFixed(1)}</span>
      </div>
    </div>

    <!-- Liquidation -->
    <div style="display:flex;align-items:center;gap:8px;margin-top:10px;padding:8px;background:rgba(255,77,109,0.06);border-radius:8px;border:1px solid rgba(255,77,109,0.15);">
      <span style="font-size:12px;">💀</span>
      <div>
        <div style="font-size:10px;color:var(--text-muted);">Liquidation Price (${lev}x)</div>
        <div style="font-size:13px;font-weight:700;color:var(--accent-red);">${formatPrice(liq, coin)}</div>
      </div>
    </div>

    <!-- Futures data -->
    <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
      <div style="padding:6px 8px;background:rgba(0,0,0,0.2);border-radius:6px;">
        <div style="color:var(--text-muted);margin-bottom:2px;">Funding Rate</div>
        <div class="${frClass}" style="font-weight:600;">${fr >= 0 ? '+' : ''}${fr.toFixed(4)}%</div>
      </div>
      <div style="padding:6px 8px;background:rgba(0,0,0,0.2);border-radius:6px;">
        <div style="color:var(--text-muted);margin-bottom:2px;">Open Interest</div>
        <div style="color:${oiColor};font-weight:600;">${oiArrow} ${oi.trend || 'N/A'}</div>
      </div>
    </div>

    <!-- Reasons (collapsed) -->
    ${reasons.length ? `
    <details style="margin-top:10px;">
      <summary style="font-size:11px;color:var(--text-secondary);cursor:pointer;">View Analysis (${reasons.length} reasons)</summary>
      <div style="margin-top:6px;font-size:11px;color:var(--text-secondary);">
        ${reasons.map(r => `<div>• ${r}</div>`).join('')}
        ${risks.map(r => `<div style="color:var(--accent-red);">⚠ ${r}</div>`).join('')}
      </div>
    </details>` : ''}
  `;
  return div;
}

// ─── Futures positions table ──────────────────────────────
function renderFuturesPositions() {
  const container = document.getElementById('futures-positions-table');
  if (!container) return;

  const d = AppState.demoAccount;
  const positions = (d?.futures_positions || []).filter(p => p.status === 'open');

  if (!positions.length) {
    container.innerHTML = `
      <div class="card" style="padding:40px;text-align:center;color:var(--text-muted);">
        No open futures positions
      </div>`;
    return;
  }

  const rows = positions.map(pos => {
    const pnl = pos.unrealized_pnl || 0;
    const pnlPct = pos.unrealized_pnl_pct || 0;
    const pnlCls = pnl >= 0 ? 'green' : 'red';
    const sideCls = pos.side === 'long' ? 'green' : 'red';
    const margin = pos.margin_used || 0;
    const liqDist = pos.liquidation_price && pos.current_price
      ? Math.abs((pos.current_price - pos.liquidation_price) / pos.current_price * 100).toFixed(1)
      : '—';

    return `
      <tr>
        <td><strong>${pos.coin}</strong></td>
        <td><span class="${sideCls}">${(pos.side||'').toUpperCase()}</span></td>
        <td><span class="leverage-badge">⚡${pos.leverage}x</span></td>
        <td>${formatPrice(pos.entry_price, pos.coin)}</td>
        <td>${formatPrice(pos.current_price || pos.entry_price, pos.coin)}</td>
        <td>$${margin.toFixed(2)}</td>
        <td class="${pnlCls}"><strong>${formatPnl(pnl)}</strong><br><small>${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</small></td>
        <td><span style="color:var(--accent-red);font-size:12px;">${formatPrice(pos.liquidation_price, pos.coin)}</span><br><small style="color:var(--text-muted);">${liqDist}% away</small></td>
        <td>
          <button class="btn btn-sm btn-red" onclick="closeFuturesPosition('${pos.id}')">Close</button>
        </td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <div class="card" style="padding:0;overflow:hidden;">
      <table class="data-table">
        <thead>
          <tr>
            <th>Coin</th><th>Side</th><th>Lev</th><th>Entry</th><th>Mark</th>
            <th>Margin</th><th>PnL</th><th>Liquidation</th><th>Action</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ─── Funding rates table ──────────────────────────────────
function renderFundingRates() {
  const container = document.getElementById('futures-funding-table');
  if (!container) return;

  const coins = ['BTC', 'ETH', 'SOL'];
  const rows = coins.map(coin => {
    const mkt = AppState.prices[coin] || {};
    const futures = mkt.futures_data?.funding || {};
    const fr   = futures.funding_rate_pct || 0;
    const frCls = fr >= 0 ? 'funding-positive' : 'funding-negative';
    const sent  = futures.funding_sentiment || '—';
    const extreme = futures.funding_extreme ? '⚠️ Extreme' : '✓ Normal';

    return `
      <tr>
        <td><strong>${COIN_ICONS[coin]||''} ${coin}</strong></td>
        <td class="${frCls}"><strong>${fr >= 0 ? '+' : ''}${fr.toFixed(4)}%</strong></td>
        <td>${sent}</td>
        <td>${extreme}</td>
        <td style="color:var(--text-muted);font-size:11px;">
          ${fr >= 0 ? 'Longs pay shorts — bearish bias' : 'Shorts pay longs — bullish bias'}
        </td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <div class="card" style="padding:0;overflow:hidden;margin-bottom:16px;">
      <table class="data-table">
        <thead>
          <tr><th>Coin</th><th>Funding Rate (8h)</th><th>Sentiment</th><th>Status</th><th>Interpretation</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="card" style="padding:16px;font-size:12px;color:var(--text-secondary);">
      <strong>How Funding Rates Work:</strong> Positive rate → Longs pay Shorts (bearish pressure).
      Negative rate → Shorts pay Longs (bullish pressure). Rates reset every 8 hours.
      Extreme rates (>0.1%) signal potential reversal.
    </div>`;
}

// ─── Tab switcher ─────────────────────────────────────────
window.switchFuturesTab = function(btn, tab) {
  document.querySelectorAll('#futures-tab-signals, #futures-tab-positions, #futures-tab-funding')
    .forEach(el => el.style.display = 'none');
  document.querySelectorAll('#futures-tab-signals').forEach(el => el.style.display = tab === 'signals' ? 'block' : 'none');
  document.querySelectorAll('#futures-tab-positions').forEach(el => el.style.display = tab === 'positions' ? 'block' : 'none');
  document.querySelectorAll('#futures-tab-funding').forEach(el => el.style.display = tab === 'funding' ? 'block' : 'none');

  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  if (tab === 'positions') renderFuturesPositions();
  if (tab === 'funding')   renderFundingRates();
};

window.closeFuturesPosition = function(id) {
  showToast(`Close request sent for position ${id}`, 'info');
  // Handled by backend — demo_engine.py will close on next run
};
