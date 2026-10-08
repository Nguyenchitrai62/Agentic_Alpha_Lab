# OpenCode task oc_haltsim - simulate the LIVE_RAMP halt rules on 9 years of paths (how often they halt, what they cost, what they save)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_haltsim/` and `tests/test_oc_haltsim.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Task
docs/LIVE_RAMP_VI.md defines H2 (28-day sleeve DD > 17.0 % -> stop new entries for 4 weeks, keep SL / TP) and V2 (90-day DD > 19 % -> halve
size). Simulate both on stored equity paths: G2 2021-2026 (v421 4-phase runs, Binance and Bybit S5), G2 + C2, G2 + B7 (oc_cascadeboost /
oc_cboostbybit runs), and the dip-only pre-sample replica 2017-2020 (oc_presample2 / oc_presampleg2). Approximate "stop new entries" as
holding the existing exposure flat and missing new trades for 4 weeks (state the approximation). Report per path: number of halts, dates,
return with vs without halts, max DD with vs without, and whether halts fired before or after the worst part of each crash leg. No tuning of
the bounds (they are frozen from dev); if they look badly placed, say so without changing them. Vietnamese 3-line verdict.
