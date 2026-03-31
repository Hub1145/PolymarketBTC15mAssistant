import asyncio
import time
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
import data
import ws_data
import chainlink
import indicators
import engines
import utils
from net_utils import get_proxy_url_for

app = FastAPI(title="Polymarket BTC 15m Assistant")
templates = Jinja2Templates(directory="templates")

# Global state to store the latest data
state = {
    "latest_data": {},
    "last_update_ts": 0,
    "trading_mode": settings.MODE,
    "paper_balance": settings.PAPER_BALANCE_USD,
    "active_trades": [],
    "trade_history": []
}

# Background task instances
binance_stream = ws_data.BinanceTradeStream(symbol=settings.SYMBOL)
polymarket_ws_stream = ws_data.PolymarketChainlinkStream(ws_url=settings.POLYMARKET_LIVE_DATA_WS_URL)
chainlink_ws_stream = ws_data.ChainlinkPriceStream(aggregator=settings.CHAINLINK_BTC_USD_AGGREGATOR)

def get_candle_window_timing(window_minutes: int) -> Dict[str, float]:
    now_ms = time.time() * 1000
    window_ms = window_minutes * 60_000
    start_ms = (now_ms // window_ms) * window_ms
    end_ms = start_ms + window_ms
    elapsed_ms = now_ms - start_ms
    remaining_ms = end_ms - now_ms
    return {
        "startMs": start_ms,
        "endMs": end_ms,
        "elapsedMs": elapsed_ms,
        "remainingMs": remaining_ms,
        "elapsedMinutes": elapsed_ms / 60_000,
        "remainingMinutes": remaining_ms / 60_000
    }

async def fetch_polymarket_snapshot() -> Dict[str, Any]:
    market = None
    if settings.POLYMARKET_SLUG:
        market = await data.fetch_market_by_slug(settings.POLYMARKET_SLUG)
    elif settings.POLYMARKET_AUTO_SELECT_LATEST:
        events = await data.fetch_live_events_by_series_id(settings.POLYMARKET_SERIES_ID)
        markets = data.flatten_event_markets(events)

        # Simple pick latest logic
        now = time.time() * 1000
        live_markets = [m for m in markets if m.get("endDate") and datetime.fromisoformat(m["endDate"].replace('Z', '+00:00')).timestamp() * 1000 > now]
        if live_markets:
            live_markets.sort(key=lambda x: x["endDate"])
            market = live_markets[0]

    if not market:
        return {"ok": False, "reason": "market_not_found"}

    outcomes = market.get("outcomes", [])
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)

    clob_token_ids = market.get("clobTokenIds", [])
    if isinstance(clob_token_ids, str):
        clob_token_ids = json.loads(clob_token_ids)

    outcome_prices = market.get("outcomePrices", [])
    if isinstance(outcome_prices, str):
        outcome_prices = json.loads(outcome_prices)

    up_token_id = None
    down_token_id = None

    for i, outcome in enumerate(outcomes):
        token_id = clob_token_ids[i] if i < len(clob_token_ids) else None
        if not token_id: continue
        if outcome.lower() == settings.POLYMARKET_UP_LABEL.lower():
            up_token_id = token_id
        elif outcome.lower() == settings.POLYMARKET_DOWN_LABEL.lower():
            down_token_id = token_id

    up_index = next((i for i, x in enumerate(outcomes) if x.lower() == settings.POLYMARKET_UP_LABEL.lower()), -1)
    down_index = next((i for i, x in enumerate(outcomes) if x.lower() == settings.POLYMARKET_DOWN_LABEL.lower()), -1)

    gamma_yes = float(outcome_prices[up_index]) if up_index >= 0 and up_index < len(outcome_prices) else None
    gamma_no = float(outcome_prices[down_index]) if down_index >= 0 and down_index < len(outcome_prices) else None

    if not up_token_id or not down_token_id:
        return {"ok": False, "reason": "missing_token_ids"}

    try:
        up_buy, down_buy, up_book, down_book = await asyncio.gather(
            data.fetch_clob_price(up_token_id, "buy"),
            data.fetch_clob_price(down_token_id, "buy"),
            data.fetch_order_book(up_token_id),
            data.fetch_order_book(down_token_id)
        )
        up_book_summary = data.summarize_order_book(up_book)
        down_book_summary = data.summarize_order_book(down_book)
    except:
        up_buy = None
        down_buy = None
        up_book_summary = {"bestBid": None, "bestAsk": None, "spread": None, "bidLiquidity": None, "askLiquidity": None}
        down_book_summary = {"bestBid": None, "bestAsk": None, "spread": None, "bidLiquidity": None, "askLiquidity": None}

    return {
        "ok": True,
        "market": market,
        "prices": {
            "up": up_buy if up_buy is not None else gamma_yes,
            "down": down_buy if down_buy is not None else gamma_no
        },
        "orderbook": {
            "up": up_book_summary,
            "down": down_book_summary
        }
    }

