# Polymarket BTC 15m Assistant (Python FastAPI)

A real-time trading assistant for Polymarket **"Bitcoin Up or Down" 15-minute** markets, ported to Python and FastAPI.

It combines:
- Polymarket market selection + UP/DOWN prices + liquidity
- Polymarket live WS **Chainlink BTC/USD CURRENT PRICE**
- Fallback to on-chain Chainlink (Polygon) via HTTP RPC
- Binance spot price for reference
- Short-term TA snapshot (Heiken Ashi, RSI, MACD, VWAP, Delta 1/3m)
- A simple live **Predict (LONG/SHORT %)** derived from the assistant’s current TA scoring

## Requirements

- Python **3.11+**
- pip (comes with Python)

## Run from terminal

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) (Optional) Set environment variables

You can run without extra config (defaults are included), but for more stable Chainlink fallback it’s recommended to set at least one Polygon RPC.

```bash
export POLYGON_RPC_URL="https://polygon-rpc.com"
export POLYGON_RPC_URLS="https://polygon-rpc.com,https://rpc.ankr.com/polygon"
```

### 3) Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker

### Build and Run

```bash
docker build -t polymarket-assistant .
docker run -p 8000:8000 polymarket-assistant
```

## API Endpoints

- `GET /` - Returns the latest analysis, market data, and predictions.
- `GET /health` - Returns the service health status and last update timestamp.

## Notes / Troubleshooting

- Ensure you have a stable internet connection for WebSocket price streams.
- If no Chainlink updates are visible, verify your Polygon RPC URLs.

## Safety

This is not financial advice. Use at your own risk.
