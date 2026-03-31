import asyncio
import json
import websockets
from typing import Optional, Callable, Dict
import time

class BinanceTradeStream:
    def __init__(self, symbol: str, on_update: Optional[Callable] = None):
        self.symbol = symbol.lower()
        self.on_update = on_update
        self.last_price = None
        self.last_ts = None
        self.closed = False

    async def start(self):
        url = f"wss://stream.binance.com:9443/ws/{self.symbol}@trade"
        while not self.closed:
            try:
                async with websockets.connect(url) as ws:
                    while not self.closed:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        p = float(data.get("p"))
                        self.last_price = p
                        self.last_ts = time.time()
                        if self.on_update:
                            await self.on_update({"price": self.last_price, "ts": self.last_ts})
            except Exception as e:
                if not self.closed:
                    await asyncio.sleep(1)

    def get_last(self):
        return {"price": self.last_price, "ts": self.last_ts}

    def close(self):
        self.closed = True

class PolymarketChainlinkStream:
    def __init__(self, ws_url: str, symbol_includes: str = "btc", on_update: Optional[Callable] = None):
        self.ws_url = ws_url
        self.symbol_includes = symbol_includes.lower()
        self.on_update = on_update
        self.last_price = None
        self.last_updated_at = None
        self.closed = False

    async def start(self):
        if not self.ws_url:
            return
        while not self.closed:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    subscribe_msg = {
                        "action": "subscribe",
                        "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    while not self.closed:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get("topic") != "crypto_prices_chainlink":
                            continue

                        payload = data.get("payload", {})
                        symbol = str(payload.get("symbol") or payload.get("pair") or payload.get("ticker") or "").lower()
                        if self.symbol_includes and self.symbol_includes not in symbol:
                            continue

                        price = float(payload.get("value") or payload.get("price") or payload.get("current") or payload.get("data"))
                        updated_at = float(payload.get("timestamp") or payload.get("updatedAt")) * 1000

                        self.last_price = price
                        self.last_updated_at = updated_at
                        if self.on_update:
                            await self.on_update({"price": self.last_price, "updatedAt": self.last_updated_at, "source": "polymarket_ws"})
            except Exception as e:
                if not self.closed:
                    await asyncio.sleep(1)

    def get_last(self):
        return {"price": self.last_price, "updatedAt": self.last_updated_at, "source": "polymarket_ws"}

    def close(self):
        self.closed = True
