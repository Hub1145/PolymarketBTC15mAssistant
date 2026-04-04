from typing import Dict, Optional, Any
from utils import clamp

def detect_regime(inputs: Dict[str, Any]) -> Dict[str, str]:
    price = inputs.get("price")
    ema_20 = inputs.get("ema_20")

    if price is None or ema_20 is None:
        return {"regime": "CHOP", "reason": "missing_inputs"}

    above = price > ema_20

    if above:
        return {"regime": "TREND_UP", "reason": "price_above_ema20"}
    else:
        return {"regime": "TREND_DOWN", "reason": "price_below_ema20"}

def score_direction(inputs: Dict[str, Any]) -> Dict[str, float]:
    price = inputs.get("price")
    ema_20 = inputs.get("ema_20")
    rsi = inputs.get("rsi")

    macd_1m = inputs.get("macd")
    ha_1m_color = inputs.get("heikenColor")
    ha_1m_count = inputs.get("heikenCount")

    macd_5m = inputs.get("macd_5m")
    macd_5m_hist_color = macd_5m.get("histColor") if macd_5m else None
    macd_5m_hist_count = macd_5m.get("histCount") if macd_5m else 0

    ha_5m_color = inputs.get("heiken_5m_color")
    ha_5m_count = inputs.get("heiken_5m_count")

    up = 1.0
    down = 1.0

    # Trend detection (20-period EMA on 5m)
    uptrend = price > ema_20 if (price is not None and ema_20 is not None) else None

    # RSI protections
    is_overbought = rsi is not None and rsi > 70
    is_oversold = rsi is not None and rsi < 30

    # Handle missing essential inputs
    if price is None:
        return {"upScore": 0, "downScore": 0, "rawUp": 0.5, "uptrend": uptrend}

    # 1. 5m MACD Momentum and Exhaustion
    macd_5m_exhausted = macd_5m_hist_count >= 6
    if macd_5m_hist_color == "green":
        if 1 <= macd_5m_hist_count <= 5:
            up += 6
        elif macd_5m_exhausted:
            up = 0.5 # Suppress buy
    elif macd_5m_hist_color == "red":
        if 1 <= macd_5m_hist_count <= 5:
            down += 6
        elif macd_5m_exhausted:
            down = 0.5 # Suppress sell

    # 2. 5m Heiken Ashi Momentum and Exhaustion
    ha_5m_exhausted = ha_5m_count >= 6
    if ha_5m_color == "green":
        if 1 <= ha_5m_count <= 5:
            up += 4
        elif ha_5m_exhausted:
            up = 0.5 # Suppress buy
    elif ha_5m_color == "red":
        if 1 <= ha_5m_count <= 5:
            down += 4
        elif ha_5m_exhausted:
            down = 0.5 # Suppress sell

    # 3. New Momentum Detection
    # If MACD exhausted, new HA start forming => sign of new momentum
    if macd_5m_exhausted and ha_5m_color and ha_5m_count <= 2:
        if ha_5m_color == "green" and uptrend:
            up += 10 # Strong signal
        elif ha_5m_color == "red" and not uptrend:
            down += 10 # Strong signal

    # If HA exhausted, new MACD histogram start => signal
    if ha_5m_exhausted and macd_5m_hist_color and macd_5m_hist_count <= 2:
        if macd_5m_hist_color == "green" and uptrend:
            up += 10
        elif macd_5m_hist_color == "red" and not uptrend:
            down += 10

    # 4. Global Filters
    if is_overbought: up = 0.1
    if is_oversold: down = 0.1

    if uptrend is False: up = min(up, 1.0)
    if uptrend is True: down = min(down, 1.0)

    raw_up = up / (up + down) if (up + down) > 0 else 0.5
    return {"upScore": up, "downScore": down, "rawUp": raw_up, "uptrend": uptrend}

def apply_time_awareness(raw_up: float, remaining_minutes: float, window_minutes: float) -> Dict[str, float]:
    time_decay = clamp(remaining_minutes / window_minutes, 0, 1)
    adjusted_up = clamp(0.5 + (raw_up - 0.5) * time_decay, 0, 1)
    return {"timeDecay": time_decay, "adjustedUp": adjusted_up, "adjustedDown": 1 - adjusted_up}

def compute_edge(inputs: Dict[str, Any]) -> Dict[str, Optional[float]]:
    model_up = inputs.get("modelUp")
    model_down = inputs.get("modelDown")
    market_yes = inputs.get("marketYes")
    market_no = inputs.get("marketNo")

    if market_yes is None or market_no is None:
        return {"marketUp": None, "marketDown": None, "edgeUp": None, "edgeDown": None}

    total_market = market_yes + market_no
    market_up = market_yes / total_market if total_market > 0 else None
    market_down = market_no / total_market if total_market > 0 else None

    edge_up = model_up - market_up if market_up is not None else None
    edge_down = model_down - market_down if market_down is not None else None

    return {
        "marketUp": clamp(market_up, 0, 1) if market_up is not None else None,
        "marketDown": clamp(market_down, 0, 1) if market_down is not None else None,
        "edgeUp": edge_up,
        "edgeDown": edge_down
    }

def decide(inputs: Dict[str, Any]) -> Dict[str, Any]:
    remaining_minutes = inputs.get("remainingMinutes")
    edge_up = inputs.get("edgeUp")
    edge_down = inputs.get("edgeDown")
    model_up = inputs.get("modelUp")
    model_down = inputs.get("modelDown")

    # Time remaining strictness: avoid late entries (< 2.5 mins left)
    if remaining_minutes is not None and remaining_minutes < 2.5:
        return {"action": "NO_TRADE", "side": None, "phase": "LATE", "reason": "time_exhaustion"}

    phase = "EARLY" if remaining_minutes > 10 else "MID" if remaining_minutes > 5 else "LATE"
    threshold = 0.05 if phase == "EARLY" else 0.1 if phase == "MID" else 0.2
    min_prob = 0.55 if phase == "EARLY" else 0.6 if phase == "MID" else 0.65

    if edge_up is None or edge_down is None:
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": "missing_market_data"}

    best_side = "UP" if edge_up > edge_down else "DOWN"
    best_edge = edge_up if best_side == "UP" else edge_down
    best_model = model_up if best_side == "UP" else model_down

    if best_edge < threshold:
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": f"edge_below_{threshold}"}

    if best_model is not None and best_model < min_prob:
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": f"prob_below_{min_prob}"}

    strength = "STRONG" if best_edge >= 0.2 else "GOOD" if best_edge >= 0.1 else "OPTIONAL"
    return {"action": "ENTER", "side": best_side, "phase": phase, "strength": strength, "edge": best_edge}
