# OpenCode task oc_fundsigndip - dip rungs larger when the coin's funding is NEGATIVE (crowded shorts -> sharper rebounds), fit-free sign rule
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_fundsigndip/` and `tests/test_oc_fundsigndip.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Rule (pre-registered, exactly two variants, no threshold fitted)
FS1: dip rung size x1.25 when the coin's last SETTLED funding rate (known before the holding bar opens) is < 0, else x1.0.
FS2: FS1 plus x0.8 when the last settled funding is > 0.0003 (3x the 0.0001 base rate, a fixed round number), else x1.0.
Data: data/raw/binance_premium_20260928 (settled funding) and the perp funding history back to its start; disclose coverage per coin / year.
## Evaluation (candidate-credibility protocol)
Pre-sample replica 2017 .. 2020-09-23 where funding exists (BTC perp from 2019-09; say what is missing) as the clean leg, the 2021-2026
replica gate (dSum5y >= +0.273, sum-half >= 4/5), and - only if both pass - the 4-phase engine vs G2 with an exposure-matched constant control
and the Bybit S5 row. Report triggers per year, boosted fill stop rates, the COVID leg. Vietnamese 3-line verdict.
