# OpenCode task audit_mvrv - BLIND replication of the MVRV-z cycle gate M1 on G2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_mvrv/` and `tests/test_audit_mvrv.py`.
Print progress every 10 minutes.

## Blind protocol
1. Read ONLY docs/opencode/IDEAS4_20261007.md section C item H8 (variant M1), docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md and
   research/tournament/oc_lit_position/PLAN.md. Do NOT open oc_lit_position's or oc_mvrvrobust's code, REPORT.md, results, events or tmp/.
2. Implement M1 independently from data/raw/onchain_20260924/btc.csv (CapMVRVCur): zM = (MVRV - mean) / std over the trailing <= 365 days
   (min 180) ending at day D, day D usable from D+1 02:00 UTC; all majors' book LONG weights x0.5 while zM > 2.0 (exact rules as PLAN.md),
   v426 mechanism (research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py) on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear
   True G 2.0; reproduce 5.41 / 16.91 / 16.82 first). 4-phase engine via heavy_slot; dev4 + the 5-year path.
3. SAVE part A `replication.json` (per year R / DD, dev4 mean / worst / DD, 5y, full-path DD, number of gated bars per year) BEFORE
   opening anything of oc_lit_position / oc_mvrvrobust.
4. Compare with their REPORT numbers (R > 0.10 pp, DD > 0.5 pp thresholds), audit their signal code for look-ahead (MVRV availability, the
   rolling window end, any use of future days, CoinMetrics revisions - is btc.csv a single vintage downloaded on 2026-09-24? discuss whether
   historical MVRV values could have been revised after the fact (realised cap revisions) and how that would bias the test), with tests.
COMPARISON.md: PASS / FAIL / PASS-WITH-NOTES. Vietnamese 3 lines.
