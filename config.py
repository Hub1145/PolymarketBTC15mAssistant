import os
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Dict, Any, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    MODE: str = "paper"  # "paper" or "live"
    PAPER_BALANCE_USD: float = 1000.0
    PRIVATE_KEY: str = ""

    SYMBOL: str = "BTCUSDT"
    BINANCE_BASE_URL: str = "https://api.binance.com"
    GAMMA_BASE_URL: str = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL: str = "https://clob.polymarket.com"

    POLL_INTERVAL_MS: int = 1000
    CANDLE_WINDOW_MINUTES: int = 15

    RISK_TYPE: str = "percent"  # "percent" or "fixed"
    RISK_VALUE: float = 10.0

    VWAP_SLOPE_LOOKBACK_MINUTES: int = 5
    RSI_PERIOD: int = 14
    RSI_MA_PERIOD: int = 14

    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9

    # SuperTrend Cluster Parameters
    ST_CONSENSUS_THRESHOLD: float = 0.60
    ST_BASE_INDEX: int = 3

    ST1_ATR_LEN: int = 7
    ST1_FACTOR: float = 1.5
    ST1_MA_TYPE: str = "EMA"
    ST1_MA_LEN: int = 3
    ST1_WEIGHT: float = 1.0

    ST2_ATR_LEN: int = 10
    ST2_FACTOR: float = 2.0
    ST2_MA_TYPE: str = "EMA"
    ST2_MA_LEN: int = 5
    ST2_WEIGHT: float = 1.0

    ST3_ATR_LEN: int = 14
    ST3_FACTOR: float = 2.5
    ST3_MA_TYPE: str = "SMA"
    ST3_MA_LEN: int = 8
    ST3_WEIGHT: float = 1.2

    ST4_ATR_LEN: int = 21
    ST4_FACTOR: float = 3.0
    ST4_MA_TYPE: str = "WMA"
    ST4_MA_LEN: int = 13
    ST4_WEIGHT: float = 1.4

    ST5_ATR_LEN: int = 34
    ST5_FACTOR: float = 4.0
    ST5_MA_TYPE: str = "HMA"
    ST5_MA_LEN: int = 21
    ST5_WEIGHT: float = 1.6

    def get_st_params(self) -> Dict[str, Any]:
        return {
            "consensus_threshold": self.ST_CONSENSUS_THRESHOLD,
            "base_st_index": self.ST_BASE_INDEX,
            "st1_atr_len": self.ST1_ATR_LEN, "st1_factor": self.ST1_FACTOR, "st1_ma_type": self.ST1_MA_TYPE, "st1_ma_len": self.ST1_MA_LEN, "st1_weight": self.ST1_WEIGHT,
            "st2_atr_len": self.ST2_ATR_LEN, "st2_factor": self.ST2_FACTOR, "st2_ma_type": self.ST2_MA_TYPE, "st2_ma_len": self.ST2_MA_LEN, "st2_weight": self.ST2_WEIGHT,
            "st3_atr_len": self.ST3_ATR_LEN, "st3_factor": self.ST3_FACTOR, "st3_ma_type": self.ST3_MA_TYPE, "st3_ma_len": self.ST3_MA_LEN, "st3_weight": self.ST3_WEIGHT,
            "st4_atr_len": self.ST4_ATR_LEN, "st4_factor": self.ST4_FACTOR, "st4_ma_type": self.ST4_MA_TYPE, "st4_ma_len": self.ST4_MA_LEN, "st4_weight": self.ST4_WEIGHT,
            "st5_atr_len": self.ST5_ATR_LEN, "st5_factor": self.ST5_FACTOR, "st5_ma_type": self.ST5_MA_TYPE, "st5_ma_len": self.ST5_MA_LEN, "st5_weight": self.ST5_WEIGHT,
        }

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
    POLYGON_WSS_URL: str = os.getenv("POLYGON_WSS_URL", "wss://polygon-bor-rpc.publicnode.com")
    POLYGON_WSS_URLS: List[str] = [url.strip() for url in os.getenv("POLYGON_WSS_URLS", "").split(",") if url.strip()]
    CHAINLINK_BTC_USD_AGGREGATOR: str = os.getenv("CHAINLINK_BTC_USD_AGGREGATOR", "0xc907E116054Ad103354f2D350FD2514433D57F6f")

    CHAINLINK_AGGREGATORS: Dict[str, str] = {
        "BTC": "0xc907E116054Ad103354f2D350FD2514433D57F6f",
        "ETH": "0xF9680D99D6C9589e2a93a78A04A279e509205945",
        "SOL": "0x39771505D18301D239916F4C88367A6010F7D2e3",
        "XRP": "0x3454796324D6469C3110996E2E10972688045F19",
        "DOGE": "0xbAf93Ba318f77363f82E8896a2E830206121D506",
        "BNB": "0x82a6C67606bdc0409f959f60608226064223A57c"
    }

    def get_aggregator(self, symbol: str) -> str:
        s = symbol.upper()
        if s.endswith("USDT"): s = s[:-4]
        return self.CHAINLINK_AGGREGATORS.get(s, self.CHAINLINK_BTC_USD_AGGREGATOR)

    # Proxy
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", os.getenv("http_proxy", ""))
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", os.getenv("https_proxy", ""))
    ALL_PROXY: str = os.getenv("ALL_PROXY", os.getenv("all_proxy", ""))

