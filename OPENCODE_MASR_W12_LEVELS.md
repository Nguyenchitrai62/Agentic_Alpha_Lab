# ma-sr W12: moving averages as support/resistance across 15m/1h/4h/1d (read OPENCODE_VF_COMMON.md first)
User hypothesis (2026-09-24): MA Ribbon lines on 15m/1h/4h (and 1d) act as fairly precise
support/resistance. Test it causally and honestly.
Files: `src/agentic_alpha_lab/patterns/ma_levels.py`, `tests/test_masr_levels.py`,
`research/masr/levels_study.py`, `artifacts/research/masr/levels/*`.
Data: 15m bars via `fetch_klines("BTCUSDT","15m",...)` into
`data/raw/btc_intraday_20260924/klines_15m.parquet` if W11 has not produced it yet
(coordinate: if the file exists, read it; else fetch and save it yourself), 1h/4h/1d via
`common.load_bars(tf, include_opened_year=True)` for FEATURES; returns only via event_study
rules (decisions < 2025-09-14).
MAs per timeframe TF in {15m,1h,4h,1d}: SMA and EMA 20/50/100/200 (TradingView MA Ribbon
defaults). A higher-TF MA is known on a 15m bar only from the last CLOSED higher-TF bar
(as-of join on close_time). Use the MA value as of the previous closed bar of its TF for
touch tests inside the current bar (no same-bar MA).
compute(bars) (works on 15m, 1h, 4h input bars): for each TF/MA: signed distance of close
to the MA in ATR14 units of the input TF; MA slope; count of touches in the last 50 input
bars; nearest support MA below and nearest resistance MA above (distance in ATR, TF,
period); confluence = number of distinct TF/MA levels within 0.5 ATR of the nearest
level; ribbon order score per TF (+4 fully bullish ... -4 fully bearish).
events(bars): per TF/MA family (group periods to keep the count manageable):
- `bounce_support` (+1): prior 10 input bars closed above the level, current low <= level
  and close >= level;
- `reject_resistance` (-1): mirror;
- `break_down` (-1): prior close above, current close below level by > 0.2 ATR;
- `break_up` (+1): mirror;
- confluence versions (>= 3 levels within 0.5 ATR) of bounce/reject.
Study A (next-open entry): `common.event_study` on 15m (horizons 4,16,48), 1h (1,4,12),
4h (1,3,6).
Study B (limit at the level, the realistic way to trade S/R): for bounce events enter at
the level price (the bar traded through it) and measure forward return from the level
price to close after h bars; compare with a placebo: identical procedure at a level
offset by +/- the same ATR distance from a random nearby price that is NOT an MA (same
trend filter). Report mean bps, hit rate, NW t-stat, and the difference vs placebo.
S/R is only real if MA levels beat the placebo levels after costs (~2-4 bps maker).
Summarize in <= 15 lines: which TF/MA/confluence, if any, beats placebo and is stable
across the two halves of development.

## Addendum from the leader (user clarification 2026-09-24 16:15 UTC)
The user's TradingView "MA Ribbon" is the built-in script with SMA 50, SMA 200, SMA 100,
SMA 200 on close (yellow = SMA50, purple = SMA200; verified against the user's 5m Bybit
screenshot to < 1 USD). Make sure the study reports the SMA 50/100/200 rows separately
(the user's exact lines), and if time allows add the 5m timeframe as an input/level TF.
