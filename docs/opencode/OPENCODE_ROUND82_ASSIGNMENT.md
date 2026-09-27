# R82: independent replication of MA-ribbon protocol + prospective shadow log

Assigned 2026-09-24 by the Claude Code leader on the user's explicit request
(user asked to evaluate TradingView MA Ribbon SMA50/SMA200 and to use OpenCode
as a contributor). R81 (serving-guard lineage) is SUPERSEDED by this round; do
not work on it now. Same session, same model, no --auto, no cloud upload, no
heavy training, no live orders, no exchange credentials. Do not edit ../Kronos,
the Codex registry, or files listed under "do not read" below.

## Why

The leader ran pre-registered protocol `configs/ma_ribbon_r1_protocol.json`
(SHA-256 f5642fdb...). One implementation is not evidence. You must reproduce
the headline numbers from the protocol text alone so engine bugs surface.

## A. Blind replication (do this FIRST)

Do NOT open these until A is written and saved:
`src/agentic_alpha_lab/backtest/ma_ribbon.py`, `src/agentic_alpha_lab/models/ma_ribbon_ml.py`,
`scripts/ma_ribbon_study.py`, `tests/test_ma_ribbon.py`, `artifacts/research/ma_ribbon_r1/`.

Inputs: `data/raw/ma_ribbon_20260924/klines_1d.parquet`, `funding.parquet`
(Binance USD-M BTCUSDT). Write your own code only under
`research/opencode_r82_ma_replication/`. Implement from the protocol:
- decision at daily close t, fill at open t+1, 1x of current equity at entry,
  compounded from 100, fee 0.0002 per fill (normal) and 0.0006 + 0.0005
  slippage per fill (stress); long pays 0.0001 per 8h funding event on current
  notional, short pays 0 (normal); open position liquidated at close of the
  bar after the last decision.
- rows: buy_hold, H1 cross long, H2 cross long/short, H3 ribbon long,
  H4 ribbon long/short (SMA50/SMA200 on daily closes).
- windows: development decisions 2019-09-08..2025-09-13, holdout decisions
  2025-09-24..2026-09-22.
Save `replication.json` with net %, fees, funding, trades, intrabar max DD
(long marks at bar low, short at bar high) per row x window x {normal, stress},
and each holdout trade (side, entry date, exit date, entry/exit price).

## B. Compare

Only after A is saved, read `artifacts/research/ma_ribbon_r1/report.json`.
Write `COMPARISON.md`: every metric difference > 0.5 percentage point or any
trade-list mismatch, with the root cause (yours or the leader's), proven by a
minimal example. Do not "fix" your numbers to match. If the leader engine is
wrong, say exactly where; do not edit the leader files yourself.

## C. Prospective shadow log (real forward test from today)

The holdout year is now opened. The only clean test left is the future.
Write `research/opencode_r82_ma_replication/shadow_log.py`: fetches closed
Binance USD-M BTCUSDT daily candles (public REST, no auth), computes H4 and the
dev-selected `4h_EMA20/200_ribbon_long` target at each new closed bar, and
APPENDS one JSON line per new bar to
`artifacts/research/ma_ribbon_shadow/shadow.jsonl` (decision time, close,
SMA50, SMA200, target, data hash). Never rewrite earlier lines; refuse if the
last logged bar is already present. It is advisory only: no order code.
Add a unit test proving the target at bar t is unchanged when later bars are
appended.

## Done criteria

`replication.json`, `COMPARISON.md`, `shadow_log.py` + test passing with
`.venv/Scripts/python.exe -m pytest tests/<your test> -q`, and a 10-line
summary at `research/opencode_r82_ma_replication/SUMMARY.md`. Stop after that.
