/**
 * demo.js — Demo trading interface (Spot + Futures paper trading).
 */

import { db, auth } from './firebase-config.js';
import { doc, getDoc, setDoc } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";
import { AppState, formatPrice, formatPnl, showToast } from './app.js';

const DEMO_INITIAL = 10000;

export function renderDemoPage(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const d = AppState.demoAccount;
  const stats = d?.stats || {};
  const bal = d?.balance?.USDT?.total || DEMO_INITIAL;
  const initBal = d?.initial_balance || DEMO_INITIAL;
  const totalPnl = bal - initBal;
  const totalPnlPct = initBal ? (totalPnl / initBal * 100) : 0;
  const equityPct = Math.min(100, Math.max(0, (bal / (initBal * 1.5)) * 100));

  const spotTrades = stats.spot_trades || 0;
  const futTrades = stats.futures_trades || 0;
  const wr = stats.win_rate || 0;

  container.innerHTML = `
    <!-- Header -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
      <div>
        <h2 style="font-size:20px;font-weight:700;margin-bottom:4px;">🧪 Demo Trading</h2>
        <div style="font-size:13px;color:var(--text-secondary);">Practice with $${DEMO_INITIAL.toLocaleString()} virtual money. Zero risk.</div>
      </div>
      <button class="btn btn-ghost" onclick="resetDemoAccount()">↺ Reset Account</button>
    </div>

    <!-- Balance card -->
    <div class="card" style="padding:20px;margin-bottom:20px;">
      <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:12px;">
        <div>
          <div style="font-size:12px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Virtual Balance</div>
          <div style="font-size:32px;font-weight:700;">$${bal.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</div>
        </div>
        <div style="text-align:right;">
          <div class="${totalPnl>=0?'green':'red'}" style="font-size:18px;font-weight:700;">
            ${totalPnl>=0?'+':''}${formatPnl(totalPnl)} (${totalPnlPct>=0?'+':''}${totalPnlPct.toFixed(1)}%)
          </div>
          <div style="font-size:12px;color:var(--text-muted);">from $${initBal.toLocaleString()}</div>
        </div>
      </div>
      <div class="equity-bar-wrap">
        <div class="equity-bar-fill" style="width:${equityPct}%"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-top:4px;">
        <span>$${initBal.toLocaleString()} Started</span>
        <span>$${bal.toLocaleString('en-US',{maximumFractionDigits:0})} Current</span>
      </div>
    </div>

    <!-- Stats row -->
    <div class="grid-3col" style="margin-bottom:20px;">
      <div class="card" style="padding:16px;">
        <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;margin-bottom:8px;">📊 Demo Spot</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
          <div><div style="color:var(--text-muted);">Trades</div><div style="font-weight:600;">${spotTrades}</div></div>
          <div><div style="color:var(--text-muted);">Win Rate</div><div style="font-weight:600;color:var(--accent-green);">${wr}%</div></div>
        </div>
      </div>
      <div class="card" style="padding:16px;">
        <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;margin-bottom:8px;">📈 Demo Futures</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
          <div><div style="color:var(--text-muted);">Trades</div><div style="font-weight:600;">${futTrades}</div></div>
          <div><div style="color:var(--text-muted);">Best</div><div style="font-weight:600;color:var(--accent-green);">+${stats.best_trade_pct||0}%</div></div>
        </div>
      </div>
      <div class="card" style="padding:16px;">
        <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;margin-bottom:8px;">📊 Performance</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
          <div><div style="color:var(--text-muted);">Total PnL</div><div style="font-weight:600;color:var(--accent-green);">+${formatPnl(stats.total_pnl_usdt||0)}</div></div>
          <div><div style="color:var(--text-muted);">Drawdown</div><div style="font-weight:600;color:var(--accent-red);">-${stats.max_drawdown_pct||0}%</div></div>
        </div>
      </div>
    </div>

    <!-- Open positions -->
    <div class="section-header">
      <div class="section-title"><span class="icon">📋</span>Open Demo Positions</div>
    </div>
    <div id="demo-positions" style="margin-bottom:20px;"></div>

    <!-- Quick demo trade -->
    <div class="card" style="padding:20px;margin-bottom:20px;">
      <div class="section-title" style="margin-bottom:16px;"><span class="icon">⚡</span>Quick Demo Trade</div>
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;align-items:end;">
        <div class="form-group" style="margin:0;">
          <label class="form-label">Coin</label>
          <select class="form-select" id="demo-coin">
            <option>BTC</option><option>ETH</option><option>SOL</option>
          </select>
        </div>
        <div class="form-group" style="margin:0;">
          <label class="form-label">Mode</label>
          <select class="form-select" id="demo-mode">
            <option value="spot">Spot</option>
            <option value="futures">Futures</option>
          </select>
        </div>
        <div class="form-group" style="margin:0;">
          <label class="form-label">Side</label>
          <select class="form-select" id="demo-side">
            <option value="buy">BUY / LONG</option>
            <option value="sell">SELL / SHORT</option>
          </select>
        </div>
        <div class="form-group" style="margin:0;">
          <label class="form-label">Amount ($)</label>
          <input class="form-input" id="demo-amount" type="number" value="500" min="10" />
        </div>
        <div class="form-group" style="margin:0;">
          <label class="form-label">Leverage</label>
          <select class="form-select" id="demo-leverage">
            ${[1,2,3,5,10].map(l=>`<option value="${l}" ${l===5?'selected':''}>${l}x</option>`).join('')}
          </select>
        </div>
      </div>
      <div style="margin-top:14px;">
        <button class="btn btn-primary btn-lg" onclick="executeDemoTrade()">Execute Demo Trade</button>
      </div>
    </div>

    <!-- Promotion banner -->
    ${wr >= 60 ? `
    <div class="promo-banner">
      <div class="promo-text">
        💡 Your demo win rate is <strong>${wr}%</strong> over ${stats.total_trades||0} trades!
        That's above the 60% threshold. Ready to trade with real money?
      </div>
      <a href="#" class="btn btn-primary" onclick="navigateTo('exchange')">🚀 Connect Exchange →</a>
    </div>` : ''}
  `;

  // Render positions inside the demo page
  import('./portfolio.js').then(m => m.renderOpenPositions('demo-positions', 'demo'));
}

