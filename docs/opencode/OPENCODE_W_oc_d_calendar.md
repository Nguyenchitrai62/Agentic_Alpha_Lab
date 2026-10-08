# OpenCode task oc_d_calendar - IDEAS12 #4: Thin-book calendar tilt
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_d_calendar/` and `tests/test_oc_d_calendar.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine / 1m work via scripts/heavy_slot.py (RAM tight: one job at a
time, one coin at a time, float32). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
Implement idea #4 of docs/opencode/IDEAS12_20261008.md EXACTLY as written (rule, the two pre-registered variants with frozen constants,
data, harness, leakage notes). PRIMARY clean test: the pre-sample dip replica 2017 .. 2020-09-23 (research/tournament/oc_presampletilt /
oc_cboostpre machinery; reproduce their base sums exactly first): per year normalised gain vs no change, timing placebo pct where the idea is a
timing rule, boosted / skipped fill stop rates, the COVID leg separately. SECONDARY: the 2021-2026 replica gate (oc_k2placebo ledger,
dSum5y >= +0.273 and sum-half >= 4/5) and, only for a variant that helps on the pre-sample AND passes the secondary gate, the 4-phase engine vs
G2 (reproduce 5.41 / 16.91 / 16.82 first) with an exposure-matched constant control and the Bybit S5 row. Apply the candidate-credibility
checks (sign-stable / fit-free rule, beats the exposure control, Bybit leg, pre-sample leg).

## Report
Pre-sample table, 2021-2026 replica gate, engine rows if run (dev4 robust pick, post-release year scored ONCE for the pick and REF, 5y,
full-path DD), and a Vietnamese 3-line verdict.
