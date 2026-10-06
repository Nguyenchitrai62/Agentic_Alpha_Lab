# Fullsuite 2026-10-06 (ops_fullsuite)

## Totals (first)
TRACKED suite only: 272 `tests/*.py` files from `git ls-files tests/`
(+1 tracked non-pytest file `tests/test_web_frontend.cjs`, Node test, not run).
10 sequential chunks via `heavy_slot.py run --tag fullsuite --min-free-gb 1.5`.
No chunk skipped. 9 chunks exit 0, 1 chunk (chunk_02) exit 1.
**1944 tests: 1939 passed, 2 failed, 2 skipped, 1 xfailed, 0 errors.**
No collection errors. All failures are in chunk_02 (details below).

Per-chunk: 00: 216 pass/1 xfail (217) | 01: 216 pass | 02: 168 pass/2 fail (170)
| 03: 317 pass/2 skip (319) | 04: 238 pass | 05: 116 pass | 06: 125 pass
| 07: 174 pass | 08: 347 pass | 09: 22 pass. Counts reconstructed from
per-test progress markers (heavy_slot-captured logs end at the short summary;
final pytest count line not captured; exit codes corroborate).

Rerun note: per the assignment NOTE, no memory was inspected directly;
all chunks ran through heavy_slot (which waited for RAM; run took ~20 min).
Scratch/logs: `research/tournament/ops_fullsuite/tmp/` (logs/, chunks/).

## Failure 1
- id: `tests/test_oc_bookmodel_audit.py::test_kpack_bundles_clean_and_in_sync`
- first error: `AssertionError: ('kpack_C1', 'c1_pooled_tvflow.py')`
  (`filecmp.cmp(IMPL/f, kd/f, shallow=False)`).
- classification: ENVIRONMENT (Windows CRLF) + test depends on untracked local
  snapshot. `research/tournament/oc_bookmodel_impl/kpack_C1|C2/` are untracked
  (`??` in git status); the kpack copies have CRLF line terminators while the
  tracked files have LF. `diff --strip-trailing-cr` = 0 lines for all 4 pairs
  (c1/common_impl x2, c2/common_impl), so content IS in sync. NOT a real
  regression from any 2026-10-06 commit (impl history: 8ff8695 C1/C2 build,
  b5ec6b4 leakage fixes, 2db89a7 re-audit+test). Fix suggestion (owner):
  regenerate kpack with LF or compare text-normalized.

## Failure 2
- id: `tests/test_ops_kaggleengine.py::test_manifest_sizes`
- first error: `FileNotFoundError: ... 'artifacts/kaggle_stage/engine_data/MANIFEST.json'`
  at `tests/test_ops_kaggleengine.py:63`.
- classification: TEST DEPENDS ON UNTRACKED/IGNORED LOCAL FILE. `artifacts/`
  is gitignored; `engine_data/` exists locally (staged bundle dirs + metadata)
  but `MANIFEST.json` was never generated here, and no in-repo script writes
  that path (only the test references it). Test added 2026-10-06
  (b2b0fa2 bundle, 343d020 smoke test). NOT a code regression: sibling tests
  in the same file passed (incl. `test_bundle_outside_repo_imports_and_smoke`
  50.17 s, `test_smoke_kernel_matches_direct` 19.97 s).

## 15 slowest tests (union of per-chunk top-15; boundary approximate)
1. 174.21 s `test_bot_soak_smoke.py::test_soak_2h_no_violations`
2. 114.06 s `test_oc_bookmodel_evalprep.py::test_end_to_end_reproduces_v421_g2_dev_years`
3. 65.03 s `test_oc_regime.py::test_truncate_recompute_20_days`
4. 61.11 s `test_paper_trader_v21.py::test_resume_long_trackc_replay_identical`
5. 50.17 s `test_ops_kaggleengine.py::test_bundle_outside_repo_imports_and_smoke`
6. 36.82 s `test_v90_package.py::test_smoke_run_cpu_subset`
7. 30.58 s `test_paper_trader_v21.py::test_real_drill_trip_blocks_later_real_signals`
8. 23.20 s `test_oc_bookmodel_impl.py::test_c1_smoke_cli`
9. 19.97 s `test_ops_kaggleengine.py::test_smoke_kernel_matches_direct`
10. 18.68 s `test_oc_bookmodel_impl.py::test_c2_smoke_cli`
11. 18.60 s `test_ops_jitterjob.py::test_smoke_kernel_matches_direct_base`
12. 14.52 s `test_pattern_lab_chart.py::test_causal_real_1h_4h_1d`
13. 13.41 s `test_r78_accept.py::test_w1cli_kill_before_commit_recovers`
14. 12.09 s `test_r78_roll.py::test_cli_kill_after_commit_and_export_rebuild`
15. 12.06 s `test_r78_roll.py::test_cli_kill_before_commit_recovery`

Note: 2 skipped (chunk_03) + 1 xfailed (chunk_00) ids not captured
(`-q` logs lack `-rs` lines); no flaky verdict — nothing was rerun.
Git was read-only (status/diff/log/show only); no code, test, or commit changes.
