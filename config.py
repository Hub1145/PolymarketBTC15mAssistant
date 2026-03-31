import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    SYMBOL: str = "BTCUSDT"
    BINANCE_BASE_URL: str = "https://api.binance.com"
    GAMMA_BASE_URL: str = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL: str = "https://clob.polymarket.com"

    POLL_INTERVAL_MS: int = 1000
    CANDLE_WINDOW_MINUTES: int = 15

    VWAP_SLOPE_LOOKBACK_MINUTES: int = 5
    RSI_PERIOD: int = 14
    RSI_MA_PERIOD: int = 14

    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9

    # Polymarket
    POLYMARKET_SLUG: str = os.getenv("POLYMARKET_SLUG", "")
    POLYMARKET_SERIES_ID: str = os.getenv("POLYMARKET_SERIES_ID", "10192")
    POLYMARKET_SERIES_SLUG: str = os.getenv("POLYMARKET_SERIES_SLUG", "btc-up-or-down-15m")
    POLYMARKET_AUTO_SELECT_LATEST: bool = os.getenv("POLYMARKET_AUTO_SELECT_LATEST", "true").lower() == "true"
    POLYMARKET_LIVE_DATA_WS_URL: str = os.getenv("POLYMARKET_LIVE_WS_URL", "wss://ws-live-data.polymarket.com")
    POLYMARKET_UP_LABEL: str = os.getenv("POLYMARKET_UP_LABEL", "Up")
    POLYMARKET_DOWN_LABEL: str = os.getenv("POLYMARKET_DOWN_LABEL", "Down")

    # Chainlink
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    POLYGON_RPC_URLS: List[str] = [url.strip() for url in os.getenv("POLYGON_RPC_URLS", "").split(",") if url.strip()]
    POLYGON_WSS_URL: str = os.getenv("POLYGON_WSS_URL", "")
    POLYGON_WSS_URLS: List[str] = [url.strip() for url in os.getenv("POLYGON_WSS_URLS", "").split(",") if url.strip()]
    CHAINLINK_BTC_USD_AGGREGATOR: str = os.getenv("CHAINLINK_BTC_USD_AGGREGATOR", "0xc907E116054Ad103354f2D350FD2514433D57F6f")

    # Proxy
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", os.getenv("http_proxy", ""))
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", os.getenv("https_proxy", ""))
    ALL_PROXY: str = os.getenv("ALL_PROXY", os.getenv("all_proxy", ""))

settings = Settings()
