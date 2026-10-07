# OpenCode task audit_amihud - BLIND replication of the Amihud A1 book tilt on G2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_amihud/` and `tests/test_audit_amihud.py`.

## Blind protocol
1. Read ONLY docs/opencode/IDEAS4_20261007.md section C item H4 (variant A1), docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md and
   research/tournament/oc_lit_xs/PLAN.md. Do NOT open oc_lit_xs's code, REPORT.md, results or tmp/, nor research/tournament/oc_amihudrobust/.
2. Implement A1 independently: per coin trailing-30-day Amihud illiquidity from daily data known before the bar (state your daily source and
   the day-availability rule; PLAN.md defines it - follow it exactly), cross-sectional z across the 5 coins at each standard book row,
   multiplier (1 + 0.25 z) on long and short weights (clip / rules exactly as PLAN.md), applied with the v426 mechanism
   (research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py) on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0;
   reproduce 5.41 / 16.91 / 16.82 first). Run the 4-phase engine (heavy_slot) for dev4 and the most recent year.
3. SAVE part A `replication.json` (per year R / DD for A1, dev4 mean / worst / DD, 5y and full-path DD) BEFORE opening anything of oc_lit_xs.
4. Then compare with oc_lit_xs's REPORT / results (thresholds: R > 0.10 pp, DD > 0.5 pp) and audit its code for look-ahead (daily data
   timing, cross-sectional z at the same timestamp only, volume source), with a test for each check.
COMPARISON.md with PASS / FAIL / PASS-WITH-NOTES and causes of any mismatch. Vietnamese 3 lines. Print progress every 10 minutes.
