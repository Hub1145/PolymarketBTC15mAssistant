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

def score_direction(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Implements scoring for the Mean Reversion strategy.
    Returns scores for 'UP' and 'DOWN' entries.
    """
    price = inputs.get("price")
    vwap = inputs.get("vwap")
    rsi = inputs.get("rsi")
    macd = inputs.get("macd")  # expects dict with 'hist' and 'histDelta'
    ha_candles = inputs.get("ha_candles", []) # Last 1-minute HA candles

    up_score = 0
    down_score = 0

    reasons_up = []
    reasons_down = []

    # 1. RSI
    if rsi is not None:
        if rsi < 28:
            up_score += 1
            reasons_up.append("RSI < 28")
        if rsi > 72:
            down_score += 1
            reasons_down.append("RSI > 72")

    # 2. MACD Histogram
    # Signal for "Up" buy: Histogram RISING (3 consecutive increases) AND still negative
    if macd and macd.get("hist_series") and len(macd["hist_series"]) >= 3:
        h = macd["hist_series"]
        # Up
        if h[-1] < 0 and h[-1] > h[-2] and h[-2] > h[-3]:
            up_score += 1
            reasons_up.append("MACD Hist Rising (Neg)")
        # Down
        if h[-1] > 0 and h[-1] < h[-2] and h[-2] < h[-3]:
            down_score += 1
            reasons_down.append("MACD Hist Falling (Pos)")

    # 3. VWAP Deviation
    if price and vwap:
        dev = (price - vwap) / vwap
        if dev <= -0.0015: # -0.15%
            up_score += 1
            reasons_up.append(f"VWAP Dev {dev*100:.2f}%")
        if dev >= 0.0015: # +0.15%
            down_score += 1
            reasons_down.append(f"VWAP Dev {dev*100:.2f}%")

    # 4. Heikin Ashi
    if ha_candles and len(ha_candles) >= 2:
        last_ha = ha_candles[-1]
        prev_ha = ha_candles[-2]

        # Up: Doji or first green after reds
        # Check if previous was red
        if not prev_ha["isGreen"]:
            # Pattern 1: Exhaustion doji (body < 30% of avg body)
            # Simple version: body < 0.3 * average body of last few candles
            avg_body = sum(c["body"] for c in ha_candles[-5:]) / 5 if len(ha_candles) >= 5 else last_ha["body"]
            is_doji = last_ha["body"] < 0.3 * avg_body

            # Pattern 2: First green
            is_first_green = last_ha["isGreen"]

            if is_doji or is_first_green:
                # Avoid if strong downtrend (no lower wick)
                # HA Low = Min(Low, HA Open, HA Close). No lower wick means HA Low == Min(HA Open, HA Close)
                has_lower_wick = last_ha["low"] < min(last_ha["open"], last_ha["close"])
                if has_lower_wick or is_first_green:
                    up_score += 1
                    reasons_up.append("HA Reversal/Doji")

        # Down: Doji or first red after greens
        if prev_ha["isGreen"]:
            avg_body = sum(c["body"] for c in ha_candles[-5:]) / 5 if len(ha_candles) >= 5 else last_ha["body"]
            is_doji = last_ha["body"] < 0.3 * avg_body
            is_first_red = not last_ha["isGreen"]

            if is_doji or is_first_red:
                has_upper_wick = last_ha["high"] > max(last_ha["open"], last_ha["close"])
                if has_upper_wick or is_first_red:
                    down_score += 1
                    reasons_down.append("HA Reversal/Doji")

    return {
        "UP": {"score": up_score, "reasons": reasons_up},
        "DOWN": {"score": down_score, "reasons": reasons_down}
    }

def check_reversal(side: str, inputs: Dict[str, Any]) -> bool:
    """
    Checks if position should be closed due to signal reversal.
    Trigger: Indicators flip to OPPOSITE direction with score >= 3/4
    """
    scores = score_direction(inputs)
    opposite_side = "DOWN" if side == "UP" else "UP"
    return scores[opposite_side]["score"] >= 3

def decide(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry logic gates and scoring.
    """
    time_left_sec = inputs.get("time_left_sec", 0)
    poly_price_up = inputs.get("poly_price_up") # e.g. 0.20
    poly_price_down = inputs.get("poly_price_down")
    btc_price = inputs.get("btc_price")
    btc_open = inputs.get("btc_open")
    active_position = inputs.get("active_position") # bool

    # Gate 1: Time remaining >= 4 min
    if time_left_sec < 240:
        return {"action": "NO_TRADE", "reason": "time_left < 4m"}

    # Gate 4: No active position
    if active_position:
        return {"action": "NO_TRADE", "reason": "active_position_exists"}

    scores = score_direction(inputs)

    # Check "UP" entry
    if poly_price_up is not None and poly_price_up <= 0.20:
        if btc_price and btc_open and (btc_price - btc_open) / btc_open <= -0.0015:
            if scores["UP"]["score"] >= 3:
                return {
                    "action": "ENTER",
                    "side": "UP",
                    "score": scores["UP"]["score"],
                    "reasons": scores["UP"]["reasons"]
                }

    # Check "DOWN" entry
    if poly_price_down is not None and poly_price_down <= 0.20:
        if btc_price and btc_open and (btc_price - btc_open) / btc_open >= 0.0015:
            if scores["DOWN"]["score"] >= 3:
                return {
                    "action": "ENTER",
                    "side": "DOWN",
                    "score": scores["DOWN"]["score"],
                    "reasons": scores["DOWN"]["reasons"]
                }

    return {"action": "NO_TRADE", "reason": "gates_or_score_not_met"}
