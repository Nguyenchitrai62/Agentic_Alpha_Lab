# oc_wfselect PLAN (pre-registered BEFORE computing outcomes; 2026-10-06)

## Hypothesis
Walk-forward meta-selection with the AGENTS.md robust criterion picks variant
rows that generalise to the next anchor year. Null: the candidate pool was
wholly designed after seeing all five years, so even a walk-forward chain over
years 1..4 is optimistic and need not beat holding the deployed row.

## Candidate set (fixed)
31 unique rows with cached 4-phase runs. Source map (first-seen cache wins;
duplicates verified identical via year_reset spot-check BEFORE outcomes:
R2B1D17BF identical in v411/v415/v417/v418, R2B1D16 identical in v406/v411,
R2B1D17BFG2 identical in v421/v422 — no selection outcomes inspected):
- v406/v406_runs.pkl: R2B1D16, R2B1D18B08, R2B1_130
- v411/v411_runs.pkl: R2B1D17BF (+dup R2B1D16)
- v415/v415_runs.pkl: R2B1D17BFS5, R2B1D17BFS6
- v417/v417_runs.pkl: R2B1D17BFC, R2B1D17BFCX, R2B1D17BFX
- v418/v418_runs.pkl: R2B1D17BFDS
- v419/v419_runs.pkl: R2B1D17BFBRK05, R2B1D17BFBRK08, R2B1D17BFBUD13
- v420/v420_runs.pkl: R2B1F15K20, R2B1F15K23, R2B1F20K17, R2B1F20K20
- v421/v421_runs.pkl: R2B1D17BFG2, R2B1D17BFG3
- v422/v422_runs.pkl: G15K20, G2F20K20, G2K20 (+dup R2B1D17BFG2)
- v423/v423_runs.pkl: R2B1D17BFX45, R2B1D17BFX45G2, R2B1D17BFX5
- research/diagnostics/oc_plateau/oc_plateau_runs.pkl: R2B1D17BF_F20,
  R2B1D17BF_F30, R2B1D17BF_MA900, R2B1D17BF_MA1500, R2B1D17BF_BM035,
  R2B1D17BF_BM065 (+dup R2B1D17BF reference = v411 cache)
Deployed baseline row: R2B1D17BF.

## Exact causal definitions
- Anchor years y=0..4 = [2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24,
  2025-09-24], each +365 d. Market data cap 2026-09-24 00:00 UTC.
- Per-year stat = research/diagnostics/r2_decompose5/reset_metric.py
  `year_reset(runs, strat, y)` exactly (4 sub-accounts reset to 1/4 capital at
  each anchor; R = 100*(prod^(1/12)-1) monthly %; DD = max yearly DD %).
  No refit, no 1m data, no parameter choice on test years.
- Geometric mean over a set S of years: 100*(prod_{y in S}(1+R_y/100)^(1/|S|)-1).
- Meta-causality: pick for test year k uses ONLY selection years {0..k-1}.
  Scoring on year k uses only that year's reset segment. k=1..4
  (anchors 2022-09-24..2025-09-24). k=0 has empty selection set: not scored.

## Decision rules (fixed)
- Rule A (AGENTS robust): eligible = rows with every selection-year DD <= 20
  AND no losing selection year (R >= 0; exactly 0 counts as not losing).
  If >=1 eligible with geo-mean >= 5: pick highest worst-year R; ties ->
  higher geo-mean; ties -> alphabetical row name. Else if >=1 eligible: same
  ordering among all eligible. Else (no eligible): fallback = highest
  geo-mean among ALL rows (disclosed as fallback, counts as unstable).
  For k=1 the window is {2021} only, so mean = worst = that year's R.
- Rule B (simple DD18): eligible = rows with every selection-year DD <= 18
  (no return filter); pick highest geo-mean; ties -> alphabetical. Fallback =
  highest geo-mean among ALL rows if none eligible.
- Baselines: ALWAYS-R2B1D17BF (hold R2B1D17BF every test year);
  BEST-IN-HINDSIGHT = row with highest geo-mean over test years 1..4 among
  the 31 (oracle for the scored window; ties -> higher worst, then name).
- LOO stability: for each k>=2, recompute Rule-A pick on each leave-one-out
  subset of {0..k-1} (k subsets); stable(k) = all LOO picks == main pick(k).
  k=1 has no LOO (reported N/A, excluded from denominator).

## Effect + verdict rule
- Per-test-year effect e_k = R_WF_A(k) - R_BASE(k) (pp/month, Rule-A WF pick
  minus always-R2B1D17BF). Sign = positive excess.
- PROMISING only if (a) e_k > 0 in >= 3 of 4 test years AND (b) stable(k) in
  >= 3 of 3 testable years k=2..4 (adapted from the default >=4/5: only 4
  test years exist and k=1 has no LOO; thresholds 75%/100% disclosed).
  Otherwise NOT PROMISING. One-line verdict in REPORT.md.
- Optimism caveat (mandatory in REPORT): candidates were all designed after
  seeing the five years, so even this walk-forward chain is optimistic.

## Outputs + resources
- scripts/run_wfselect.py (single process, RAM < 1 GB, loads one runs.pkl at
  a time, no 1m data), results.json, REPORT.md (tables + one-line verdict),
  tests/test_oc_wfselect.py (reruns selection from results.json caches).
- No commits; write ONLY under research/tournament/oc_wfselect/ + the test.
