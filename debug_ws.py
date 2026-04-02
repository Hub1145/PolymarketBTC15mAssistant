import asyncio
import json
import websockets
import time

async def test_polymarket_ws():
    url = "wss://ws-live-data.polymarket.com"
    # Polymarket WS often requires a specific user agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    print(f"Connecting to {url} with headers...")
    try:
        async with websockets.connect(url, extra_headers=headers) as ws:
            print("Connected. Subscribing...")
            subscribe_msg = {
                "action": "subscribe",
                "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}]
            }
            await ws.send(json.dumps(subscribe_msg))

            print("Waiting for messages (30s)...")
            start = time.time()
            while time.time() - start < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(msg)
                    print(f"Received topic: {data.get('topic')}")
                    if data.get("topic") == "crypto_prices_chainlink":
                        payload = data.get("payload")
                        print(f"Payload: {payload}")
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                except Exception as e:
                    print(f"Error receiving: {e}")
    except Exception as e:
        print(f"Connection error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_polymarket_ws())
