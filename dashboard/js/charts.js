/**
 * charts.js — Mini price + equity charts using Canvas API.
 * Lightweight — no external chart library required.
 * Optional: drop in TradingView Lightweight Charts by swapping renderMiniChart().
 */

import { AppState } from './app.js';

// ─── Color palette ────────────────────────────────────────
const COLORS = {
  green:  '#00d4a0',
  red:    '#ff4d6d',
  blue:   '#4d9fff',
  purple: '#a855f7',
  grid:   'rgba(255,255,255,0.05)',
  text:   'rgba(139,149,168,0.8)',
};

// ─── Render a mini sparkline from an array of close prices ─
export function renderSparkline(canvasId, closes, color = COLORS.green) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || canvas.width;
  const H = canvas.offsetHeight || canvas.height;
  canvas.width  = W;
  canvas.height = H;

  if (!closes || closes.length < 2) return;

  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;

  const toX = i => (i / (closes.length - 1)) * W;
  const toY = v => H - ((v - min) / range) * H * 0.85 - H * 0.075;

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, color + '33');
  grad.addColorStop(1, color + '00');

  ctx.clearRect(0, 0, W, H);
  ctx.beginPath();
  closes.forEach((v, i) => {
    i === 0 ? ctx.moveTo(toX(i), toY(v)) : ctx.lineTo(toX(i), toY(v));
  });
  const lastX = toX(closes.length - 1);
  const lastY = toY(closes[closes.length - 1]);

  // Fill area
  ctx.lineTo(lastX, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  closes.forEach((v, i) => {
    i === 0 ? ctx.moveTo(toX(i), toY(v)) : ctx.lineTo(toX(i), toY(v));
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Last-price dot
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
}

// ─── Render equity curve (demo vs live) ───────────────────
export function renderEquityCurve(canvasId, liveHistory = [], demoHistory = []) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || 500;
  const H = canvas.offsetHeight || 200;
  canvas.width  = W;
  canvas.height = H;

  ctx.clearRect(0, 0, W, H);

  if (!liveHistory.length && !demoHistory.length) {
    ctx.fillStyle = COLORS.text;
    ctx.font = '12px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No trade history yet', W / 2, H / 2);
    return;
  }

  const allValues = [...liveHistory, ...demoHistory];
  const min = Math.min(...allValues) * 0.99;
  const max = Math.max(...allValues) * 1.01;
  const range = max - min || 1;

  const toX = (i, arr) => (i / Math.max(arr.length - 1, 1)) * (W - 40) + 20;
  const toY = v => H - 20 - ((v - min) / range) * (H - 40);

  // Grid lines
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 20 + (i / 4) * (H - 40);
    ctx.beginPath();
    ctx.moveTo(20, y);
    ctx.lineTo(W - 20, y);
    ctx.stroke();
  }

  const drawLine = (data, color) => {
    if (data.length < 2) return;
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color + '22');
    grad.addColorStop(1, color + '00');

    ctx.beginPath();
    data.forEach((v, i) => {
      i === 0 ? ctx.moveTo(toX(i, data), toY(v)) : ctx.lineTo(toX(i, data), toY(v));
    });
    const lx = toX(data.length - 1, data);
    ctx.lineTo(lx, H - 20);
    ctx.lineTo(20, H - 20);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    data.forEach((v, i) => {
      i === 0 ? ctx.moveTo(toX(i, data), toY(v)) : ctx.lineTo(toX(i, data), toY(v));
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();
  };

  if (liveHistory.length) drawLine(liveHistory, COLORS.blue);
  if (demoHistory.length) drawLine(demoHistory, COLORS.purple);

  // Legend
  if (liveHistory.length && demoHistory.length) {
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillStyle = COLORS.blue;
    ctx.fillRect(W - 120, 8, 10, 10);
    ctx.fillStyle = COLORS.text;
    ctx.fillText('Live', W - 106, 18);
    ctx.fillStyle = COLORS.purple;
    ctx.fillRect(W - 70, 8, 10, 10);
    ctx.fillStyle = COLORS.text;
    ctx.fillText('Demo', W - 56, 18);
  }
}

// ─── Bar chart for signal confidence ─────────────────────
export function renderConfidenceChart(canvasId, signals = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || 400;
  const H = canvas.offsetHeight || 120;
  canvas.width  = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);

  const coins = Object.keys(signals);
  if (!coins.length) return;

  const barW = (W - 40) / coins.length - 8;
  const maxH  = H - 30;

  coins.forEach((coin, i) => {
    const sig  = signals[coin]?.spot_latest || {};
    const conf = sig.confidence || 0;
    const direction = sig.signal || 'HOLD';
    const color = direction === 'BUY' ? COLORS.green
                : direction === 'SELL' ? COLORS.red
                : COLORS.text;

    const x = 20 + i * ((W - 40) / coins.length);
    const barH = (conf / 100) * maxH;
    const y = H - 20 - barH;

    // Bar
    const grad = ctx.createLinearGradient(0, y, 0, H - 20);
    grad.addColorStop(0, color + 'cc');
    grad.addColorStop(1, color + '33');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x, y, barW, barH, 3);
    ctx.fill();

    // Coin label
    ctx.fillStyle = COLORS.text;
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(coin, x + barW / 2, H - 5);

    // Confidence value
    ctx.fillStyle = color;
    ctx.font = 'bold 10px Inter, sans-serif';
    ctx.fillText(`${conf}%`, x + barW / 2, y - 4);
  });
}

// ─── Auto-refresh all charts every 30s ───────────────────
export function startChartRefresh(interval = 30000) {
  setInterval(() => {
    document.dispatchEvent(new CustomEvent('refreshCharts'));
  }, interval);
}
