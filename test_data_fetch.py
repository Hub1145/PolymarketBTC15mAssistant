import asyncio
import json
import httpx
from config import settings

async def test_rest_api():
    async with httpx.AsyncClient() as client:
        # 1. Binance
        print("Testing Binance REST...")
        res = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={settings.SYMBOL}")
        print(f"Binance: {res.json()}")

        # 2. Polymarket Gamma
        print("Testing Polymarket Gamma...")
        res = await client.get(f"{settings.GAMMA_BASE_URL}/markets/{settings.POLYMARKET_SERIES_ID}")
        print(f"Polymarket Gamma: {res.status_code}")

        # 3. Polymarket CLOB
        print("Testing Polymarket CLOB...")
        # Just a health check or book
        res = await client.get(f"{settings.CLOB_BASE_URL}/health")
        print(f"Polymarket CLOB Health: {res.json()}")

if __name__ == "__main__":
    asyncio.run(test_rest_api())
