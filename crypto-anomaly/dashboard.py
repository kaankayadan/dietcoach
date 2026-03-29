"""
Real-time dashboard: FastAPI + WebSocket + inline HTML/JS/Chart.js.

- GET /       → Single-page dashboard
- WS  /ws     → Real-time event stream
- GET /stats  → JSON system stats
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto Anomaly Detector")

# Connected WebSocket clients
_clients: set[WebSocket] = set()

# Stats callback (set by main.py)
_stats_callback = None


def set_stats_callback(callback):
    global _stats_callback
    _stats_callback = callback


async def broadcast(data: dict[str, Any]) -> None:
    """Send data to all connected WebSocket clients."""
    if not _clients:
        return
    message = json.dumps(data, default=str)
    disconnected = set()
    for ws in _clients:
        try:
            await asyncio.wait_for(ws.send_text(message), timeout=5.0)
        except Exception:
            disconnected.add(ws)
    _clients -= disconnected


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/stats")
async def stats():
    if _stats_callback:
        return _stats_callback()
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    logger.info(f"Dashboard client connected ({len(_clients)} total)")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        logger.info(f"Dashboard client disconnected ({len(_clients)} total)")


# ─────────────────────────────────────────────────────────────
# Inline Dashboard HTML
# ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Anomaly Detector</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #0a0a1a;
    color: #e0e0e0;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #1a1a3e, #0d0d2b);
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a2a5a;
  }
  .header h1 { font-size: 20px; color: #7c8cf8; }
  .status {
    display: flex; gap: 16px; align-items: center; font-size: 13px;
  }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; margin-right: 4px;
  }
  .dot-green { background: #4caf50; box-shadow: 0 0 6px #4caf50; }
  .dot-red { background: #f44336; box-shadow: 0 0 6px #f44336; }
  .container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto 1fr;
    gap: 12px;
    padding: 12px;
    max-width: 1600px;
    margin: 0 auto;
    height: calc(100vh - 60px);
  }
  .card {
    background: #12122a;
    border: 1px solid #2a2a5a;
    border-radius: 8px;
    padding: 16px;
    overflow-y: auto;
  }
  .card h2 {
    font-size: 14px; color: #7c8cf8;
    margin-bottom: 12px; text-transform: uppercase;
    letter-spacing: 1px;
  }
  .gauges {
    grid-column: 1 / -1;
    display: flex; gap: 12px; flex-wrap: wrap;
    justify-content: center; align-items: center;
    padding: 8px;
  }
  .gauge-item {
    text-align: center; width: 100px;
  }
  .gauge-item canvas { width: 80px !important; height: 80px !important; }
  .gauge-label { font-size: 11px; margin-top: 4px; color: #aaa; }
  .gauge-value { font-size: 16px; font-weight: bold; }

  /* Anomaly feed */
  .anomaly-entry {
    padding: 10px;
    margin-bottom: 8px;
    border-radius: 6px;
    border-left: 3px solid #555;
    background: #1a1a35;
    cursor: pointer;
    transition: background 0.2s;
    font-size: 13px;
  }
  .anomaly-entry:hover { background: #22224a; }
  .anomaly-entry.warning { border-left-color: #ff9800; }
  .anomaly-entry.critical {
    border-left-color: #f44336;
    animation: flash 0.5s;
  }
  @keyframes flash {
    0%, 100% { background: #1a1a35; }
    50% { background: #3a1a1a; }
  }
  .anomaly-symbol { font-weight: bold; color: #7c8cf8; }
  .anomaly-sigma { font-weight: bold; }
  .sigma-high { color: #f44336; }
  .sigma-med { color: #ff9800; }

  /* Sparklines */
  .sparkline-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }
  .sparkline-item { text-align: center; }
  .sparkline-item canvas { width: 100% !important; height: 60px !important; }
  .sparkline-label {
    font-size: 11px; color: #aaa;
    display: flex; justify-content: space-between; padding: 0 4px;
  }
  .sparkline-price { color: #4caf50; font-weight: bold; font-size: 13px; }

  /* Similar patterns panel */
  .pattern-entry {
    padding: 8px;
    margin-bottom: 6px;
    background: #1a1a35;
    border-radius: 4px;
    font-size: 12px;
  }
  .pattern-entry .sim { color: #4caf50; }
  .pattern-entry .move-pos { color: #4caf50; font-weight: bold; }
  .pattern-entry .move-neg { color: #f44336; font-weight: bold; }

  /* Trend summary */
  .trend-box {
    background: #1a1a35;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 10px;
  }
  .trend-box h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; }
  .trend-row {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 6px;
  }
  .trend-card {
    background: #12122a;
    border: 1px solid #2a2a5a;
    border-radius: 6px;
    padding: 10px 14px;
    min-width: 140px;
    text-align: center;
  }
  .trend-card .interval { font-size: 11px; color: #888; }
  .trend-card .direction { font-size: 16px; font-weight: bold; }
  .trend-card .details { font-size: 11px; color: #aaa; margin-top: 4px; }
  .trend-bullish { border-color: #4caf50; }
  .trend-bullish .direction { color: #4caf50; }
  .trend-bearish { border-color: #f44336; }
  .trend-bearish .direction { color: #f44336; }
  .trend-neutral { border-color: #ff9800; }
  .trend-neutral .direction { color: #ff9800; }

  /* Anomaly trend tag */
  .trend-tag {
    display: inline-block;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
    margin-left: 6px;
  }
  .tag-bullish { background: #1b3a1b; color: #4caf50; }
  .tag-bearish { background: #3a1b1b; color: #f44336; }
  .tag-neutral { background: #3a3a1b; color: #ff9800; }

  .empty-msg { color: #555; font-style: italic; font-size: 13px; }
</style>
</head>
<body>

<div class="header">
  <h1>Crypto Anomaly Detector</h1>
  <div class="status">
    <span><span class="status-dot dot-red" id="connDot"></span><span id="connText">Disconnected</span></span>
    <span id="statsText">Vectors: 0</span>
    <span id="uptimeText"></span>
  </div>
</div>

<div class="container">
  <div class="card gauges" id="gaugeSection">
    <p class="empty-msg">Waiting for data...</p>
  </div>

  <div class="card" style="max-height: 45vh;">
    <h2>Anomaly Feed</h2>
    <div id="anomalyList">
      <p class="empty-msg">No anomalies detected yet</p>
    </div>
  </div>

  <div class="card" style="max-height: 45vh;">
    <h2>Price Charts</h2>
    <div class="sparkline-grid" id="sparklineGrid"></div>
  </div>

  <div class="card" id="patternsCard" style="grid-column: 1 / -1; max-height: 25vh;">
    <h2>Similar Historical Patterns</h2>
    <div id="patternsList">
      <p class="empty-msg">Click an anomaly to see similar patterns</p>
    </div>
  </div>
</div>

<script>
const MAX_ANOMALIES = 50;
const MAX_SPARKLINE_POINTS = 60;

// State
const priceData = {};     // symbol -> [prices]
const gaugeCharts = {};   // symbol -> Chart
const sparkCharts = {};   // symbol -> Chart
const anomalies = [];
let vectorCount = 0;
const startTime = Date.now();

// WebSocket
let ws;
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById('connDot').className = 'status-dot dot-green';
    document.getElementById('connText').textContent = 'Connected';
  };
  ws.onclose = () => {
    document.getElementById('connDot').className = 'status-dot dot-red';
    document.getElementById('connText').textContent = 'Reconnecting...';
    setTimeout(connect, 2000);
  };
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleMessage(data);
    } catch(err) { console.error('Parse error:', err); }
  };
}

function handleMessage(data) {
  switch(data.type) {
    case 'candle': handleCandle(data); break;
    case 'anomaly': handleAnomaly(data); break;
    case 'status': handleStatus(data); break;
  }
}

function handleCandle(data) {
  const sym = data.symbol;
  if (!priceData[sym]) priceData[sym] = [];
  priceData[sym].push(data.price);
  if (priceData[sym].length > MAX_SPARKLINE_POINTS) priceData[sym].shift();
  updateSparkline(sym, data.price);
}

function handleAnomaly(data) {
  anomalies.unshift(data);
  if (anomalies.length > MAX_ANOMALIES) anomalies.pop();
  renderAnomalyList();
  updateGauge(data.symbol, data.sigma_level);
}

function handleStatus(data) {
  vectorCount = data.vector_count || 0;
  document.getElementById('statsText').textContent = `Vectors: ${vectorCount.toLocaleString()}`;
}

// Gauges
function updateGauge(symbol, sigma) {
  const section = document.getElementById('gaugeSection');
  // Remove empty message
  const empty = section.querySelector('.empty-msg');
  if (empty) empty.remove();

  if (!gaugeCharts[symbol]) {
    const div = document.createElement('div');
    div.className = 'gauge-item';
    div.innerHTML = `<canvas id="gauge-${symbol}"></canvas>
      <div class="gauge-label">${symbol.toUpperCase()}</div>
      <div class="gauge-value" id="gval-${symbol}">0.0</div>`;
    section.appendChild(div);

    const ctx = document.getElementById(`gauge-${symbol}`).getContext('2d');
    gaugeCharts[symbol] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        datasets: [{
          data: [0, 4],
          backgroundColor: ['#4caf50', '#1a1a35'],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: false,
        cutout: '70%',
        rotation: -90,
        circumference: 180,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        animation: false,
      }
    });
  }

  const chart = gaugeCharts[symbol];
  const clampedSigma = Math.min(Math.max(sigma, 0), 4);
  const color = sigma > 3 ? '#f44336' : sigma > 2 ? '#ff9800' : '#4caf50';
  chart.data.datasets[0].data = [clampedSigma, 4 - clampedSigma];
  chart.data.datasets[0].backgroundColor[0] = color;
  chart.update();

  const gval = document.getElementById(`gval-${symbol}`);
  if (gval) {
    gval.textContent = sigma.toFixed(1) + 'σ';
    gval.style.color = color;
  }
}

// Sparklines
function updateSparkline(symbol, price) {
  const grid = document.getElementById('sparklineGrid');

  if (!sparkCharts[symbol]) {
    const div = document.createElement('div');
    div.className = 'sparkline-item';
    div.innerHTML = `<div class="sparkline-label">
        <span>${symbol.toUpperCase()}</span>
        <span class="sparkline-price" id="price-${symbol}">$${price.toFixed(2)}</span>
      </div>
      <canvas id="spark-${symbol}"></canvas>`;
    grid.appendChild(div);

    const ctx = document.getElementById(`spark-${symbol}`).getContext('2d');
    sparkCharts[symbol] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: Array(MAX_SPARKLINE_POINTS).fill(''),
        datasets: [{
          data: priceData[symbol] || [],
          borderColor: '#7c8cf8',
          borderWidth: 1.5,
          fill: false,
          pointRadius: 0,
          tension: 0.3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { display: false },
        },
        animation: false,
      }
    });
  }

  const chart = sparkCharts[symbol];
  chart.data.datasets[0].data = priceData[symbol] || [];
  chart.data.labels = Array(Math.max((priceData[symbol]||[]).length, 1)).fill('');
  chart.update();

  const priceEl = document.getElementById(`price-${symbol}`);
  if (priceEl) priceEl.textContent = '$' + price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

// Anomaly list
function renderAnomalyList() {
  const container = document.getElementById('anomalyList');
  container.innerHTML = '';
  anomalies.forEach((a, i) => {
    const div = document.createElement('div');
    div.className = `anomaly-entry ${a.alert_level}`;
    const time = new Date(a.timestamp * 1000).toLocaleTimeString();
    const sigmaClass = a.sigma_level > 3 ? 'sigma-high' : 'sigma-med';

    // Build trend tag from first available trend summary
    let trendTag = '';
    if (a.trend_summaries && a.trend_summaries.length > 0) {
      const t = a.trend_summaries[0]; // use shortest interval
      const tagClass = t.direction === 'BULLISH' ? 'tag-bullish' :
                       t.direction === 'BEARISH' ? 'tag-bearish' : 'tag-neutral';
      trendTag = `<span class="trend-tag ${tagClass}">${t.direction} ${t.bullish_pct.toFixed(0)}% (${t.interval_minutes}m)</span>`;
    }

    div.innerHTML = `
      <span class="anomaly-symbol">${a.symbol.toUpperCase()}</span>
      &nbsp;$${Number(a.price).toLocaleString(undefined, {minimumFractionDigits: 2})}
      &nbsp;<span class="anomaly-sigma ${sigmaClass}">${a.sigma_level.toFixed(1)}σ</span>
      ${trendTag}
      &nbsp;<span style="color:#666">${time}</span>`;
    div.onclick = () => showPatterns(a);
    container.appendChild(div);
  });
}

// Similar patterns
function showPatterns(anomaly) {
  const container = document.getElementById('patternsList');
  if (!anomaly.similar_patterns || anomaly.similar_patterns.length === 0) {
    container.innerHTML = '<p class="empty-msg">No similar patterns found</p>';
    return;
  }

  let html = `<p style="font-size:12px;color:#888;margin-bottom:8px;">
    Patterns similar to ${anomaly.symbol.toUpperCase()} anomaly at
    ${new Date(anomaly.timestamp * 1000).toLocaleTimeString()}</p>`;

  // Trend summary cards
  if (anomaly.trend_summaries && anomaly.trend_summaries.length > 0) {
    html += '<div class="trend-box"><h3>TREND ANALYSIS (from similar patterns)</h3><div class="trend-row">';
    anomaly.trend_summaries.forEach(t => {
      const cls = t.direction === 'BULLISH' ? 'trend-bullish' :
                  t.direction === 'BEARISH' ? 'trend-bearish' : 'trend-neutral';
      html += `<div class="trend-card ${cls}">
        <div class="interval">${t.interval_minutes} min outlook</div>
        <div class="direction">${t.direction}</div>
        <div class="details">${t.num_bullish}/${t.num_patterns} bullish (${t.bullish_pct.toFixed(0)}%)</div>
        <div class="details">avg: ${t.avg_pct_change >= 0 ? '+' : ''}${t.avg_pct_change.toFixed(3)}%</div>
      </div>`;
    });
    html += '</div></div>';
  }

  // Individual patterns
  anomaly.similar_patterns.forEach(p => {
    const time = new Date(p.timestamp * 1000).toLocaleString();
    let movesHtml = '';
    if (p.subsequent_moves && p.subsequent_moves.length > 0) {
      movesHtml = '<br><span style="font-size:11px;color:#888;">After: </span>';
      movesHtml += p.subsequent_moves.map(m => {
        const cls = m.pct_change >= 0 ? 'move-pos' : 'move-neg';
        const sign = m.pct_change >= 0 ? '+' : '';
        return `<span class="${cls}">${m.interval_minutes}m: ${sign}${m.pct_change.toFixed(2)}%</span>`;
      }).join(' &nbsp;');
    }
    html += `<div class="pattern-entry">
      <strong>${p.symbol.toUpperCase()}</strong>
      @ $${Number(p.price).toLocaleString(undefined, {minimumFractionDigits: 2})}
      &mdash; ${time}
      &nbsp;<span class="sim">sim: ${p.similarity.toFixed(4)}</span>
      ${movesHtml}
    </div>`;
  });

  container.innerHTML = html;
}

// Uptime counter
setInterval(() => {
  const secs = Math.floor((Date.now() - startTime) / 1000);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  document.getElementById('uptimeText').textContent = `Uptime: ${m}m ${s}s`;
}, 1000);

// Start
connect();
</script>
</body>
</html>"""
