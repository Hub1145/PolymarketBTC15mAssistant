from typing import Dict, Optional, Any
from utils import clamp

def detect_regime(inputs: Dict[str, Any]) -> Dict[str, str]:
    cluster = inputs.get("cluster")
    if not cluster:
        return {"regime": "CHOP", "reason": "missing_cluster"}

    regime_val = cluster.get("regime", 0)

    if regime_val == 1:
        return {"regime": "TREND_UP", "reason": f"ST_Cluster_Bullish_{cluster.get('strength', 0):.2f}"}
    elif regime_val == -1:
        return {"regime": "TREND_DOWN", "reason": f"ST_Cluster_Bearish_{cluster.get('strength', 0):.2f}"}
    else:
        return {"regime": "CHOP", "reason": "ST_Cluster_Neutral"}

def score_direction(inputs: Dict[str, Any]) -> Dict[str, float]:
    price = inputs.get("price")
    cluster = inputs.get("cluster")
    rsi = inputs.get("rsi")
    cvd_data = inputs.get("cvd_data") # {divergence: BULLISH|BEARISH|NONE, cvd_delta: float}
    mc_data = inputs.get("mc_data") # {prob_up: float, bias: str}

    macd_1m = inputs.get("macd")
    macd_variants = inputs.get("macd_variants") # { '3_15_3': {histDelta: float}, ... }
    ha_1m_color = inputs.get("heikenColor")
    ha_1m_count = inputs.get("heikenCount")

    macd_5m = inputs.get("macd_5m")
    macd_5m_hist_color = macd_5m.get("histColor") if macd_5m else None
    macd_5m_hist_count = macd_5m.get("histCount") if macd_5m else 0

    ha_5m_color = inputs.get("heiken_5m_color")
    ha_5m_count = inputs.get("heiken_5m_count") or 0

    up = 1.0
    down = 1.0

    # Trend detection (SuperTrend Cluster on 5m)
    cluster_regime = cluster.get("regime", 0) if cluster else 0
    cluster_strength = cluster.get("strength", 0) if cluster else 0
    uptrend = True if cluster_regime == 1 else False if cluster_regime == -1 else None

    # Handle missing essential inputs
    if price is None or cluster is None:
        return {"upScore": None, "downScore": None, "rawUp": None, "uptrend": uptrend}

    # 1. SuperTrend Strength (Trend Following)
    if cluster_regime == 1:
        up += 20 * cluster_strength
    elif cluster_regime == -1:
        down += 20 * cluster_strength

    # 2. Monte Carlo conviction (Predictive)
    if mc_data:
        up += mc_data.get("prob_up", 0.5) * 40
        down += mc_data.get("prob_down", 0.5) * 40

    # 3. 5m MACD Momentum and Exhaustion Reversal
    # If exhausted (streak >= 6), we favor reversal if other signals agree
    macd_5m_exhausted = macd_5m_hist_count >= 6
    if macd_5m_exhausted:
        if macd_5m_hist_color == "green":
            down += 15 # Favor reversal to down
            up = 0.5   # Suppress following the exhausted trend
        else:
            up += 15   # Favor reversal to up
            down = 0.5
    else:
        # Early momentum (1-5 bars)
        if macd_5m_hist_color == "green": up += 10
        elif macd_5m_hist_color == "red": down += 10

    # 4. 5m Heiken Ashi Exhaustion Reversal
    ha_5m_exhausted = ha_5m_count >= 6
    if ha_5m_exhausted:
        if ha_5m_color == "green":
            down += 20
            up = 0.1
        else:
            up += 20
            down = 0.1
    else:
        if ha_5m_color == "green": up += 15
        elif ha_5m_color == "red": down += 15

    # 5. CVD Aggression and Divergence
    if cvd_data:
        div = cvd_data.get("divergence", "NONE")
        if div == "BULLISH": up += 30
        elif div == "BEARISH": down += 30

    # 6. RSI Overbought/Oversold Reversal Logic
    if rsi is not None:
        if rsi > 70:
            down += 25 # High conviction reversal
            up = 0.1
        elif rsi < 30:
            up += 25 # High conviction reversal
            down = 0.1

    # 7. MACD Alpha Alignment
    if macd_variants:
        for name, m_data in macd_variants.items():
            if not m_data: continue
            delta = m_data.get("histDelta")
            hist = m_data.get("hist")
            if delta is not None and hist is not None:
                if delta > 0: up += 5
                elif delta < 0: down += 5

    # Final trend filter: Only allow counter-trend if conviction is very high
    if uptrend is True and down < (up + 15):
        down = min(down, 1.0)
    if uptrend is False and up < (down + 15):
        up = min(up, 1.0)

    import math
    def is_invalid(v):
        return v is None or (isinstance(v, float) and math.isnan(v))

    if is_invalid(up) or is_invalid(down):
        return {"upScore": None, "downScore": None, "rawUp": None, "uptrend": uptrend}

    raw_up = up / (up + down) if (up + down) > 0 else None

    return {"upScore": up, "downScore": down, "rawUp": raw_up, "uptrend": uptrend}

def apply_time_awareness(raw_up: Optional[float], remaining_minutes: float, window_minutes: float) -> Dict[str, Optional[float]]:
    time_decay = clamp(remaining_minutes / window_minutes, 0, 1)

    if raw_up is None or time_decay is None:
        return {"timeDecay": time_decay, "adjustedUp": None, "adjustedDown": None}

    adj = 0.5 + (raw_up - 0.5) * time_decay
    adjusted_up = clamp(adj, 0, 1)

    return {
        "timeDecay": time_decay,
        "adjustedUp": adjusted_up,
        "adjustedDown": (1 - adjusted_up) if adjusted_up is not None else None
    }

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

    edge_up = model_up - market_up if (model_up is not None and market_up is not None) else None
    edge_down = model_down - market_down if (model_down is not None and market_down is not None) else None

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

    # Time remaining strictness: avoid very late entries (< 1 min left)
    if remaining_minutes is not None and remaining_minutes < 1.0:
        return {"action": "NO_TRADE", "side": None, "phase": "EXPIRING", "reason": "too_late"}

    phase = "EARLY" if remaining_minutes > 10 else "MID" if remaining_minutes > 5 else "LATE"

    # Requirement for High Conviction (Predictive options style)
    # We prioritize model probability over market edge
    min_prob = 0.70 # Require 70% conviction for any trade

    if model_up is None or model_down is None:
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": "missing_model_data"}

    best_side = "UP" if model_up > model_down else "DOWN"
    best_prob = model_up if best_side == "UP" else model_down

    if best_prob < min_prob:
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": f"conviction_{best_prob:.2f}_below_{min_prob}"}

    # Optional: still check edge if market data is available, but don't block
    edge = edge_up if best_side == "UP" else edge_down
    if edge is not None and edge < 0:
        # If model says UP but market is already priced HIGHER than model, skip
        return {"action": "NO_TRADE", "side": None, "phase": phase, "reason": "negative_edge"}

    strength = "HIGH_CONVICTION" if best_prob >= 0.8 else "STRONG"
    return {"action": "ENTER", "side": best_side, "phase": phase, "strength": strength, "prob": best_prob}
