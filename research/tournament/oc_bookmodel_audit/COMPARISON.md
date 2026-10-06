# oc_bookmodel audit — comparison (pre-run, blind)

Audited: `research/tournament/oc_bookmodel_impl/` (C1 `c1_pooled_tvflow.py`, C2
`c2_rank_calibrated.py`, shared `common_impl.py`, `kpack_C1/`, `kpack_C2/`,
`REPORT.md`) vs `docs/opencode/BOOKMODEL_PLAN_20261006.md` §(c)+§(e) under the
AGENTS.md ZERO DATA LEAKAGE rule. Detail: `AUDIT.md` in this folder. Regression
tests: `tests/test_oc_bookmodel_audit.py` (9 tests, green — including a pin for F1).

## Verdict

bookmodel: FAIL

Do NOT upload C1/C2 to Kaggle until F1 is fixed and this audit is re-run.

## Findings (file:line)

- F1 [FAIL, blocker] C2 trains on its own label — `research/tournament/oc_bookmodel_impl/common_impl.py:251-256` (`feature_list` excludes only `y*`, keeps `rank42`); label created at `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:79`; consumed as a feature at `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:149` (ranker fit), `:150-151` (calibrator fit), `:152-154` (predict); wired via `:167-168` and `:188-189`. Kpack inherits it at `research/tournament/oc_bookmodel_impl/kpack_C2/common_impl.py:251` + `research/tournament/oc_bookmodel_impl/kpack_C2/c2_rank_calibrated.py:149`. Fix: exclude `rank42` (and `pred`) from features, rebuild kpacks, re-audit.
- W1 [WARN] C2 calibration split is random, not time-last-20% — `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:141-147` (`.sample()` before `iloc` split; docstring at `:18` and comment at `:144` claim time split). Pre-cutoff so no leakage; fix the order or the doc.
- W2 [WARN] `feature_list` allowlist fragile — `research/tournament/oc_bookmodel_impl/common_impl.py:251-256` passes through any non-`y*` label/`pred` column. Recommend explicit denylist.
- N1 [NOTE] dead `pass` loop over `FINAL_ANCHOR` — `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:147-148` (no fit inside; verified harmless; delete for clarity).
- PASS (1) features causal — `research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py:27-170`, `research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py:27-51`, `research/tournament/oc_bookmodel_impl/common_impl.py:42-43,157-178`; truncation 0.0 on 3 anchors.
- PASS (2) label windows — `research/tournament/oc_bookmodel_impl/common_impl.py:98-129` + `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:81-112` (C1 h=3/18/42); `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:135-136` (C2 mask correct, contaminated by F1).
- PASS (3) fits pre-cutoff — C1 no scaler; C2 calibrator `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:84-101` fit on train fold only.
- PASS (4) quarterly cutoffs — `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:85-93`, `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:126-134`, `research/tournament/oc_bookmodel_impl/common_impl.py:51-57`.
- PASS (5) universe fixed Dec-2020 — `research/tournament/oc_bookmodel_impl/common_impl.py:60-64,181-222` (72 alts, majors excluded).
- PASS (6) kpacks clean + in sync — `research/tournament/oc_bookmodel_impl/kpack_C1/`, `research/tournament/oc_bookmodel_impl/kpack_C2/` (byte-identical scripts, metadata private/no-GPU/no-net, no data/credentials).
- PASS (7) 2025-09-24 unused in training/selection — `research/tournament/oc_bookmodel_impl/common_impl.py:18-19`, `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:120,147-156`, `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:166,193-200`.
