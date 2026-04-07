import pandas as pd
import numpy as np
import time
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator, WMAIndicator
from ta.volatility import AverageTrueRange
from typing import List, Optional, Dict, Any
from utils import clamp
from typing import Dict, Any, List, Optional

def sma(series: pd.Series, period: int) -> pd.Series:
    return SMAIndicator(close=series, window=period).sma_indicator()

def ema(series: pd.Series, period: int) -> pd.Series:
    return EMAIndicator(close=series, window=period).ema_indicator()

def wma(series: pd.Series, period: int) -> pd.Series:
    return WMAIndicator(close=series, window=period).wma()

def hma(series: pd.Series, period: int) -> pd.Series:
    half_len = period // 2
    sqrt_len = int(np.sqrt(period))
    wma_half = wma(series, half_len)
    wma_full = wma(series, period)
    diff = 2 * wma_half - wma_full
    return wma(diff, sqrt_len)

def lsma(series: pd.Series, period: int) -> pd.Series:
    def linreg(x):
        n = len(x)
        weights = np.arange(n)
        slope, intercept = np.polyfit(weights, x, 1)
        return slope * (n - 1) + intercept
    return series.rolling(period).apply(linreg, raw=True)

def rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0/period, adjust=False).mean()

def compute_ma(ma_type: str, series: pd.Series, period: int) -> pd.Series:
    t = ma_type.upper()
    if t == 'SMA': return sma(series, period)
    if t == 'EMA': return ema(series, period)
    if t == 'WMA': return wma(series, period)
    if t == 'HMA': return hma(series, period)
    if t == 'LSMA': return lsma(series, period)
    if t == 'RMA': return rma(series, period)
    return sma(series, period)

def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    return AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=period).average_true_range()

def compute_supertrend_base(df: pd.DataFrame, src: pd.Series, atr_len: int, factor: float) -> tuple:
    atr = compute_atr(df, atr_len)

    upper_band_basic = src + factor * atr
    lower_band_basic = src - factor * atr

    upper_band_vals = upper_band_basic.values.copy()
    lower_band_vals = lower_band_basic.values.copy()
    src_vals = src.values

    for i in range(1, len(src)):
        if np.isnan(upper_band_vals[i-1]): continue

        if upper_band_basic.values[i] < upper_band_vals[i-1] or src_vals[i-1] > upper_band_vals[i-1]:
            upper_band_vals[i] = upper_band_basic.values[i]
        else:
            upper_band_vals[i] = upper_band_vals[i-1]

        if lower_band_basic.values[i] > lower_band_vals[i-1] or src_vals[i-1] < lower_band_vals[i-1]:
            lower_band_vals[i] = lower_band_basic.values[i]
        else:
            lower_band_vals[i] = lower_band_vals[i-1]

    direction = np.ones(len(src))
    for i in range(1, len(src)):
        if direction[i-1] == -1 and src_vals[i] > upper_band_vals[i-1]:
            direction[i] = 1
        elif direction[i-1] == 1 and src_vals[i] < lower_band_vals[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]

    supertrend = np.where(direction == 1, lower_band_vals, upper_band_vals)
    return supertrend, direction

