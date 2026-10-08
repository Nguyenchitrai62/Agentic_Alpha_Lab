# OpenCode task oc_venueladder - venue-consistent dip ladder: rung prices and sigma from BYBIT's own 4h bars when trading on Bybit
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_venueladder/` and `tests/test_oc_venueladder.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Why
research/tournament/oc_bybitgap: G2 loses ~0.5 %/month on Bybit prices and the gap rides the dip ladder (fewer rung / TP fills). The engine's
S5 row trades on Bybit prices but (check this first, cite code) may still build rung prices and sigma from Binance data. A ladder anchored
on Bybit's own open and sigma would match the venue's wick distribution - a fit-free change.
## Variants (exactly two)
VL1: rung / TP / stop prices from Bybit's own 4h open and Bybit sigma360; VL2: Bybit open, Binance sigma. Everything else G2, on Bybit S5
prices (harness research/tournament/oc_c2bybit). If the S5 harness already uses Bybit opens and sigma, report that and stop (no variant).
## Report
REF_S5 vs VL1 / VL2: dev4 per year / mean / WORST / DD, robust pick on dev4 ONLY, post-release year once (labelled), 5y, full-path DD, rung /
TP fill counts. Vietnamese 3-line verdict.