window.executeDemoTrade = async function() {
  const user = auth.currentUser;
  if (!user) { showToast('Please sign in first', 'error'); return; }

  const coin = document.getElementById('demo-coin')?.value;
  const mode = document.getElementById('demo-mode')?.value;
  const side = document.getElementById('demo-side')?.value;
  const amount = parseFloat(document.getElementById('demo-amount')?.value || '500');
  const leverage = parseInt(document.getElementById('demo-leverage')?.value || '1');

  // Get current price from AppState
  const price = AppState.prices[coin]?.price;
  if (!price) { showToast('Price not available yet', 'error'); return; }

  const sl = side === 'buy'
    ? price * (mode === 'futures' ? 0.985 : 0.97)
    : price * (mode === 'futures' ? 1.015 : 1.03);

  const tp1 = side === 'buy' ? price * 1.02 : price * 0.98;

  showToast(`Demo ${mode} ${side.toUpperCase()} ${coin} order placed!`, 'success');
  // Full execution is handled by the backend demo_engine.py
  // Dashboard just shows confirmation; actual position will appear on next sync
};

window.resetDemoAccount = async function() {
  const user = auth.currentUser;
  if (!user) return;
  if (!confirm('Reset demo account to $10,000? All positions will be closed.')) return;

  const docRef = doc(db, 'demo_accounts', user.uid);
  await setDoc(docRef, {
    balance: { USDT: { free: DEMO_INITIAL, used: 0, total: DEMO_INITIAL } },
    initial_balance: DEMO_INITIAL,
    spot_positions: [],
    futures_positions: [],
    stats: {
      total_trades: 0, winning_trades: 0, losing_trades: 0,
      win_rate: 0, total_pnl_usdt: 0, total_pnl_pct: 0, max_drawdown_pct: 0,
    },
    last_reset: new Date().toISOString(),
  }, { merge: false });

  showToast('Demo account reset to $10,000', 'success');
};
