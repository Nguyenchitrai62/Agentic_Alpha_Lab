# Testsuite report 2026-10-06 (OPENCODE_W_ops_testsuite)

Command: `.venv/Scripts/python.exe -m pytest -q tests -p no:randomly`
Date (UTC): 2026-10-06. Exit code: 1.
Result: 2766 collected (separate `--collect-only` count), **20 FAILED, 2 skipped, 0 errors**.
Derived passed: 2744. No `ERROR` lines; skips visible as 2 `s` marks in `-q` progress
(skip ids not captured; no `-rs` rerun done). Only `tests/` was run, once.
No code edited, no commits. AGENTS.md scope/cost rules untouched.

## Classification summary

| Bucket | Count | Tests |
|---|---|---|
| A. Pre-existing frozen-hash / frozen-string drift (tracked files, clean tree, mutually inconsistent at HEAD) | 14 | test_r78_nonwait (1) + v218..v304 engine source-string asserts (13) |
| B. Research-folder generated artifacts missing/ignored/stale | 6 | test_oc_g2k20robust (5) + test_oc_frontier::test_rows_match_sources (1) |
| C. Data not on disk (own bucket) | 0 | none beyond B (S4/S5 pkls covered in B4) |
| D. Real regressions in tracked code (bot/, backend/, scripts/, engine_user behavior) | 0 | none proven; engine_user semantic equivalence still to be confirmed by leader (see A2) |

## A. Frozen drift (14)

### A1. test_r78_nonwait.py::test_prespec_frozen_shas — runner_config SHA drift
- Error line: `tests/test_r78_nonwait.py:31` -> fails in `scripts/opencode_r78_nonwait.py:100`
  (`assert _sha(RUNNER_CONFIG_PATH) == fp["runner_config_sha256"]`).
- Cause: research config, checkpoints and calibrators verify OK (earlier asserts in
  `verify_frozen` pass); only `RUNNER_CONFIG_PATH = configs/opencode_r77_advisor.json`
  no longer matches `runner_config_sha256` frozen in `configs/opencode_r78_nonwait.json`.
  The runner config was edited after the prespec SHA was recorded.
- Minimal fix: leader decides — either re-freeze the prespec SHA (if the config edit was
  approved) or revert `configs/opencode_r77_advisor.json` to the frozen content.
  Fail-closed test is working as designed; do not weaken it.

### A2. Engine source-string asserts stale after tracked engine refactor (13 tests)
Failing tests (all `AssertionError` on an `inspect.getsource(eu.simulate)` literal):

| Test id | Error line | Asserted literal (absent) |
|---|---|---|
| test_v218_v219_audit.py::test_book_mult_threshold_unscaled_and_sleeve_isolation_in_engine | :59 | `risk_open + rn * (m_sleeve_sl * sg + gap) > sleeve_risk_budget` |
| test_v221_audit.py::test_engine_threshold_fill_and_sleeve_isolation | :87 | same as above |
| test_v222_audit.py::test_engine_threshold_fill_and_subaccount_isolation | :108 | same as above |
| test_v223_v224_audit.py::test_engine_trade_mode_conventions | :76 | same as above |
| test_v225_v226_audit.py::test_engine_trade_mode_conventions | :82 | same as above |
| test_v227_v229_audit.py::test_engine_trade_mode_conventions | :76 | same as above |
| test_v230_audit.py::test_engine_trade_mode_conventions | :77 | same as above |
| test_v231_audit.py::test_engine_trade_mode_conventions | :81 | same as above |
| test_v232_v233_audit.py::test_engine_trade_mode_conventions | :78 | same as above |
| test_v234_audit.py::test_engine_trade_mode_conventions | :80 | same as above |
| test_v301_audit.py::test_engine_and_selection_guards | :83 | `risk_open = sum(t[7] * (m_sleeve_sl * t[6] + gap)` |
| test_v302_v303_audit.py::test_engine_and_selection_guards | :97 | same as above |
| test_v304_audit.py::test_engine_and_selection_guards | :104 | same as above |

