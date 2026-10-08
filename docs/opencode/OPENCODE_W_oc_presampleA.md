# OpenCode task oc_presampleA - can the A whale-flow book members be rebuilt for 2020-09 .. 2021-09 (perp flow exists from 2020-01) to test the FULL book on one more year?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presampleA/` and `tests/test_oc_presampleA.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Why
research/tournament/oc_presampleg2: the book without the A / Aq members lost in 2018-2019; A needs perp order flow that starts 2020-01. The
year 2020-09-24 .. 2021-09-23 precedes the first dev anchor; the deployed 2021 models were trained on data before 2021-09-17, so this year is
inside their TRAINING window - state clearly that it is NOT clean out-of-sample for the deployed models.
## Task
Feasibility first (data coverage of every A / Aq input for 2020-01 .. 2021-09). If feasible: train A / Aq walk-forward with an anchor at
2020-09-24 on data 2020-01 .. 2020-09-17 only (frozen builder; short training window disclosed), blend the full member set exactly as
research_books_d2, and replay book + dip sleeve on 2020-09-24 .. 2021-09-23 (replica level like oc_presampleg2; dip-only must reproduce
oc_presample2's Y2020p). Report the book vs dip P&L, with and without A. Vietnamese 3-line verdict, with the training-overlap caveat.
