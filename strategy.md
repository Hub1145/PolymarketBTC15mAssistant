# Trading Strategy Specification

This document outlines the predictive scoring and decision-making logic used in the Python FastAPI implementation of the Polymarket trading bot.

## 1. Point-Based Scoring System

The engine evaluates multiple technical indicators and assigns points to either the "UP" (Bullish) or "DOWN" (Bearish) side. The final probability is calculated as a ratio of these scores.

| Indicator | Weight (Points) | Logic |
|-----------|-----------------|-------|
| **Monte Carlo** | 40 | Predictive conviction based on price paths. |
| **CVD Divergence** | 30 | Detects BULLISH or BEARISH divergence in Cumulative Volume Delta. |
| **RSI Reversal** | 25 | Contrarian signal: >70 favors DOWN, <30 favors UP. |
| **SuperTrend Cluster** | 20 * Strength | Trend-following signal based on 5m SuperTrend clusters. |
| **Heiken Ashi (5m)** | 20 / 15 | Reversal if exhausted (streak >= 6), otherwise trend-following. |
| **MACD (5m)** | 15 / 10 | Reversal if exhausted (streak >= 6), otherwise trend-following. |
| **MACD Alpha** | 5 (per variant) | Momentum alignment across multiple MACD configurations. |

## 2. Market Regime Filtering

The system identifies the current market state using a SuperTrend Cluster:
- **TREND_UP**: Bullish bias. Counter-trend trades are suppressed unless conviction is significantly higher than the trend.
- **TREND_DOWN**: Bearish bias. Counter-trend trades are suppressed unless conviction is significantly higher than the trend.
- **CHOP**: No bias. All signals are weighted equally.

## 3. Time Awareness

Conviction is decayed linearly as the market approaches its expiry time.
- **Window**: The last 15 minutes of a market.
- **Effect**: If the model has 80% conviction but only 7.5 minutes (50%) of the window remain, the conviction is pulled toward 50% (neutral).
- **Rationale**: Reduces risk in highly volatile "settlement" periods where technical indicators may become less reliable.

## 4. Decision Logic

The bot follows a strict set of rules for entering trades:

1. **Minimum Conviction**: The model's probability for a side must be **> 70%**.
2. **Negative Edge Check**: If market data is available, the bot skips if the market is already priced higher than the model's prediction.
3. **Expiry Filter**: No new trades are entered if less than **1 minute** remains until expiry.
4. **Execution Phase**:
   - **EARLY**: > 10m remaining.
   - **MID**: 5m - 10m remaining.
   - **LATE**: 1m - 5m remaining.

## 5. Settlement

Trades are settled based on the **Chainlink price feed** for BTC/USD at the exact moment of the Polymarket expiry (`endDate`). This ensures the bot's paper trading records match the real-world outcome of the binary options.