- Cause: `research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py`
  (tracked, working tree clean) was refactored after these audits were written. Current
  source (lines ~690-696) computes the same sleeve-risk budget via helpers with an
  epsilon, e.g. `risk_open = sum(t[7] * (_msl(t[2]) * t[6] + gap) ...` /
  `over = risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget + 1e-12`
  (plus a `sleeve_budget_sl` variant). All earlier asserts in each test pass
  (book_mult ordering, `win_start`, stop-wins-tie, MAKER/TAKER/FUND_LONG); only the
  risk-budget literal fails. Recent engine history (`sleeve_gross_cap` hook, per-coin
  `sleeve_sl_coin`, v417 cascade controls) is consistent with an intentional refactor,
  not a reverted feature.
- Minimal fix: leader confirms the `_msl`/`+1e-12` refactor is intentional and
  behavior-preserving (one replay parity check), then updates the 13 asserted literals
  to the new canonical form. If the refactor was NOT approved, revert engine_user.py
  instead. Do not silently edit either side; this is bucket A, not a proven bucket D
  regression — no failing test shows changed backtest behavior, only changed source text.

## B. Research-folder artifacts (6)

### B1-B5. test_oc_g2k20robust.py — generated files absent (gitignored)
- Error lines: `:20` (test_files_exist), `:27`, `:41`, `:49` (all via `_res()` at `:15`),
  `:67` (test_report_verdict). All `AssertionError`/`FileNotFoundError` for
  `research/diagnostics/oc_g2k20robust/results.json` and `REPORT.md`.
- Cause: both paths are gitignored (`research/diagnostics/` rule); the folder holds only
  `robust_g2k20.py` + run pkls. The study was never run to completion on this machine:
  at test time S1/S2 pkls present; S3 pkl appeared during this assignment (another
  worker/leader job seems to be generating them now); S4/S5, `results.json`, `REPORT.md`
  still absent. Tests 2-5 all funnel through the missing `results.json`.
- Minimal fix: run `robust_g2k20.py` to regenerate all artifacts, then rerun these tests;
  or mark the 5 tests skip with reason "generated gitignored study artifacts not on disk".
  Do not hand-write `results.json`/`REPORT.md`.

### B6. test_oc_frontier.py::test_rows_match_sources — stale derived table
- Error line: `tests/test_oc_frontier.py:54`
  (`assert r["audited"] == audited` -> `('v421', 'R2B1D17BF'): assert False == True`).
- Cause: `research/tournament/oc_frontier/` is untracked (generated); its `results.json`
  says v421/R2B1D17BF `audited: False` but the source
  `research/parallel/rounds/parallel-20260906-r2/v421/result_manifest.json` now records
  `audit.passed: True`. The manifest was updated (audit PASS) after the frontier table
  was built; all other fidelity checks in the file pass (row counts, Pareto, artifacts).
- Minimal fix: rerun the tracked builder `research/tournament/oc_frontier/build_frontier.py`
  to refresh `results.json` (and REPORT/frontier.png if affected), then rerun the test.
  Alternative: mark skip with reason only if the leader abandons the frontier folder.

## Notes for the leader
1. No failure implicates `bot/`, `backend/`, `scripts/` behavior or backtest numerics;
   `test_engine_trade_mode.py`, `test_engine_user*`, bot parity/resilience/risk-guard and
   web suites all pass.
2. Suggested order: A1 (one-line re-freeze/revert decision) -> B6 (rebuild frontier table)
   -> B1-B5 (finish/skip g2k20robust study) -> A2 (confirm engine refactor, refresh 13
   literals at once since they share one root cause).
3. Pre-existing tree state (not mine, left untouched): `M research/parallel/registry.json`
   plus unrelated untracked files; `research/diagnostics/oc_g2k20robust/runs_G2K20_S3.pkl`
   materialized mid-assignment, suggesting a concurrent study run — avoid double-running it.
