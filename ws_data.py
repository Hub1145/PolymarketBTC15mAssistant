import asyncio
import json
import websockets
import time
from typing import Optional, Callable, Dict, List
from config import settings
from net_utils import get_proxy_url_for

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
                # Note: standard websockets library doesn't easily support proxies
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
                print(f"WS Error (Binance): {e}")
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
                print(f"WS Error (Polymarket): {e}")
                if not self.closed:
                    await asyncio.sleep(1)

    def get_last(self):
        return {"price": self.last_price, "updatedAt": self.last_updated_at, "source": "polymarket_ws"}

    def close(self):
        self.closed = True

class ChainlinkPriceStream:
    def __init__(self, aggregator: str, decimals: int = 8, on_update: Optional[Callable] = None):
        self.aggregator = aggregator
        self.decimals = decimals
        self.on_update = on_update
        self.last_price = None
        self.last_updated_at = None
        self.closed = False
        self.wss_urls = settings.POLYGON_WSS_URLS + ([settings.POLYGON_WSS_URL] if settings.POLYGON_WSS_URL else [])

    async def start(self):
        if not self.wss_urls or not self.aggregator:
            return

        url_idx = 0
        while not self.closed:
            url = self.wss_urls[url_idx % len(self.wss_urls)]
            url_idx += 1
            try:
                async with websockets.connect(url) as ws:
                    sub_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": [
                            "logs",
                            {
                                "address": self.aggregator,
                                "topics": ["0x05598845ccd9c46647361c770d3023029a3514781ca1029c91d84f2913e79435"] # AnswerUpdated topic
                            }
                        ]
                    }
                    await ws.send(json.dumps(sub_msg))

                    while not self.closed:
                        msg = await ws.recv()
                        data = json.loads(msg)

                        if data.get("method") == "eth_subscription":
                            log = data.get("params", {}).get("result", {})
                            topics = log.get("topics", [])
                            if len(topics) >= 2:
                                answer = int(topics[1], 16)
                                if answer >= 2**255:
                                    answer -= 2**256

                                self.last_price = answer / (10 ** self.decimals)
                                data_hex = log.get("data", "0x")
                                if len(data_hex) >= 66:
                                    self.last_updated_at = int(data_hex[2:66], 16) * 1000

                                if self.on_update:
                                    await self.on_update({"price": self.last_price, "updatedAt": self.last_updated_at, "source": "chainlink_ws"})
            except Exception as e:
                print(f"WS Error (Chainlink): {e}")
                if not self.closed:
                    await asyncio.sleep(1)

    def get_last(self):
        return {"price": self.last_price, "updatedAt": self.last_updated_at, "source": "chainlink_ws"}

    def close(self):
        self.closed = True
