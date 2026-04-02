import asyncio
import json
import aiohttp
import time

async def debug_polymarket_ws():
    url = "wss://ws-live-data.polymarket.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    print(f"Connecting to {url}...")
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.ws_connect(url) as ws:
                print("Connected. Sending subscription...")
                subscribe_msg = {
                    "action": "subscribe",
                    "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}]
                }
                await ws.send_json(subscribe_msg)

                print("Waiting for messages...")
                start = time.time()
                while time.time() - start < 30:
                    msg = await ws.receive()
                    print(f"Msg Type: {msg.type}")
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"RAW DATA: {msg.data[:200]}...")
                        try:
                            data = json.loads(msg.data)
                            print(f"Topic: {data.get('topic')}")
                        except Exception as e:
                            print(f"JSON ERROR: {e}")
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        print(f"BINARY DATA: {msg.data[:10]}...")
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print("WS Closed")
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print("WS Error")
                        break
    except Exception as e:
        print(f"Debug Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_polymarket_ws())
