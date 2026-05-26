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

If you are seeing errors related to Node.js or `npm run start`, it is because Render is auto-detecting the old environment. **You must manually set the runtime to Python.**

### Recommended: Use `render.yaml`
The repository includes a `render.yaml`. When creating a new blueprint on Render, it will automatically set the correct environment.

### Manual Setup
1. Create a **Web Service** on Render.
2. Under **Runtime**, explicitly select **Python 3**.
3. Set the following commands:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8000`
4. Add any necessary environment variables (optional).

## Safety

This is not financial advice. Use at your own risk.
