# OpenCode task oc_weeklybook - IDEAS10 #6: Weekly-decision book sleeve (slow diversifier) alongside 4h G2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_weeklybook/` and `tests/test_oc_weeklybook.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome (docs task: a short PLAN section at the top of your folder's notes).
Heavy work via scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
Implement idea #6 of docs/opencode/IDEAS10_20261008.md EXACTLY as written (rule, the two pre-registered variants, data, harness,
leakage notes) - read the whole file and the CLOSED rows it cites first. Engine ideas: 4-phase engine vs G2 (v421 R2B1D17BFG2; reproduce 5.41 /
16.91 / 16.82 to the digit first) plus an exposure-matched control where exposure changes; also report the Bybit-price row (S5, harness of
research/tournament/oc_c2bybit) for the dev4 pick. User trade rules (AGENTS.md) bind: limit entries unless the idea is explicitly a stop-entry
order (then trade-through fills only, taker fee), every position has a stop and a TP, stop-first.

## Report
Per year table where applicable (dev 2021-2024; post-release year scored ONCE for the dev4 robust pick and REF only, labelled), dev4 robust
pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST, ties -> mean), 5y, full-path DD, the leakage checklist, Vietnamese 3-line verdict.
