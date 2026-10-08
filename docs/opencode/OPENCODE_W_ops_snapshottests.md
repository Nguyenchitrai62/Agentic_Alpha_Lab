# OpenCode task ops_snapshottests - make 8 research snapshot tests robust to live-growing artifacts (without weakening real checks)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. You MAY edit ONLY these test files: tests/test_oc_bookoos.py, tests/test_oc_oos12d.py,
tests/test_oc_carryparity.py, tests/test_oc_eventblk.py, tests/test_oc_frontier.py, tests/test_oc_bookmodel_reaudit.py; write notes to
`research/diagnostics/ops_snapshottests/`. Do NOT edit research artifacts, results, scripts or data to make tests pass. Print progress every 10 minutes.

## Failures (2026-10-08 run, pytest -q)
- test_oc_bookoos.py (3) and test_oc_oos12d.py (1): the OOS window end moved 2026-10-06 -> 2026-10-07 (days 6 -> 7, totals rounded).
- test_oc_carryparity.py: n_decisions 145 != 144 (the live carry ledger loop keeps appending decisions).
- test_oc_eventblk.py::test_calendar_utc: sha256 of the cached FOMC calendar html differs from the manifest.
- test_oc_frontier.py::test_rows_match_sources: audited flag for ('v421', 'R2B1D17BF') differs from the result_manifest.
- test_oc_bookmodel_reaudit.py::test_kpack_bundles_clean_and_in_sync: kpack_C1 c1_pooled_tvflow.py differs from oc_bookmodel_impl.
## Task
For each failure: find out (read code, manifests, file mtimes; never modify the artifacts) WHY the artifact changed - a live loop appending
data (expected), a regenerated file, or a real inconsistency someone introduced. Then:
- expected growth -> rewrite the assertion to check the invariant (e.g. window starts at 2026-09-24 and ends at or after 2026-10-06; totals
  recomputed from the same file; n_decisions >= 144 and the first 144 rows unchanged vs a stored hash) instead of a fixed snapshot;
- a real inconsistency -> keep the test failing and document the cause precisely in research/diagnostics/ops_snapshottests/REPORT.md
  (who / what changed it, with paths and mtimes) for the leader.
Run the 6 test files at the end and report pass / fail. Vietnamese 3-line summary.
