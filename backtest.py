import pandas as pd
import numpy as np
import indicators
import engines
from typing import List, Dict, Any

class Backtester:
    def __init__(self, df_1m: pd.DataFrame, df_5m: pd.DataFrame, st_params: Dict[str, Any]):
        self.df_1m = df_1m
        self.df_5m = df_5m
        self.st_params = st_params
        self.balance = 1000.0
        self.trades = []
        self.active_trade = None

    def run(self):
        # We need enough data for indicators
        # 5m data drives the regime and scoring
        # 1m data can be used for entries/exits

        # Pre-calculate all indicators on 5m to speed up
        # However, for true backtesting, we should iterate time

        # Simplify: Loop through 5m bars
        for i in range(150, len(self.df_5m)):
            chunk_5m = self.df_5m.iloc[:i+1]
            closes_5m = chunk_5m['close'].tolist()

            # SuperTrend
            st_cluster = indicators.compute_supertrend_cluster(chunk_5m, self.st_params)

            # MACD Variants
            macd_variants = {
                "3_15_3": indicators.compute_macd(closes_5m[-150:], 3, 15, 3),
                "4_16_3": indicators.compute_macd(closes_5m[-58:], 4, 16, 3),
                "6_28_5": indicators.compute_macd(closes_5m[-58:], 6, 28, 5)
            }

            # Simplified Decision
            regime = engines.detect_regime({"cluster": st_cluster})

            # Heiken Ashi for 5m
            ha_5m = indicators.compute_heiken_ashi(chunk_5m.to_dict('records'))
            consec_5m = indicators.count_consecutive(ha_5m)

            # Score
            score = engines.score_direction({
                "price": closes_5m[-1],
                "cluster": st_cluster,
                "rsi": indicators.compute_rsi(closes_5m, 14),
                "macd": indicators.compute_macd(closes_5m, 12, 26, 9),
                "macd_variants": macd_variants,
                "heiken_5m_color": consec_5m["color"],
                "heiken_5m_count": consec_5m["count"]
                # CVD still missing as it needs tick data
            })

            # Entry logic
            if not self.active_trade:
                if score["rawUp"] > 0.80: # Very selective
                    self.active_trade = {"side": "UP", "entry_price": closes_5m[-1], "entry_idx": i}
                elif score["rawUp"] < 0.20:
                    self.active_trade = {"side": "DOWN", "entry_price": closes_5m[-1], "entry_idx": i}
            else:
                # Exit logic: simple 15m window (3 bars of 5m)
                if i - self.active_trade["entry_idx"] >= 3:
                    exit_price = closes_5m[-1]
                    profit = 0
                    if self.active_trade["side"] == "UP":
                        profit = (exit_price / self.active_trade["entry_price"] - 1) * 100
                    else:
                        profit = (1 - exit_price / self.active_trade["entry_price"]) * 100

                    self.active_trade["exit_price"] = exit_price
                    self.active_trade["profit"] = profit
                    self.trades.append(self.active_trade)
                    self.active_trade = None

        return self.calculate_stats()

    def calculate_stats(self):
        if not self.trades:
            return {"win_rate": 0, "total_trades": 0}

        wins = [t for t in self.trades if t["profit"] > 0]
        win_rate = len(wins) / len(self.trades)
        total_profit = sum([t["profit"] for t in self.trades])

        return {
            "win_rate": win_rate,
            "total_trades": len(self.trades),
            "total_profit": total_profit,
            "avg_profit": total_profit / len(self.trades)
        }

if __name__ == "__main__":
    # Generate dummy data for testing the backtester itself
    np.random.seed(42)
    data = 60000 + np.cumsum(np.random.randn(500) * 20)
    df = pd.DataFrame({
        'open': data - 5,
        'high': data + 10,
        'low': data - 10,
        'close': data
    })

    st_params = {
        "consensus_threshold": 0.6, "base_st_index": 3,
        "st1_atr_len": 7, "st1_factor": 1.5, "st1_ma_type": "EMA", "st1_ma_len": 3, "st1_weight": 1.0,
        "st2_atr_len": 10, "st2_factor": 2.0, "st2_ma_type": "EMA", "st2_ma_len": 5, "st2_weight": 1.0,
        "st3_atr_len": 14, "st3_factor": 2.5, "st3_ma_type": "SMA", "st3_ma_len": 8, "st3_weight": 1.2,
        "st4_atr_len": 21, "st4_factor": 3.0, "st4_ma_type": "WMA", "st4_ma_len": 13, "st4_weight": 1.4,
        "st5_atr_len": 34, "st5_factor": 4.0, "st5_ma_type": "HMA", "st5_ma_len": 21, "st5_weight": 1.6,
    }

    bt = Backtester(df, df, st_params)
    stats = bt.run()
    print(f"Backtest Stats: {stats}")
