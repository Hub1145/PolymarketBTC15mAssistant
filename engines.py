from typing import Dict, Optional, Any

def clamp(x: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, x))

def detect_regime(inputs: Dict[str, Any]) -> Dict[str, str]:
    price = inputs.get("price")
    vwap = inputs.get("vwap")
    vwap_slope = inputs.get("vwapSlope")
    vwap_cross_count = inputs.get("vwapCrossCount")
    volume_recent = inputs.get("volumeRecent")
    volume_avg = inputs.get("volumeAvg")

    if price is None or vwap is None or vwap_slope is None:
        return {"regime": "CHOP", "reason": "missing_inputs"}

    above = price > vwap

    low_volume = volume_recent < 0.6 * volume_avg if volume_recent is not None and volume_avg is not None else False
    if low_volume and abs((price - vwap) / vwap) < 0.001:
        return {"regime": "CHOP", "reason": "low_volume_flat"}

    if above and vwap_slope > 0:
        return {"regime": "TREND_UP", "reason": "price_above_vwap_slope_up"}

    if not above and vwap_slope < 0:
        return {"regime": "TREND_DOWN", "reason": "price_below_vwap_slope_down"}

    if vwap_cross_count is not None and vwap_cross_count >= 3:
        return {"regime": "RANGE", "reason": "frequent_vwap_cross"}

    return {"regime": "RANGE", "reason": "default"}

def score_direction(inputs: Dict[str, Any]) -> Dict[str, float]:
    price = inputs.get("price")
    vwap = inputs.get("vwap")
    vwap_slope = inputs.get("vwapSlope")
    rsi = inputs.get("rsi")
    rsi_slope = inputs.get("rsiSlope")
    macd = inputs.get("macd")
    heiken_color = inputs.get("heikenColor")
    heiken_count = inputs.get("heikenCount")
    failed_vwap_reclaim = inputs.get("failedVwapReclaim")

    # 5m indicators
    macd_5m = inputs.get("macd_5m")
    heiken_5m_color = inputs.get("heiken_5m_color")
    heiken_5m_count = inputs.get("heiken_5m_count")

    up = 1.0
    down = 1.0

    if price is not None and vwap is not None:
        if price > vwap:
            up += 2
        if price < vwap:
            down += 2

    if vwap_slope is not None:
        if vwap_slope > 0:
            up += 2
        if vwap_slope < 0:
            down += 2

    if rsi is not None and rsi_slope is not None:
        if rsi > 55 and rsi_slope > 0:
            up += 2
        if rsi < 45 and rsi_slope < 0:
            down += 2

    if macd is not None and macd.get("hist") is not None and macd.get("histDelta") is not None:
        expanding_green = macd["hist"] > 0 and macd["histDelta"] > 0
        expanding_red = macd["hist"] < 0 and macd["histDelta"] < 0
        if expanding_green:
            up += 2
        if expanding_red:
            down += 2

        if macd.get("macd") is not None:
            if macd["macd"] > 0:
                up += 1
            if macd["macd"] < 0:
                down += 1

    if heiken_color:
        if heiken_color == "green" and heiken_count >= 2:
            up += 1
        if heiken_color == "red" and heiken_count >= 2:
            down += 1

    # 5m Logic
    if heiken_5m_color:
        if heiken_5m_color == "green" and heiken_5m_count >= 2:
            up += 1.5
        if heiken_5m_color == "red" and heiken_5m_count >= 2:
            down += 1.5

    if macd_5m is not None and macd_5m.get("hist") is not None and macd_5m.get("histDelta") is not None:
        if macd_5m["histDelta"] > 0:
            up += 1
        if macd_5m["histDelta"] < 0:
            down += 1

    if failed_vwap_reclaim is True:
        down += 3

    raw_up = up / (up + down)
    return {"upScore": up, "downScore": down, "rawUp": raw_up}

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