def load_settings():
    base_settings = Settings()
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)

            if "mode" in config_data: base_settings.MODE = config_data["mode"]
            if "paper_balance_usd" in config_data: base_settings.PAPER_BALANCE_USD = config_data["paper_balance_usd"]
            if "private_key" in config_data: base_settings.PRIVATE_KEY = config_data["private_key"]

            if "polymarket" in config_data:
                poly = config_data["polymarket"]
                if "gamma_base_url" in poly: base_settings.GAMMA_BASE_URL = poly["gamma_base_url"]
                if "clob_base_url" in poly: base_settings.CLOB_BASE_URL = poly["clob_base_url"]
                if "live_ws_url" in poly: base_settings.POLYMARKET_LIVE_DATA_WS_URL = poly["live_ws_url"]
                if "series_id" in poly: base_settings.POLYMARKET_SERIES_ID = poly["series_id"]
                if "series_slug" in poly: base_settings.POLYMARKET_SERIES_SLUG = poly["series_slug"]
                if "auto_select_latest" in poly: base_settings.POLYMARKET_AUTO_SELECT_LATEST = poly["auto_select_latest"]
                if "up_label" in poly: base_settings.POLYMARKET_UP_LABEL = poly["up_label"]
                if "down_label" in poly: base_settings.POLYMARKET_DOWN_LABEL = poly["down_label"]

            if "trading" in config_data:
                trading = config_data["trading"]
                if "symbol" in trading: base_settings.SYMBOL = trading["symbol"]
                if "binance_base_url" in trading: base_settings.BINANCE_BASE_URL = trading["binance_base_url"]
                if "candle_window_minutes" in trading: base_settings.CANDLE_WINDOW_MINUTES = trading["candle_window_minutes"]
                if "poll_interval_ms" in trading: base_settings.POLL_INTERVAL_MS = trading["poll_interval_ms"]
                if "risk_type" in trading: base_settings.RISK_TYPE = trading["risk_type"]
                if "risk_value" in trading: base_settings.RISK_VALUE = trading["risk_value"]

            if "chainlink" in config_data:
                cl = config_data["chainlink"]
                if "polygon_rpc_url" in cl: base_settings.POLYGON_RPC_URL = cl["polygon_rpc_url"]
                if "polygon_wss_url" in cl: base_settings.POLYGON_WSS_URL = cl["polygon_wss_url"]
                if "btc_usd_aggregator" in cl: base_settings.CHAINLINK_BTC_USD_AGGREGATOR = cl["btc_usd_aggregator"]

        except Exception as e:
            print(f"Warning: Failed to load config.json: {e}")

    return base_settings

settings = load_settings()
