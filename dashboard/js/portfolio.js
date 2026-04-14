/**
 * portfolio.js — Portfolio tracker (Live + Demo tabs).
 */

import { AppState, formatPrice, formatPnl, timeAgo } from './app.js';

export function renderPortfolioSummary(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const p = AppState.portfolio;
  const d = AppState.demoAccount;

  const demoBalance = d?.balance?.USDT?.total || 0;
  const demoInitial = d?.initial_balance || 10000;
  const demoPnl = demoBalance - demoInitial;
  const demoPnlPct = demoInitial ? (demoPnl / demoInitial * 100) : 0;
  const demoStats = d?.stats || {};

  container.innerHTML = `
    <div class="grid-4col" style="margin-bottom:20px;">
      <div class="stat-card card fade-in">
        <div class="label">Live Balance</div>
        <div class="value">${formatPnl(p.total_live_balance || 0, false)}</div>
        <div class="change ${(p.live_pnl_usdt||0)>=0?'green':'red'}">
          ${formatPnl(p.live_pnl_usdt || 0)} today
        </div>
      </div>
      <div class="stat-card card fade-in">
        <div class="label">Demo Balance</div>
        <div class="value purple">${formatPnl(demoBalance, false)}</div>
        <div class="change ${demoPnl>=0?'green':'red'}">
          ${formatPnl(demoPnl)} (${demoPnlPct>=0?'+':''}${demoPnlPct.toFixed(1)}% from $10K)
        </div>
      </div>
      <div class="stat-card card fade-in">
        <div class="label">Open Trades</div>
        <div class="value blue">${(p.open_live_trades||0) + (p.open_demo_spot||0) + (p.open_demo_futures||0)}</div>
        <div class="sub">${p.open_live_trades||0} live · ${(p.open_demo_spot||0)+(p.open_demo_futures||0)} demo</div>
      </div>
      <div class="stat-card card fade-in">
        <div class="label">Demo Win Rate</div>
        <div class="value ${(demoStats.win_rate||0)>=60?'green':'gold'}">${demoStats.win_rate||0}%</div>
        <div class="sub">${demoStats.total_trades||0} total trades</div>
      </div>
    </div>
  `;
}

export function renderOpenPositions(containerId, mode = 'all') {
  const container = document.getElementById(containerId);
  if (!container) return;

  const d = AppState.demoAccount;
  const spotPos = (d?.spot_positions || []).filter(p => p.status === 'open');
  const futPos = (d?.futures_positions || []).filter(p => p.status === 'open');

  const allPositions = [
    ...spotPos.map(p => ({ ...p, _type: 'spot' })),
    ...futPos.map(p => ({ ...p, _type: 'futures' })),
  ];

  if (!allPositions.length) {
    container.innerHTML = `<div style="text-align:center;padding:40px;color:var(--text-muted);">No open positions</div>`;
    return;
  }

  const rows = allPositions.map(pos => {
    const isFut = pos._type === 'futures';
    const pnl = isFut ? (pos.unrealized_pnl || 0) : (pos.pnl_usdt || 0);
    const pnlPct = isFut ? (pos.unrealized_pnl_pct || 0) : (pos.pnl_pct || 0);
    const pnlClass = pnl >= 0 ? 'green' : 'red';
    const typeLabel = isFut ? `Futures ${pos.leverage}x` : 'Spot';
    const sideLabel = (pos.side || '').toUpperCase();

    return `
      <tr>
        <td><strong>${pos.coin}</strong></td>
        <td><span style="font-size:12px;color:var(--text-secondary);">${typeLabel}</span></td>
        <td><span class="${sideLabel === 'BUY' || sideLabel === 'LONG' ? 'green' : 'red'}">${sideLabel}</span></td>
        <td>${formatPrice(pos.entry_price, pos.coin)}</td>
        <td>${formatPrice(pos.current_price || pos.entry_price, pos.coin)}</td>
        ${isFut ? `<td><span class="liq-indicator">${formatPrice(pos.liquidation_price, pos.coin)}</span></td>` : '<td>—</td>'}
        <td class="${pnlClass}"><strong>${formatPnl(pnl)}</strong> <span style="font-size:11px;">(${pnlPct>0?'+':''}${pnlPct.toFixed(2)}%)</span></td>
        <td>
          <button class="btn btn-sm btn-red" onclick="closePosition('${pos.id}','${pos._type}')">Close</button>
        </td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <div class="card" style="padding:0;overflow:hidden;">
      <table class="data-table">
        <thead>
          <tr>
            <th>Coin</th><th>Type</th><th>Side</th><th>Entry</th><th>Current</th><th>Liq Price</th><th>PnL</th><th>Action</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

export function renderTradeHistory(containerId, limit = 20) {
  // Placeholder — will be populated from Firestore trade history
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = `<div style="color:var(--text-muted);text-align:center;padding:24px;">Trade history loads from Firestore...</div>`;
}

window.closePosition = function(id, type) {
  // Sends close request — handled by demo engine or trade executor
  console.log('Close position:', id, type);
  // TODO: Call Firestore to mark as close_requested
};