async def execute_trade(decision: Dict[str, Any], market_prices: Dict[str, Any], market: Dict[str, Any]):
    if decision["action"] != "ENTER":
        return

    side = decision["side"]
    price = market_prices["up"] if side == "UP" else market_prices["down"]
    if price is None:
        return

    # Check if already in a trade for this market
    if any(t["market_id"] == market["id"] for t in state["active_trades"]):
        return

    amount_to_risk = 100.0  # Fixed risk for simulation
    if state["paper_balance"] < amount_to_risk:
        print(f"Insufficient paper balance: {state['paper_balance']}")
        return

    trade = {
        "market_id": market["id"],
        "market_slug": market.get("slug"),
        "side": side,
        "entry_price": price,
        "amount": amount_to_risk,
        "shares": amount_to_risk / price,
        "entry_time": datetime.now().isoformat(),
        "status": "OPEN",
        "settlement_price": None,
        "profit_loss": None
    }

    if state["trading_mode"] == "paper":
        state["paper_balance"] -= amount_to_risk
        state["active_trades"].append(trade)
        print(f"Executed PAPER trade: {side} @ {price} for {market.get('slug')}")
    else:
        # Live mode logic would go here
        print(f"LIVE mode enabled but execution not implemented yet. Mode: {state['trading_mode']}")

async def update_trades(current_prices: Dict[str, Any]):
    remaining_active = []
    for trade in state["active_trades"]:
        market = await data.fetch_market_by_slug(trade["market_slug"])
        if not market:
            remaining_active.append(trade)
            continue

        is_closed = market.get("closed", False)
        if is_closed:
            trade["status"] = "CLOSED"
            trade["exit_time"] = datetime.now().isoformat()
            state["trade_history"].append(trade)
            print(f"Trade for {trade['market_slug']} closed (Simulated)")
        else:
            remaining_active.append(trade)

    state["active_trades"] = remaining_active

