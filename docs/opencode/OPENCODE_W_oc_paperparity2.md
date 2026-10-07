# OpenCode task oc_paperparity2 - after the two bot fixes (cb14cb7 exits, b5f12b0 dust): do the paper runners trade what the research engine trades?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_paperparity2/` and `tests/test_oc_paperparity2.py`.
artifacts/bot/* READ-ONLY; never start / stop processes.

## Context
An earlier parity check (oc_planparity: 0 plan mismatches) compared PLANS. Fills / exits were never compared after the 2026-10-07 fixes.
The paper runners replay live Bybit 1m klines (bot/paper.py); research uses Binance 1m with the 4-phase engine. Window: from 2026-10-07
12:30 UTC (all runners restarted on b5f12b0 at ~12:22 UTC) to the last complete hour.

## Tasks
1. For the deployment runner artifacts/bot/paper_d17bfg2 (G2) and artifacts/bot/paper_d17bfg2c (G2 + carry): extract every dip rung fill,
   TP, close5 stop, time exit and book order fill from actions.jsonl / exchange.json (piece ids encode phase / coin / depth: read bot/mirror.py).
2. Recompute what the RESEARCH rules would have done in the same window from the same plan file the runner used
   (artifacts/research/advisor_shadow/trade_plan_v376.json history if kept; else the per-cycle plan snapshots in the runner logs) and Bybit
   public 1m klines (GET /v5/market/kline, public): rung prices, fill minutes (strict trade-through, minute >= 16 of the bar as the engine),
   TP / close5 / timeout exits. Compare piece by piece: missing / extra fills, fill-minute differences, exit-type differences, P&L difference.
3. Report: a table per runner (counts and P&L: bot vs research replay), every mismatch with its cause (venue price difference, timing,
   bug). Any mismatch caused by bot logic -> describe a minimal reproduction (do not edit bot/). Vietnamese 3-line verdict.
