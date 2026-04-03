import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import settings
import data
import ws_data
import chainlink
import indicators
import engines
import utils

app = FastAPI(title="Polymarket BTC 15m Assistant")
templates = Jinja2Templates(directory="templates")

# Global state to store the latest data
state = {
    "latest_data": {},
    "last_update_ts": 0,
    "trading_mode": settings.MODE,
    "paper_balance": settings.PAPER_BALANCE_USD,
    "active_trades": [],
    "trade_history": [],
    "logs": [],
    "btc_window_open": None,
    "current_window_start": 0
}

def log_message(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    state["logs"].append(formatted)
    if len(state["logs"]) > 100:
        state["logs"].pop(0)

def get_ws_symbol_filter(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("USDT"):
        return s[:-4].lower()
    return s.lower()

# Background task instances
binance_stream = ws_data.BinanceTradeStream(symbol=settings.SYMBOL)
binance_kline_1m = ws_data.BinanceKlineStream(symbol=settings.SYMBOL, interval="1m", limit=240)
binance_kline_5m = ws_data.BinanceKlineStream(symbol=settings.SYMBOL, interval="5m", limit=200)

polymarket_ws_stream = ws_data.PolymarketChainlinkStream(
    ws_url=settings.POLYMARKET_LIVE_DATA_WS_URL,
    symbol_includes=get_ws_symbol_filter(settings.SYMBOL)
)
chainlink_ws_stream = ws_data.ChainlinkPriceStream(aggregator=settings.get_aggregator(settings.SYMBOL))

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
    # For Mean Reversion, we always buy the side priced <= 20c
    price = market_prices["up"] if side == "UP" else market_prices["down"]
    if price is None:
        return

    if any(t["market_id"] == market["id"] for t in state["active_trades"]):
        return

    # Risk management - Conviction-based scaling
    # 4/4 signals -> 10% of bankroll, 3/4 signals -> 5% of bankroll
    base_percent = 5.0 if decision["score"] == 3 else 10.0

    # Drawdown scaling (simple version)
    # TODO: Implement full drawdown scaling if needed

    amount_to_risk = (base_percent / 100.0) * state["paper_balance"]

    if state["paper_balance"] < amount_to_risk or amount_to_risk <= 0:
        print(f"Insufficient paper balance ({state['paper_balance']}) or invalid risk amount ({amount_to_risk})")
        return

    trade = {
        "market_id": market["id"],
        "market_slug": market.get("slug"),
        "side": side,
        "entry_price": 0.20, # Strategy specifies buying at 20c
        "amount": amount_to_risk,
        "shares": amount_to_risk / price,
        "entry_time": datetime.now().isoformat(),
        "status": "OPEN",
        "settlement_price": None,
        "profit_loss": None,
        "reasons": decision["reasons"]
    }

    if state["trading_mode"] == "paper":
        state["paper_balance"] -= amount_to_risk
        state["active_trades"].append(trade)
        log_message(f"Executed PAPER trade: {side} @ {price*100:.0f}c (Score: {decision['score']}/4)")
    else:
        log_message(f"LIVE mode enabled but execution not implemented.")

async def update_trades(current_prices: Dict[str, Any], indicators_data: Dict[str, Any], time_left_sec: float):
    remaining_active = []
    for trade in state["active_trades"]:
        # 1. Check TP/SL
        side_price = current_prices["up"] if trade["side"] == "UP" else current_prices["down"]

        if side_price is not None:
            # Take Profit >= 80c
            if side_price >= settings.TP_VALUE:
                await close_trade(trade, side_price, "TAKE_PROFIT")
                continue

            # Stop Loss <= 10c
            if side_price <= settings.SL_VALUE:
                await close_trade(trade, side_price, "STOP_LOSS")
                continue

        # 2. Signal Reversal (if price < 65c)
        if side_price is not None and side_price < 0.65:
            if engines.check_reversal(trade["side"], indicators_data):
                await close_trade(trade, side_price, "SIGNAL_REVERSAL")
                continue

        # 3. Time Exit
        if time_left_sec < 120:
            # Hard rule < 60s
            if time_left_sec < 60:
                await close_trade(trade, side_price or 0, "TIME_EXIT_HARD")
                continue

            # Path B: Signals neutral/reversed or already profitable (>= 30c)
            # Path A: Hold if signals still valid AND price < entry (in loss)
            # For simplicity, if not (signals valid AND in loss), close.
            is_profitable = side_price is not None and side_price >= 0.30
            signals_valid = not engines.check_reversal(trade["side"], indicators_data) # This is a bit loose but works

            if is_profitable or not signals_valid:
                await close_trade(trade, side_price or 0, "TIME_EXIT_SOFT")
                continue

        # 4. Check if market actually closed (fallback)
        market = await data.fetch_market_by_slug(trade["market_slug"])
        if market and market.get("closed", False):
            outcomes = market.get("outcomes", [])
            if isinstance(outcomes, str): outcomes = json.loads(outcomes)
            outcome_prices = market.get("outcomePrices", [])
            if isinstance(outcome_prices, str): outcome_prices = json.loads(outcome_prices)

            won = False
            up_index = next((i for i, x in enumerate(outcomes) if x.lower() == settings.POLYMARKET_UP_LABEL.lower()), -1)
            down_index = next((i for i, x in enumerate(outcomes) if x.lower() == settings.POLYMARKET_DOWN_LABEL.lower()), -1)

            winning_index = -1
            if outcome_prices:
                try:
                    for i, p in enumerate(outcome_prices):
                        if float(p) > 0.9:
                            winning_index = i
                            break
                except: pass

            if winning_index != -1:
                if (trade["side"] == "UP" and winning_index == up_index) or (trade["side"] == "DOWN" and winning_index == down_index):
                    won = True

                await close_trade(trade, 1.0 if won else 0.0, "RESOLUTION")
                continue

        remaining_active.append(trade)

    state["active_trades"] = remaining_active

async def close_trade(trade: Dict[str, Any], exit_price: float, reason: str):
    payout = trade["shares"] * exit_price
    state["paper_balance"] += payout
    settings.PAPER_BALANCE_USD = state["paper_balance"]
    trade["profit_loss"] = payout - trade["amount"]
    trade["status"] = "CLOSED"
    trade["exit_price"] = exit_price
    trade["exit_time"] = datetime.now().isoformat()
    trade["exit_reason"] = reason
    state["trade_history"].append(trade)

    log_message(f"CLOSED {trade['side']} @ {exit_price*100:.0f}c | Reason: {reason} | P/L: ${trade['profit_loss']:.2f}")

    # Persist balance
    try:
        with open("config.json", "r") as f:
            cfg = json.load(f)
        cfg["paper_balance_usd"] = state["paper_balance"]
        with open("config.json", "w") as f:
            json.dump(cfg, f, indent=2)
    except: pass

async def seed_kline_buffers():
    try:
        k1m, k5m = await asyncio.gather(
            data.fetch_klines(settings.SYMBOL, "1m", 240),
            data.fetch_klines(settings.SYMBOL, "5m", 200)
        )
        binance_kline_1m.set_candles(k1m)
        binance_kline_5m.set_candles(k5m)
        log_message(f"Seeded Binance kline buffers (1m/5m) for {settings.SYMBOL}")
    except Exception as e:
        log_message(f"Failed to seed kline buffers: {e}")

async def update_loop():
    csv_header = [
        "timestamp", "entry_minute", "time_left_min", "regime", "signal",
        "model_up", "model_down", "mkt_up", "mkt_down", "edge_up", "edge_down", "recommendation"
    ]

    while True:
        try:
            timing = get_candle_window_timing(settings.CANDLE_WINDOW_MINUTES)

            binance_ws = binance_stream.get_last()
            poly_ws = polymarket_ws_stream.get_last()
            cl_ws = chainlink_ws_stream.get_last()

            results = await asyncio.gather(
                data.fetch_last_price(settings.SYMBOL),
                chainlink.chainlink_fetcher.fetch_chainlink_btc_usd(),
                fetch_polymarket_snapshot(),
                return_exceptions=True
            )

            last_price = results[0] if not isinstance(results[0], Exception) else None
            chainlink_data = results[1] if not isinstance(results[1], Exception) else {}
            poly_snapshot = results[2] if not isinstance(results[2], Exception) else {"ok": False}

            # Use real-time WebSocket buffers for indicators
            klines_1m = binance_kline_1m.get_candles()
            klines_5m = binance_kline_5m.get_candles()

            spot_price = binance_ws.get("price") or last_price

            # Polymarket Chainlink Price Logic with explicit source tracking
            current_price = None
            price_source = None

            if poly_ws.get("price"):
                current_price = poly_ws["price"]
                price_source = "Polymarket WS"
            elif cl_ws.get("price"):
                current_price = cl_ws["price"]
                price_source = "Chainlink RPC WS"
            elif chainlink_data.get("price"):
                current_price = chainlink_data["price"]
                price_source = "Chainlink RPC REST"

            settlement_ms = None
            if poly_snapshot["ok"] and poly_snapshot["market"].get("endDate"):
                settlement_ms = datetime.fromisoformat(poly_snapshot["market"]["endDate"].replace('Z', '+00:00')).timestamp() * 1000

            time_left_min = (settlement_ms - time.time() * 1000) / 60_000 if settlement_ms else timing["remainingMinutes"]

            if timing["startMs"] != state["current_window_start"]:
                state["current_window_start"] = timing["startMs"]
                state["btc_window_open"] = spot_price
                log_message(f"New window started. BTC Open: {state['btc_window_open']}")

            closes = [c["close"] for c in klines_1m]
            vwap_now = indicators.compute_session_vwap(klines_1m, start_time_ms=timing["startMs"])

            rsi_now = indicators.compute_rsi(closes, settings.RSI_PERIOD)
            macd = indicators.compute_macd(closes, settings.MACD_FAST, settings.MACD_SLOW, settings.MACD_SIGNAL)
            ha = indicators.compute_heiken_ashi(klines_1m)

            market_up = poly_snapshot["prices"]["up"] if poly_snapshot["ok"] else None
            market_down = poly_snapshot["prices"]["down"] if poly_snapshot["ok"] else None

            indicators_data = {
                "price": spot_price,
                "vwap": vwap_now,
                "rsi": rsi_now,
                "macd": macd,
                "ha_candles": ha
            }

            decision = engines.decide({
                **indicators_data,
                "time_left_sec": time_left_min * 60,
                "poly_price_up": market_up,
                "poly_price_down": market_down,
                "btc_price": spot_price,
                "btc_open": state["btc_window_open"],
                "active_position": len(state["active_trades"]) > 0
            })

            if poly_snapshot["ok"]:
                await execute_trade(decision, poly_snapshot["prices"], poly_snapshot["market"])

            await update_trades(poly_snapshot["prices"] if poly_snapshot["ok"] else {}, indicators_data, time_left_min * 60)

            signal_label = f"BUY {decision.get('side')}" if decision["action"] == "ENTER" else "NO TRADE"
            # Update CSV logging to match new strategy data
            csv_header_new = ["timestamp", "time_left_min", "signal", "score", "reasons", "poly_up", "poly_down", "btc_price", "btc_open"]
            utils.append_csv_row("./logs/signals.csv", csv_header_new, [
                datetime.now().isoformat(), time_left_min, signal_label,
                decision.get("score", 0), "|".join(decision.get("reasons", [])),
                market_up, market_down, spot_price, state["btc_window_open"]
            ])

            state["latest_data"] = {
                "timestamp": datetime.now().isoformat(),
                "timing": timing,
                "market": poly_snapshot.get("market") if poly_snapshot["ok"] else None,
                "trading_state": {
                    "mode": state["trading_mode"],
                    "balance": state["paper_balance"],
                    "active_trades": state["active_trades"],
                    "history_count": len(state["trade_history"]),
                    "risk": {"type": settings.RISK_TYPE, "value": settings.RISK_VALUE},
                    "symbol": settings.SYMBOL,
                    "btc_open": state["btc_window_open"],
                    "use_tp_sl": settings.USE_TP_SL,
                    "tp_value": settings.TP_VALUE,
                    "sl_value": settings.SL_VALUE
                },
                "prices": {
                    "spot": spot_price,
                    "chainlink": current_price,
                    "chainlink_source": price_source,
                    "poly_up": market_up,
                    "poly_down": market_down
                },
                "indicators": {
                    "rsi": rsi_now,
                    "vwap": vwap_now,
                    "macd": macd,
                    "ha_last": ha[-1] if ha else None
                },
                "analysis": {
                    "decision": decision
                }
            }
            state["last_update_ts"] = time.time()

        except Exception as e:
            print(f"Error in update loop: {e}")

        await asyncio.sleep(settings.POLL_INTERVAL_MS / 1000)

@app.on_event("startup")
async def startup_event():
    # Initial seeding
    await seed_kline_buffers()

    # Start all background tasks
    asyncio.create_task(binance_stream.start())
    asyncio.create_task(binance_kline_1m.start())
    asyncio.create_task(binance_kline_5m.start())
    asyncio.create_task(polymarket_ws_stream.start())
    asyncio.create_task(chainlink_ws_stream.start())
    asyncio.create_task(update_loop())

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
async def get_settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/api/latest")
async def get_latest():
    return state["latest_data"]

@app.get("/api/logs")
async def get_logs():
    return state["logs"]

@app.get("/api/available-series")
async def get_available_series():
    return await data.fetch_available_15m_series()

@app.get("/api/settings")
async def get_settings():
    # Return serializable version of settings
    pk = settings.PRIVATE_KEY
    masked_pk = pk[:6] + "..." + pk[-4:] if pk and len(pk) > 10 else pk

    return {
        "mode": settings.MODE,
        "paper_balance_usd": settings.PAPER_BALANCE_USD,
        "private_key": masked_pk,
        "polymarket": {
            "series_id": settings.POLYMARKET_SERIES_ID,
            "gamma_base_url": settings.GAMMA_BASE_URL,
            "clob_base_url": settings.CLOB_BASE_URL,
            "live_ws_url": settings.POLYMARKET_LIVE_DATA_WS_URL,
            "up_label": settings.POLYMARKET_UP_LABEL,
            "down_label": settings.POLYMARKET_DOWN_LABEL
        },
        "trading": {
            "symbol": settings.SYMBOL,
            "risk_type": settings.RISK_TYPE,
            "risk_value": settings.RISK_VALUE,
            "use_tp_sl": settings.USE_TP_SL,
            "tp_value": settings.TP_VALUE,
            "sl_value": settings.SL_VALUE
        }
    }

@app.post("/api/settings")
async def post_settings(new_settings: Dict[str, Any]):
    global binance_stream, polymarket_ws_stream, chainlink_ws_stream, binance_kline_1m, binance_kline_5m

    # Check if critical stream settings changed
    old_symbol = settings.SYMBOL

    # Save to config.json
    with open("config.json", "w") as f:
        json.dump(new_settings, f, indent=2)

    settings.MODE = new_settings.get("mode", settings.MODE)
    settings.PAPER_BALANCE_USD = float(new_settings.get("paper_balance_usd", settings.PAPER_BALANCE_USD))

    new_pk = new_settings.get("private_key")
    if new_pk and "..." not in new_pk:
        settings.PRIVATE_KEY = new_pk

    if "trading" in new_settings:
        t = new_settings["trading"]
        settings.SYMBOL = t.get("symbol", settings.SYMBOL)
        settings.RISK_TYPE = t.get("risk_type", settings.RISK_TYPE)
        settings.RISK_VALUE = float(t.get("risk_value", settings.RISK_VALUE))
        settings.USE_TP_SL = t.get("use_tp_sl", settings.USE_TP_SL)
        settings.TP_VALUE = float(t.get("tp_value", settings.TP_VALUE))
        settings.SL_VALUE = float(t.get("sl_value", settings.SL_VALUE))

    if "polymarket" in new_settings:
        p = new_settings["polymarket"]
        settings.POLYMARKET_SERIES_ID = p.get("series_id", settings.POLYMARKET_SERIES_ID)
        settings.POLYMARKET_UP_LABEL = p.get("up_label", settings.POLYMARKET_UP_LABEL)
        settings.POLYMARKET_DOWN_LABEL = p.get("down_label", settings.POLYMARKET_DOWN_LABEL)

    state["trading_mode"] = settings.MODE
    state["paper_balance"] = settings.PAPER_BALANCE_USD

    # Restart streams if symbol changed
    if settings.SYMBOL != old_symbol:
        binance_stream.close()
        binance_stream = ws_data.BinanceTradeStream(symbol=settings.SYMBOL)
        asyncio.create_task(binance_stream.start())

        binance_kline_1m.close()
        binance_kline_1m = ws_data.BinanceKlineStream(symbol=settings.SYMBOL, interval="1m", limit=240)
        asyncio.create_task(binance_kline_1m.start())

        binance_kline_5m.close()
        binance_kline_5m = ws_data.BinanceKlineStream(symbol=settings.SYMBOL, interval="5m", limit=200)
        asyncio.create_task(binance_kline_5m.start())

        # Reseed buffers for new symbol
        await seed_kline_buffers()

        polymarket_ws_stream.close()
        polymarket_ws_stream = ws_data.PolymarketChainlinkStream(
            ws_url=settings.POLYMARKET_LIVE_DATA_WS_URL,
            symbol_includes=get_ws_symbol_filter(settings.SYMBOL)
        )
        asyncio.create_task(polymarket_ws_stream.start())

        chainlink_ws_stream.close()
        chainlink_ws_stream = ws_data.ChainlinkPriceStream(aggregator=settings.get_aggregator(settings.SYMBOL))
        asyncio.create_task(chainlink_ws_stream.start())

    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok", "last_update": state["last_update_ts"], "mode": state["trading_mode"]}

@app.get("/history")
async def get_history():
    return state["trade_history"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
