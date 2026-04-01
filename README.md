# Polymarket BTC 15m Assistant (Python FastAPI)

A real-time trading assistant for Polymarket **"Bitcoin Up or Down" 15-minute** markets, ported to Python and FastAPI.

It features a **Real-Time Web Dashboard** with TA indicators, trade history, and paper/live trading modes.

## Features

- Real-time Web Dashboard (FastAPI + Jinja2 + Alpine.js)
- Technical Indicators: RSI, MACD, Heiken Ashi, VWAP
- Trade Execution: Paper Trading simulation vs Live Mode toggle
- Data Sources: Binance, Polymarket (Gamma/CLOB), Chainlink (WebSocket + RPC)
- Proxy Support: Global HTTP/HTTPS/SOCKS proxy configuration
- Logging: CSV signal logging

## Requirements

- Python **3.11+**
- pip (comes with Python)

## Local Run

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure `config.json`

Set your trading mode, risk preferences, and optional private key in `config.json`.

### 3) Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Access the dashboard at `http://localhost:8000`.

## Docker

```bash
docker build -t polymarket-assistant .
docker run -p 8000:8000 polymarket-assistant
```

## Deployment on Render

This project includes a `render.yaml` for easy deployment on [Render](https://render.com).

1. Connect your GitHub repository to Render.
2. Select **Blueprint** and it will automatically use the `render.yaml` configuration.
3. Or create a **Web Service**, choose the **Python** runtime, and set the following:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8000`

## Safety

This is not financial advice. Use at your own risk.