def compute_supertrend_cluster(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes the SuperTrend Cluster regime following Zeiierman's Pine Script logic.
    """
    if df.empty or len(df) < 50: # Minimum candles for HMA/LSMA/ATR
        return {"regime": None, "strength": None, "scBu": None, "scBe": None}

    # Pine Script uses hlc3 as source
    src = (df['high'] + df['low'] + df['close']) / 3

    sts = []
    directions = []

    # Loop through 5 SuperTrend configurations
    for i in range(1, 6):
        ma_type = params.get(f'st{i}_ma_type', 'SMA')
        ma_len = params.get(f'st{i}_ma_len', 10)
        atr_len = params.get(f'st{i}_atr_len', 10)
        factor = params.get(f'st{i}_factor', 3.0)

        ma_src = compute_ma(ma_type, src, ma_len)
        st_val, d_val = compute_supertrend_base(df, ma_src, atr_len, factor)
        sts.append(st_val)
        directions.append(d_val)

    weights = [params.get(f'st{i}_weight', 1.0) for i in range(1, 6)]
    w_sum = sum(weights)

    thr = params.get('consensus_threshold', 0.6)
    base_idx = params.get('base_st_index', 3) - 1 # 0-indexed

    n_bars = len(src)
    regimes = np.zeros(n_bars)
    sc_bus = np.zeros(n_bars)
    sc_bes = np.zeros(n_bars)

    current_d_last = 0.0

    for i in range(n_bars):
        w_bu = 0.0
        w_be = 0.0
        for j in range(5):
            d = directions[j][i]
            w = weights[j]
            if d > 0:
                w_bu += w
            elif d < 0:
                w_be += w

        sc_bu = w_bu / w_sum if w_sum > 0 else 0.5
        sc_be = w_be / w_sum if w_sum > 0 else 0.5
        sc_bus[i] = sc_bu
        sc_bes[i] = sc_be

        base_d = directions[base_idx][i]
        is_bu = sc_bu >= thr
        is_be = sc_be >= thr

        ok_bu = is_bu and base_d > 0
        ok_be = is_be and base_d < 0

        if ok_bu and not ok_be:
            current_d_last = 1.0
        elif ok_be and not ok_bu:
            current_d_last = -1.0

        regimes[i] = current_d_last

    return {
        "regime": regimes[-1], # 1 Bull, -1 Bear, 0 Neutral
        "strength": abs(sc_bus[-1] - sc_bes[-1]),
        "scBu": sc_bus[-1],
        "scBe": sc_bes[-1]
    }

def detect_cvd_divergence(cvd_history: List[tuple], period_seconds: int = 300) -> Dict[str, Any]:
    """
    Detects divergence between CVD and Price.
    cvd_history is a list of (timestamp, cvd, price)
    """
    if len(cvd_history) < 2:
        return {"divergence": "NONE", "cvd_slope": 0, "price_slope": 0}

    now = time.time()
    relevant = [x for x in cvd_history if now - x[0] <= period_seconds]
    if len(relevant) < 10:
        return {"divergence": "NONE", "cvd_slope": 0, "price_slope": 0}

    # Calculate slopes via linear regression
    ts = [x[0] - relevant[0][0] for x in relevant]
    cvds = [x[1] for x in relevant]
    prices = [x[2] for x in relevant]

    cvd_slope, _ = np.polyfit(ts, cvds, 1)
    price_slope, _ = np.polyfit(ts, prices, 1)

    # Normalize slopes to compare direction
    div = "NONE"
    if price_slope > 0 and cvd_slope < 0:
        div = "BEARISH" # Price rising, selling pressure aggressive
    elif price_slope < 0 and cvd_slope > 0:
        div = "BULLISH" # Price falling, buying pressure aggressive

    return {
        "divergence": div,
        "cvd_slope": cvd_slope,
        "price_slope": price_slope,
        "cvd_delta": cvds[-1] - cvds[0]
    }

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
        return [float(x) if not pd.isna(x) and not np.isnan(x) else None for x in h_series.tolist()]
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

        def safe_float(v):
            if v is None or pd.isna(v) or np.isnan(v): return None
            return float(v)

        h_delta = None
        if hist is not None and prev_hist is not None and not pd.isna(hist) and not pd.isna(prev_hist):
            h_delta = safe_float(hist - prev_hist)

        return {
            "macd": safe_float(macd_line),
            "signal": safe_float(signal_line),
            "hist": safe_float(hist),
            "histDelta": h_delta
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
    if not ha_candles or len(ha_candles) < 2:
        return {"color": None, "count": None}

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
    if not hist_series or len(hist_series) < 2:
        return {"direction": None, "count": None}

    last = hist_series[-1]
    if last is None or pd.isna(last): return {"direction": None, "count": None}

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

def monte_carlo_predict(candles_5m: List[Dict], current_price: float, target_open_price: float, steps: int = 1, sims: int = 1000, lookback: int = 500) -> Dict[str, Any]:
    """
    Monte Carlo Future Moves based on ChartPrime logic.
    Predicts if the 15m candle will close above or below its 15m OPEN price.
    Uses 5m candles to build the distribution of returns.
    """
    if len(candles_5m) < 20 or current_price <= 0 or target_open_price <= 0:
        return {"prob_up": 0.5, "prob_down": 0.5, "bias": "NEUTRAL", "steps": steps}

    # Calculate 5m returns (log returns)
    hist_candles = candles_5m[-lookback:]
    rets = []
    for i in range(1, len(hist_candles)):
        prev_cl = hist_candles[i-1]['close']
        curr_cl = hist_candles[i]['close']
        if prev_cl > 0 and curr_cl > 0:
            rets.append(np.log(curr_cl / prev_cl))

    if not rets:
        return {"prob_up": 0.5, "prob_down": 0.5, "bias": "NEUTRAL", "steps": steps}

    rets = np.array(rets)

    # Standard Drift (for 5m interval)
    mean_ret = np.mean(rets)
    var_ret = np.var(rets)
    drift = mean_ret - (var_ret / 2)

    # Polarity
    up_moves = rets[rets > 0]
    dn_moves = rets[rets <= 0]

    prob_up_hist = len(up_moves) / len(rets) if len(rets) > 0 else 0.5

    outcomes = []
    for _ in range(sims):
        sim_log_ret = 0.0
        for _s in range(max(1, steps)):
            if np.random.random() < prob_up_hist:
                move = np.random.choice(up_moves) if len(up_moves) > 0 else 0
            else:
                move = np.random.choice(dn_moves) if len(dn_moves) > 0 else 0
            sim_log_ret += (move + drift)

        # Resulting price after 'steps' intervals
        sim_final_price = current_price * np.exp(sim_log_ret)
        outcomes.append(sim_final_price)

    outcomes = np.array(outcomes)
    # Target: Predict if close > 15m open
    prob_up = np.sum(outcomes > target_open_price) / sims
    prob_dn = 1.0 - prob_up

    bias = "BULLISH" if prob_up > 0.6 else "BEARISH" if prob_dn > 0.6 else "NEUTRAL"

    return {
        "prob_up": float(prob_up),
        "prob_down": float(prob_dn),
        "bias": bias,
        "steps": steps,
        "stdev": float(np.std(outcomes))
    }
