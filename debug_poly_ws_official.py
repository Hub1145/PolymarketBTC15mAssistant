import asyncio
import json
import aiohttp
import time
import os

async def test_poly_ws():
    url = "wss://ws-live-data.polymarket.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
    print(f"Connecting to: {url}")
    print(f"Using proxy: {proxy}")

    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.ws_connect(url, proxy=proxy) as ws:
                print("Connected to Polymarket WS")

                # Try subscribing to Chainlink Source
                filters = '{"symbol":"btc/usd"}'
                subscribe_msg = {
                    "action": "subscribe",
                    "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": filters}]
                }
                await ws.send_json(subscribe_msg)
                print(f"Sent subscription: {subscribe_msg}")

                # Ping loop
                async def ping():
                    while True:
                        await asyncio.sleep(5)
                        try:
                            await ws.send_str("PING")
                            # print("Sent PING")
                        except:
                            break
                asyncio.create_task(ping())

                start_time = time.time()
                while time.time() - start_time < 20:
                    try:
                        msg = await ws.receive(timeout=5)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            print(f"Received: {msg.data}")
                            if msg.data == "PONG":
                                continue
                            try:
                                data = json.loads(msg.data)
                                if data.get("topic") == "crypto_prices_chainlink":
                                    payload = data.get("payload", {})
                                    print(f"PRICE UPDATE: {payload.get('symbol')} -> {payload.get('value')}")
                            except Exception as e:
                                print(f"Parse error: {e}")
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("WS Closed")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"WS Error: {ws.exception()}")
                            break
                    except asyncio.TimeoutError:
                        print("Receive timeout, still waiting...")
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_poly_ws())
