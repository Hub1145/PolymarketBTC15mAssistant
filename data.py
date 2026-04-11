import httpx
from config import settings
from typing import List, Dict, Optional
from net_utils import get_proxy_url_for

def to_number(x) -> Optional[float]:
    try:
        n = float(x)
        return n
    except (TypeError, ValueError):
        return None

async def fetch_klines(symbol: str, interval: str, limit: int) -> List[Dict]:
    """
    Fetch OHLCV data from Kraken (fallback for Binance if blocked).
    Kraken uses different interval mapping and symbol format.
    """
    # Mapping intervals: 1m -> 1, 5m -> 5, 15m -> 15, 1h -> 60
    k_interval = 1
    if interval == "5m": k_interval = 5
    elif interval == "15m": k_interval = 15
    elif interval == "1h": k_interval = 60

    # Kraken symbol for BTCUSDT is usually XBTUSDT or XBTUSD
    k_symbol = "XBTUSDT" if "USDT" in symbol.upper() else "XBTUSD"

    url = "https://api.kraken.com/0/public/OHLC"
    params = {
        "pair": k_symbol,
        "interval": k_interval
    }

    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        try:
            res = await client.get(url, params=params)
            res.raise_for_status()
            res_data = res.json()

            if res_data.get("error"):
                # Fallback to Binance if Kraken fails
                raise Exception(f"Kraken error: {res_data['error']}")

            # Get the result key (dynamically as it contains the symbol)
            result = res_data.get("result", {})
            pair_key = next((k for k in result.keys() if k != "last"), None)
            if not pair_key:
                raise Exception("Kraken result empty")

            ohlcv = result[pair_key]
            # Kraken return: [time, open, high, low, close, vwap, volume, count]
            # Limited by Kraken to 720 bars
            return [{
                "openTime": int(k[0]) * 1000,
                "open": to_number(k[1]),
                "high": to_number(k[2]),
                "low": to_number(k[3]),
                "close": to_number(k[4]),
                "volume": to_number(k[6]),
                "closeTime": (int(k[0]) + k_interval * 60) * 1000 - 1
            } for k in ohlcv[-limit:]]

        except Exception as e:
            print(f"Kraken fetch failed, trying Binance: {e}")
            # Binance original logic
            url = f"{settings.BINANCE_BASE_URL}/api/v3/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
            return [{
                "openTime": int(k[0]),
                "open": to_number(k[1]),
                "high": to_number(k[2]),
                "low": to_number(k[3]),
                "close": to_number(k[4]),
                "volume": to_number(k[5]),
                "closeTime": int(k[6])
            } for k in data]

async def fetch_last_price(symbol: str) -> Optional[float]:
    """
    Fetch last price from Kraken (fallback for Binance).
    """
    k_symbol = "XBTUSDT" if "USDT" in symbol.upper() else "XBTUSD"
    url = "https://api.kraken.com/0/public/Ticker"
    params = {"pair": k_symbol}
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        try:
            res = await client.get(url, params=params)
            res.raise_for_status()
            res_data = res.json()
            if res_data.get("error"): raise Exception(res_data["error"])

            result = res_data["result"]
            pair_key = next(iter(result))
            # 'c' is last trade: [price, whole_lot_volume]
            return to_number(result[pair_key]["c"][0])
        except Exception as e:
            print(f"Kraken ticker failed, trying Binance: {e}")
            url = f"{settings.BINANCE_BASE_URL}/api/v3/ticker/price"
            params = {"symbol": symbol}
            res = await client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
            return to_number(data["price"])

async def fetch_market_by_slug(slug: str) -> Optional[Dict]:
    url = f"{settings.GAMMA_BASE_URL}/markets"
    params = {"slug": slug}
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
    market = data[0] if isinstance(data, list) and data else data
    return market if market else None

async def fetch_live_events_by_series_id(series_id: str, limit: int = 20) -> List[Dict]:
    url = f"{settings.GAMMA_BASE_URL}/events"
    params = {
        "series_id": series_id,
        "active": "true",
        "closed": "false",
        "limit": limit
    }
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
    return data if isinstance(data, list) else []

async def fetch_available_15m_series() -> List[Dict]:
    url = f"{settings.GAMMA_BASE_URL}/events"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 100,
        "tag_id": "102467" # 15M tag
    }
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        try:
            res = await client.get(url, params=params)
            res.raise_for_status()
            events = res.json()
        except:
            events = []

    series_map = {}
    # Common hardcoded series that are known to work
    defaults = {
        "10192": "Bitcoin Up or Down 15m",
        "10212": "Ethereum Up or Down 15m"
    }
    for sid, name in defaults.items():
        series_map[sid] = {"series_id": sid, "title": name}

    for e in events:
        series_slug = e.get("seriesSlug", "")
        if "up-or-down-15m" in series_slug:
            sid = e.get("series_id")
            if not sid and e.get("series") and isinstance(e["series"], list) and len(e["series"]) > 0:
                sid = e["series"][0].get("id")

            if sid:
                asset = series_slug.split("-")[0].upper()
                series_map[str(sid)] = {
                    "series_id": str(sid),
                    "title": f"{asset} Up or Down 15m",
                    "slug": series_slug
                }

    return sorted(list(series_map.values()), key=lambda x: x["title"])

def flatten_event_markets(events: List[Dict]) -> List[Dict]:
    out = []
    for e in events:
        markets = e.get("markets", [])
        if isinstance(markets, list):
            out.extend(markets)
    return out

async def fetch_clob_price(token_id: str, side: str) -> Optional[float]:
    url = f"{settings.CLOB_BASE_URL}/price"
    params = {"token_id": token_id, "side": side}
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
    return to_number(data.get("price"))

async def fetch_order_book(token_id: str) -> Dict:
    url = f"{settings.CLOB_BASE_URL}/book"
    params = {"token_id": token_id}
    proxy = get_proxy_url_for(url)
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        return res.json()

def summarize_order_book(book: Dict, depth_levels: int = 5) -> Dict:
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    best_bid = None
    if bids:
        for lvl in bids:
            p = to_number(lvl.get("price"))
            if p is not None:
                best_bid = max(best_bid, p) if best_bid is not None else p

    best_ask = None
    if asks:
        for lvl in asks:
            p = to_number(lvl.get("price"))
            if p is not None:
                best_ask = min(best_ask, p) if best_ask is not None else p

    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None

    bid_liquidity = sum(to_number(lvl.get("size")) or 0 for lvl in bids[:depth_levels])
    ask_liquidity = sum(to_number(lvl.get("size")) or 0 for lvl in asks[:depth_levels])

    return {
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "spread": spread,
        "bidLiquidity": bid_liquidity,
        "askLiquidity": ask_liquidity
    }
