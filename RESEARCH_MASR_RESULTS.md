# MA-Ribbon support/resistance and multi-timeframe model (ma-sr), 2026-09-24

User request: target 5% per month (1.05^12 = +79.6% per year); test (a) a model
fed with indicator/MA-Ribbon parameters and (b) TradingView MA Ribbon lines on
15m/1h/4h as support/resistance. The user's MA Ribbon is the built-in script
with SMA 50 (yellow), SMA 200 (purple), SMA 100 (hidden), verified against their
5m Bybit screenshot to < 1 USD (Bybit SMA50 83,953.7 vs 83,954.4 shown;
SMA200 83,938.2 vs 83,938.4).

## (a) Multi-timeframe MA-Ribbon model (`src/agentic_alpha_lab/models/mtf.py`)

100 causal features per 1h bar (SMA/EMA 20/50/100/200 distance in ATR, slope,
touch count, ribbon order, nearest support/resistance MA, confluence) for 1h,
4h and 1d; HGB regressor on 4/12/24h vol-normalised returns, walk-forward from
2021, frozen for the hidden year. Spearman IC by year between -0.063 and +0.041;
hidden-year IC 0.01-0.03; hidden top-decile predictions earned less than the
bottom decile at 4h. Best selected config: hidden year +1.2% / -1.0% stress.
Rejected.

## (b) MA lines as support/resistance

- W12 (OpenCode) event study, 15m/1h/4h/1d levels, 432 rows: 0 stable
  significant; near-misses point against the hypothesis (4h SMA confluence
  "support bounce" followed by -32 bps over 12h in both halves). Study B, limit
  entry at the level vs placebo levels at the same distance: median difference
  0.2 bps; confluence adds nothing (`artifacts/research/masr/levels/`).
- Leader limit-order lab (`scripts/masr_limit_lab.py`, engine
  `src/agentic_alpha_lab/backtest/limit_levels.py`, real 1m bars,
  trade-through fills, stop-first, gap fills at the open, maker 0.02%,
  taker 0.05% + 0.02% stop slippage): orders resting at the nearest user
  SMA 50/100/200 level of 15m/1h/4h lose -6.9 to -7.6 bps per trade in both
  development (~19k trades) and the hidden year (~1.4-4.5k trades), the same as
  placebo levels (-6.5 to -7.3 bps). Win rate 47% at 1:1.

Conclusion: in this data the MA Ribbon lines are not better support/resistance
than any other nearby price; their visual reliability comes from price
revisiting all nearby levels.
- Full grid (64 configs: distance band, stop 0.5/1 ATR, R 1/2, hold 4/16h, trend
  filter, shorts): 0 profitable configs in development or hidden year; median
  MA minus placebo -0.33 bps (dev) and -0.27 bps (hidden).
