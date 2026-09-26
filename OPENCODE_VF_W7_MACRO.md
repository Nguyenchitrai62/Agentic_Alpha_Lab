# vf W7: macro risk regime for BTC (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/macro.py`, `tests/test_vf_macro.py`,
`research/vf/macro_study.py`, `artifacts/research/vf/macro/*`,
`data/raw/macro_20260924/*` (all downloads/temp files here, never outside the workspace).
Data: daily closes 2019-06-01..2026-09-23 for SPY, QQQ, ^VIX (or VIXY), DX-Y.NYB (or UUP),
^TNX (or IEF), GLD. Prefer the public Stooq CSV endpoint
`https://stooq.com/q/d/l/?s=<symbol>&i=d` (e.g. spy.us, qqq.us, gld.us, uup.us, ief.us, vixy.us);
existing partial files in `data/raw/opencode_macro_yahoo_20220101_20260907` may help.
Record source URL, row counts and SHA-256 in a manifest.
Availability: a US daily close is known only after 21:00 UTC of that trading day
(use 22:00 UTC to be safe); weekends/holidays carry the last known value.
compute(): per asset distance to 50/200-day SMA, 20-day return, 20-day realized
vol, risk-on score (SPY>200d, QQQ>200d, VIX<20d median, DXY<200d), rolling 60-day
correlation of BTC daily returns with QQQ (as-of), DXY 20-day change.
events(): risk-on regime switch (+1 when risk-on score rises to >=3, -1 when it
falls to <=1), VIX spike (VIX 20% above 20-day mean -> -1), DXY breakout (-1).
Event study on 4h and 1d BTC bars.
