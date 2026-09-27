# pattern_lab W3: technical indicators (read OPENCODE_PATTERN_LAB_COMMON.md first)

Files you may write: `src/agentic_alpha_lab/patterns/indicators.py`,
`tests/test_pattern_lab_indicators.py`, `research/pattern_lab/indicators_study.py`,
`artifacts/research/pattern_lab/indicators/*`. Column prefix: `ind_`.

compute(): scale-free versions of RSI(14, 7), Stochastic %K/%D, StochRSI,
MACD (12,26,9) line/signal/hist divided by ATR or price, Bollinger %B and
bandwidth, Keltner position, ATR/price, ADX/+DI/-DI, CCI, Williams %R, MFI, OBV
slope z-score, CMF, ROC, Aroon, Ichimoku (tenkan/kijun/cloud distances; NO
chikou span or anything shifted forward in time), Supertrend(10,3) state and
distance, Parabolic SAR state, SMA/EMA 20/50/100/200 distances and slopes, MA
ribbon order score, VWAP(rolling 24 bars) deviation, volume z-score, taker buy
ratio, funding rate (known at or before bar close) level and 7-day mean.
Use Wilder smoothing where standard. Recursive indicators must be computed
forward only (no backfill).
events(): RSI 30/70 re-cross, stochastic cross in extreme zone, MACD signal
cross and zero cross, Bollinger band re-entry and breakout, Supertrend flip,
PSAR flip, golden/death cross 50/200, ADX>25 with DI cross, Ichimoku TK cross
and cloud breakout, Donchian-free (W2 owns Donchian), RSI divergence (only with
causal pivots; confirm divergence at the bar it becomes known).
