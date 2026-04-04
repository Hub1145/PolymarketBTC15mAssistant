import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from typing import List, Optional, Dict
from utils import clamp

def compute_rsi(closes: List[float], period: int) -> Optional[float]:
    if not closes or len(closes) < period:
        return None
    series = pd.Series(closes)
    rsi = RSIIndicator(close=series, window=period).rsi()
    if rsi.empty: return None
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else None

def compute_ema_series(values: List[float], period: int) -> List[Optional[float]]:
    if not values: return []
    if len(values) < period:
        return [None] * len(values)
    series = pd.Series(values)
    ema = EMAIndicator(close=series, window=period).ema_indicator()
    return [float(x) if not pd.isna(x) else None for x in ema.tolist()]

def compute_macd_series(closes: List[float], fast: int, slow: int, signal: int) -> List[Optional[float]]:
    if not closes or len(closes) < slow:
        return [None] * len(closes)
    try:
        series = pd.Series(closes)
        macd_ind = MACD(close=series, window_fast=fast, window_slow=slow, window_sign=signal)
        h_series = macd_ind.macd_diff()
        return [float(x) if not pd.isna(x) else None for x in h_series.tolist()]
    except:
        return [None] * len(closes)

def compute_macd(closes: List[float], fast: int, slow: int, signal: int) -> Optional[Dict]:
    if not closes or len(closes) < slow:
        return None
    try:
        series = pd.Series(closes)
        macd_ind = MACD(close=series, window_fast=fast, window_slow=slow, window_sign=signal)

        m_series = macd_ind.macd()
        s_series = macd_ind.macd_signal()
        h_series = macd_ind.macd_diff()

        if m_series.empty or s_series.empty or h_series.empty:
            return None

        macd_line = m_series.iloc[-1]
        signal_line = s_series.iloc[-1]
        hist = h_series.iloc[-1]

        # Prev hist for delta
        prev_hist = h_series.iloc[-2] if len(h_series) > 1 else None

        return {
            "macd": float(macd_line) if not pd.isna(macd_line) else None,
            "signal": float(signal_line) if not pd.isna(signal_line) else None,
            "hist": float(hist) if not pd.isna(hist) else None,
            "histDelta": float(hist - prev_hist) if not pd.isna(hist) and not pd.isna(prev_hist) else None
        }
    except:
        return None

def compute_heiken_ashi(candles: List[Dict]) -> List[Dict]:
    if not candles:
        return []

    ha = []
    for i in range(len(candles)):
        c = candles[i]
        ha_close = (c["open"] + c["high"] + c["low"] + c["close"]) / 4

        if i > 0:
            prev = ha[i - 1]
            ha_open = (prev["open"] + prev["close"]) / 2
        else:
            ha_open = (c["open"] + c["close"]) / 2

        ha_high = max(c["high"], ha_open, ha_close)
        ha_low = min(c["low"], ha_open, ha_close)

        ha.append({
            "open": ha_open,
            "high": ha_high,
            "low": ha_low,
            "close": ha_close,
            "isGreen": ha_close >= ha_open,
            "body": abs(ha_close - ha_open)
        })
    return ha

def count_consecutive(ha_candles: List[Dict]) -> Dict:
    if not ha_candles:
        return {"color": None, "count": 0}

    last = ha_candles[-1]
    target = "green" if last["isGreen"] else "red"

    count = 0
    for i in range(len(ha_candles) - 1, -1, -1):
        c = ha_candles[i]
        color = "green" if c["isGreen"] else "red"
        if color != target:
            break
        count += 1

    return {"color": target, "count": count}

def count_consecutive_hist(hist_series: List[float]) -> Dict:
    if not hist_series:
        return {"direction": None, "count": 0}

    last = hist_series[-1]
    if last is None or pd.isna(last): return {"direction": None, "count": 0}

    target = "up" if last > 0 else "down"

    count = 0
    for i in range(len(hist_series) - 1, -1, -1):
        val = hist_series[i]
        if val is None or pd.isna(val): break
        direction = "up" if val > 0 else "down"
        if direction != target:
            break
        count += 1

    return {"direction": target, "count": count}