async def update_loop():
    csv_header = [
        "timestamp",
        "entry_minute",
        "time_left_min",
        "regime",
        "signal",
        "model_up",
        "model_down",
        "mkt_up",
        "mkt_down",
        "edge_up",
        "edge_down",
        "recommendation"
    ]

    while True:
        try:
            timing = get_candle_window_timing(settings.CANDLE_WINDOW_MINUTES)

            binance_ws = binance_stream.get_last()
            poly_ws = polymarket_ws_stream.get_last()
            cl_ws = chainlink_ws_stream.get_last()

            klines_1m, klines_5m, last_price, chainlink_data, poly_snapshot = await asyncio.gather(
                data.fetch_klines(settings.SYMBOL, "1m", 240),
                data.fetch_klines(settings.SYMBOL, "5m", 200),
                data.fetch_last_price(settings.SYMBOL),
                chainlink.chainlink_fetcher.fetch_chainlink_btc_usd(),
                fetch_polymarket_snapshot()
            )

            # Fallback hierarchy for current price
            spot_price = binance_ws.get("price") or last_price
            current_price = poly_ws.get("price") or cl_ws.get("price") or chainlink_data.get("price")

            settlement_ms = None
            if poly_snapshot["ok"] and poly_snapshot["market"].get("endDate"):
                settlement_ms = datetime.fromisoformat(poly_snapshot["market"]["endDate"].replace('Z', '+00:00')).timestamp() * 1000

            time_left_min = (settlement_ms - time.time() * 1000) / 60_000 if settlement_ms else timing["remainingMinutes"]

            closes = [c["close"] for c in klines_1m]
            vwap_now = indicators.compute_session_vwap(klines_1m)
            vwap_series = indicators.compute_vwap_series(klines_1m)

            lookback = settings.VWAP_SLOPE_LOOKBACK_MINUTES
            vwap_slope = (vwap_now - vwap_series[-lookback]) / lookback if vwap_now and len(vwap_series) >= lookback and vwap_series[-lookback] else None

            # Efficient RSI calculation
            rsi_now = indicators.compute_rsi(closes, settings.RSI_PERIOD)

            # Compute limited series for slope to save time
            rsi_series_limited = []
            for i in range(len(closes) - 5, len(closes)):
                r = indicators.compute_rsi(closes[:i+1], settings.RSI_PERIOD)
                if r is not None: rsi_series_limited.append(r)
            rsi_slope = indicators.slope_last(rsi_series_limited, 3)

            macd = indicators.compute_macd(closes, settings.MACD_FAST, settings.MACD_SLOW, settings.MACD_SIGNAL)

            ha = indicators.compute_heiken_ashi(klines_1m)
            consec = indicators.count_consecutive(ha)

            failed_vwap_reclaim = False
            if vwap_now and len(vwap_series) >= 2:
                failed_vwap_reclaim = closes[-1] < vwap_now and closes[-2] > vwap_series[-2]

            regime_info = engines.detect_regime({
                "price": spot_price,
                "vwap": vwap_now,
                "vwapSlope": vwap_slope,
                "volumeRecent": sum(c["volume"] for c in klines_1m[-20:]),
                "volumeAvg": sum(c["volume"] for c in klines_1m[-120:]) / 6
            })

            scored = engines.score_direction({
                "price": spot_price,
                "vwap": vwap_now,
                "vwapSlope": vwap_slope,
                "rsi": rsi_now,
                "rsiSlope": rsi_slope,
                "macd": macd,
                "heikenColor": consec["color"],
                "heikenCount": consec["count"],
                "failedVwapReclaim": failed_vwap_reclaim
            })

            time_aware = engines.apply_time_awareness(scored["rawUp"], time_left_min, settings.CANDLE_WINDOW_MINUTES)

            market_up = poly_snapshot["prices"]["up"] if poly_snapshot["ok"] else None
            market_down = poly_snapshot["prices"]["down"] if poly_snapshot["ok"] else None

            edge = engines.compute_edge({
                "modelUp": time_aware["adjustedUp"],
                "modelDown": time_aware["adjustedDown"],
                "marketYes": market_up,
                "marketNo": market_down
            })

            decision = engines.decide({
                "remainingMinutes": time_left_min,
                "edgeUp": edge["edgeUp"],
                "edgeDown": edge["edgeDown"],
                "modelUp": time_aware["adjustedUp"],
                "modelDown": time_aware["adjustedDown"]
            })

            if poly_snapshot["ok"]:
                await execute_trade(decision, poly_snapshot["prices"], poly_snapshot["market"])

            await update_trades(poly_snapshot["prices"] if poly_snapshot["ok"] else {})

            # CSV Logging
            signal_label = f"BUY {decision['side']}" if decision["action"] == "ENTER" else "NO TRADE"
            utils.append_csv_row("./logs/signals.csv", csv_header, [
                datetime.now().isoformat(),
                timing["elapsedMinutes"],
                time_left_min,
                regime_info["regime"],
                signal_label,
                time_aware["adjustedUp"],
                time_aware["adjustedDown"],
                market_up,
                market_down,
                edge["edgeUp"],
                edge["edgeDown"],
                f"{decision['side']}:{decision['phase']}:{decision['strength']}" if decision["action"] == "ENTER" else "NO_TRADE"
            ])

            state["latest_data"] = {
                "timestamp": datetime.now().isoformat(),
                "timing": timing,
                "market": poly_snapshot.get("market") if poly_snapshot["ok"] else None,
                "trading_state": {
                    "mode": state["trading_mode"],
                    "balance": state["paper_balance"],
                    "active_trades": state["active_trades"],
                    "history_count": len(state["trade_history"])
                },
                "prices": {
                    "spot": spot_price,
                    "chainlink": current_price,
                    "poly_up": market_up,
                    "poly_down": market_down
                },
                "indicators": {
                    "rsi": rsi_now,
                    "vwap": vwap_now,
                    "macd": macd,
                    "heiken": consec
                },
                "analysis": {
                    "regime": regime_info,
                    "probability": time_aware,
                    "edge": edge,
                    "decision": decision
                }
            }
            state["last_update_ts"] = time.time()

        except Exception as e:
            print(f"Error in update loop: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(settings.POLL_INTERVAL_MS / 1000)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(binance_stream.start())
    asyncio.create_task(polymarket_ws_stream.start())
    asyncio.create_task(chainlink_ws_stream.start())
    asyncio.create_task(update_loop())

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/latest")
async def get_latest():
    return state["latest_data"]

@app.get("/health")
async def health():
    return {"status": "ok", "last_update": state["last_update_ts"], "mode": state["trading_mode"]}

@app.get("/history")
async def get_history():
    return state["trade_history"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
