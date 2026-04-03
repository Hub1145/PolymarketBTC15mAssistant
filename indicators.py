from typing import List, Optional, Dict

def clamp(x: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, x))

def compute_rsi(closes: List[float], period: int) -> Optional[float]:
    if not isinstance(closes, list) or len(closes) < period + 1:
        return None

    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        diff = cur - prev
        if diff > 0:
            gains += diff
        else:
            losses += -diff

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return clamp(rsi, 0.0, 100.0)

def sma(values: List[float], period: int) -> Optional[float]:
    if not isinstance(values, list) or len(values) < period:
        return None
    slice_vals = values[-period:]
    return sum(slice_vals) / period

def slope_last(values: List[float], points: int) -> Optional[float]:
    if not isinstance(values, list) or len(values) < points:
        return None
    slice_vals = values[-points:]
    first = slice_vals[0]
    last = slice_vals[-1]
    return (last - first) / (points - 1)

def ema(values: List[float], period: int) -> Optional[float]:
    if not isinstance(values, list) or len(values) < period:
        return None

    k = 2 / (period + 1)
    prev = values[0]
    for i in range(1, len(values)):
        prev = values[i] * k + prev * (1 - k)
    return prev

def compute_macd(closes: List[float], fast: int, slow: int, signal: int) -> Optional[Dict]:
    if not isinstance(closes, list) or len(closes) < slow + signal:
        return None

    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    if fast_ema is None or slow_ema is None:
        return None

    macd_line = fast_ema - slow_ema

    macd_series = []
    for i in range(len(closes)):
        sub = closes[: i + 1]
        f = ema(sub, fast)
        s = ema(sub, slow)
        if f is None or s is None:
            continue
        macd_series.append(f - s)

    signal_line = ema(macd_series, signal)
    if signal_line is None:
        return None

    hist = macd_line - signal_line
    last_hist = hist

    prev_hist = None
    if len(macd_series) >= signal + 1:
        prev_sub = macd_series[:-1]
        prev_signal = ema(prev_sub, signal)
        if prev_signal is not None:
             prev_hist = macd_series[-2] - prev_signal

    hist_series = []
    for i in range(len(macd_series)):
        sub_macd = macd_series[:i+1]
        sig = ema(sub_macd, signal)
        if sig is not None:
            hist_series.append(macd_series[i] - sig)

    return {
        "macd": macd_line,
        "signal": signal_line,
        "hist": hist,
        "histDelta": last_hist - prev_hist if prev_hist is not None else None,
        "hist_series": hist_series
    }

def compute_session_vwap(candles: List[Dict], start_time_ms: Optional[int] = None) -> Optional[float]:
    if not isinstance(candles, list) or len(candles) == 0:
        return None

    pv = 0.0
    v = 0.0
    for c in candles:
        if start_time_ms is not None and c["openTime"] < start_time_ms:
            continue
        tp = (c["high"] + c["low"] + c["close"]) / 3
        pv += tp * c["volume"]
        v += c["volume"]
    if v == 0:
        return None
    return pv / v

def compute_vwap_series(candles: List[Dict]) -> List[Optional[float]]:
    series = []
    for i in range(len(candles)):
        sub = candles[: i + 1]
        series.append(compute_session_vwap(sub))
    return series

def compute_heiken_ashi(candles: List[Dict]) -> List[Dict]:
    if not isinstance(candles, list) or len(candles) == 0:
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
    if not isinstance(ha_candles, list) or len(ha_candles) == 0:
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
