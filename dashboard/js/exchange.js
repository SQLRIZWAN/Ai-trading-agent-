/**
 * exchange.js — Exchange connection manager.
 * Encrypts API keys client-side before storing in Firestore.
 */

import { db, auth } from './firebase-config.js';
import { showToast } from './app.js';

// Dynamic import — only loaded when saving exchange config (user signed in)
async function _firestore() {
  return import("https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js");
}

const SUPPORTED_EXCHANGES = ['binance', 'bitget', 'bybit', 'okx', 'kucoin'];

// ─── Client-side encryption (AES-GCM via WebCrypto) ──────────────────────────

async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 480000, hash: 'SHA-256' },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false, ['encrypt', 'decrypt']
  );
}

async function encryptText(text, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt);
  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(text));

  const combined = new Uint8Array(salt.length + iv.length + ciphertext.byteLength);
  combined.set(salt, 0);
  combined.set(iv, salt.length);
  combined.set(new Uint8Array(ciphertext), salt.length + iv.length);
  return btoa(String.fromCharCode(...combined));
}

// ─── Exchange form ────────────────────────────────────────

export function renderExchangeConnectForm(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div class="card" style="padding:24px;max-width:500px;">
      <div class="section-title" style="margin-bottom:20px;">
        <span class="icon">🔗</span> Connect Exchange
      </div>

      <div class="form-group">
        <label class="form-label">Exchange</label>
        <select class="form-select" id="ex-name">
          ${SUPPORTED_EXCHANGES.map(e => `<option value="${e}">${e.charAt(0).toUpperCase() + e.slice(1)}</option>`).join('')}
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">API Key</label>
        <input class="form-input" id="ex-apikey" type="text" placeholder="Enter your API key" autocomplete="off" />
      </div>

      <div class="form-group">
        <label class="form-label">API Secret</label>
        <input class="form-input" id="ex-secret" type="password" placeholder="Enter your API secret" autocomplete="off" />
      </div>

      <div class="form-group">
        <label class="form-label">Passphrase <span style="color:var(--text-muted);font-weight:400;">(Bitget/OKX/KuCoin only)</span></label>
        <input class="form-input" id="ex-passphrase" type="password" placeholder="Optional passphrase" />
      </div>

      <div style="background:rgba(0,0,0,0.2);border-radius:var(--radius-md);padding:14px;margin-bottom:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:10px;">Trading Modes</div>
        <div class="toggle-row">
          <div>
            <div style="font-size:13px;font-weight:500;">Spot Trading</div>
            <div style="font-size:11px;color:var(--text-muted);">Buy/Sell real assets</div>
          </div>
          <div class="toggle-switch" id="toggle-spot" onclick="this.classList.toggle('on')">
            <div class="toggle-knob"></div>
          </div>
        </div>
        <div class="toggle-row">
          <div>
            <div style="font-size:13px;font-weight:500;">Futures Trading</div>
            <div style="font-size:11px;color:var(--text-muted);">Long/Short with leverage</div>
          </div>
          <div class="toggle-switch on" id="toggle-futures" onclick="this.classList.toggle('on')">
            <div class="toggle-knob"></div>
          </div>
        </div>
        <div id="futures-settings" style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
          <div class="form-group">
            <label class="form-label">Default Leverage</label>
            <select class="form-select" id="ex-default-lev">
              ${[1,2,3,5,10].map(l => `<option value="${l}" ${l===5?'selected':''}>${l}x</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Max Leverage</label>
            <select class="form-select" id="ex-max-lev">
              ${[2,3,5,10,20].map(l => `<option value="${l}" ${l===10?'selected':''}>${l}x</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Margin Mode</label>
            <select class="form-select" id="ex-margin-mode">
              <option value="isolated" selected>Isolated</option>
              <option value="cross">Cross</option>
            </select>
          </div>
        </div>
      </div>

      <div style="display:flex;gap:10px;">
        <button class="btn btn-ghost" onclick="testExchangeConnection()">Test Connection</button>
        <button class="btn btn-primary" onclick="saveExchangeConnection()">Save & Connect</button>
      </div>

      <div id="ex-status" style="margin-top:12px;font-size:13px;"></div>
    </div>
  `;
}

export function renderConnectedExchanges(containerId, exchanges = []) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!exchanges.length) {
    container.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">No exchanges connected yet.</div>`;
    return;
  }

  container.innerHTML = exchanges.map(ex => `
    <div class="exchange-pill">
      <div class="exchange-dot ${ex.connected ? 'ok' : 'error'}"></div>
      <div style="flex:1;">
        <div style="font-weight:600;">${ex.exchange.charAt(0).toUpperCase() + ex.exchange.slice(1)}</div>
        <div style="font-size:11px;color:var(--text-muted);">
          ${ex.spot_enabled ? `Spot: $${(ex.spot_balance||0).toLocaleString()}` : ''}
          ${ex.futures_enabled ? ` · Futures: $${(ex.futures_balance||0).toLocaleString()} (${ex.default_leverage}x)` : ''}
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <div class="toggle-switch ${ex.auto_trade ? 'on' : ''}" onclick="toggleAutoTrade('${ex.id}')">
          <div class="toggle-knob"></div>
        </div>
        <span style="font-size:11px;color:var(--text-muted);">Auto</span>
      </div>
    </div>
  `).join('');
}

// ─── Save exchange config to Firestore ────────────────────

window.saveExchangeConnection = async function() {
  const user = auth.currentUser;
  if (!user) { showToast('Please sign in first', 'error'); return; }

  const name = document.getElementById('ex-name')?.value;
  const apiKey = document.getElementById('ex-apikey')?.value?.trim();
  const secret = document.getElementById('ex-secret')?.value?.trim();
  const passphrase = document.getElementById('ex-passphrase')?.value?.trim();
  const spotEnabled = document.getElementById('toggle-spot')?.classList.contains('on');
  const futuresEnabled = document.getElementById('toggle-futures')?.classList.contains('on');
  const defaultLev = parseInt(document.getElementById('ex-default-lev')?.value || '5');
  const maxLev = parseInt(document.getElementById('ex-max-lev')?.value || '10');
  const marginMode = document.getElementById('ex-margin-mode')?.value || 'isolated';

  if (!apiKey || !secret) { showToast('API Key and Secret are required', 'error'); return; }

  const statusEl = document.getElementById('ex-status');
  statusEl.innerHTML = `<span style="color:var(--text-muted);">Encrypting keys...</span>`;

  try {
    // Encrypt client-side using user's UID as encryption password
    const password = user.uid;
    const encKey = await encryptText(apiKey, password);
    const encSecret = await encryptText(secret, password);

    const { doc, getDoc, setDoc } = await _firestore();
    const userDocRef = doc(db, 'users', user.uid);
    const userDoc = await getDoc(userDocRef);
    const userData = userDoc.exists() ? userDoc.data() : { exchanges: [] };

    const exchanges = userData.exchanges || [];
    const existingIdx = exchanges.findIndex(e => e.exchange === name);

    const exConfig = {
      id: `${name}_${Date.now()}`,
      exchange: name,
      api_key_enc: encKey,
      api_secret_enc: encSecret,
      passphrase: passphrase || null,
      spot_enabled: spotEnabled,
      futures_enabled: futuresEnabled,
      default_leverage: defaultLev,
      max_leverage: maxLev,
      margin_mode: marginMode,
      auto_trade: false,
      connected: true,
      added_at: new Date().toISOString(),
    };

    if (existingIdx >= 0) {
      exchanges[existingIdx] = exConfig;
    } else {
      exchanges.push(exConfig);
    }

    await setDoc(userDocRef, { ...userData, exchanges }, { merge: true });
    statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ Exchange connected successfully!</span>`;
    showToast(`${name} connected!`, 'success');
  } catch (err) {
    statusEl.innerHTML = `<span style="color:var(--accent-red);">Error: ${err.message}</span>`;
    showToast('Failed to save exchange', 'error');
  }
};

window.testExchangeConnection = function() {
  showToast('Test connection feature coming soon', 'info');
};

window.toggleAutoTrade = async function(exchangeId) {
  showToast('Auto-trade toggle updated', 'info');
};
