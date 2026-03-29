# Crypto Market Anomaly Detection System

Real-time crypto anomaly detection using TurboQuant vector quantization (arXiv:2504.19874).

Vectorizes price movements from Binance WebSocket feeds, quantizes them with TurboQuant (random rotation + Lloyd-Max scalar quantization), stores in an in-memory vector DB, and detects anomalies via nearest-neighbor distance analysis.

## Architecture

```
[Binance WebSocket] → [Feature Extractor] → [TurboQuant Encoder] → [Vector DB (in-memory)]
                                                                           ↓
                                                                   [Nearest Neighbor Search]
                                                                           ↓
                                                                   [Anomaly Score + Alert]
                                                                           ↓
                                                                   [Dashboard (FastAPI + WebSocket)]
```

## Quick Start

```bash
cd crypto-anomaly
pip install -r requirements.txt
python main.py
```

Dashboard: http://localhost:8765

## Features

- **Real-time data**: Binance public WebSocket (no API key needed)
- **TurboQuant compression**: 128-dim vectors quantized to 2-bit per coordinate (~32 bytes/vector)
- **Fast NN search**: Brute-force on cached decoded vectors, <10ms for 100K vectors
- **Anomaly detection**: Statistical distance-based (>2σ from historical mean)
- **Live dashboard**: Dark theme, Chart.js gauges, sparklines, anomaly feed
- **Low memory**: <500MB for 100K vectors

## Configuration

Edit `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbols` | BTC, ETH + 10 altcoins | Binance trading pairs |
| `kline_interval` | `1m` | Candle interval |
| `bit_width` | `2` | TurboQuant bits per coordinate |
| `max_vectors` | `100,000` | Vector store capacity |
| `sigma_threshold` | `2.0` | Anomaly detection threshold |
| `port` | `8765` | Dashboard port |

## Modules

| File | Description |
|------|-------------|
| `main.py` | Async orchestrator, signal handling |
| `config.py` | All configurable parameters |
| `data_collector.py` | Binance WebSocket + REST bootstrap |
| `feature_extractor.py` | 60 candles → 128-dim unit-norm vector |
| `turboquant.py` | Algorithm 1 (MSE) & Algorithm 2 (Inner Product) |
| `vector_store.py` | Ring buffer, cached NN search |
| `anomaly_detector.py` | KNN distance-based anomaly scoring |
| `dashboard.py` | FastAPI + WebSocket + inline HTML/JS |

## TurboQuant Details

Based on the TurboQuant paper (arXiv:2504.19874):

- **Random rotation** via Haar-distributed orthogonal matrix (QR decomposition)
- **Lloyd-Max scalar quantization** on rotated coordinates (≈ Gaussian after rotation)
- **b=2**: MSE ≈ 0.117, 4 quantization levels per coordinate
- **b=4**: MSE ≈ 0.009, 16 levels (optional, higher accuracy)
- Inner product preservation via QJL residual correction (Algorithm 2)
