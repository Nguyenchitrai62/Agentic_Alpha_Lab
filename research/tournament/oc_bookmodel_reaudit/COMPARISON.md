# oc_bookmodel re-audit — comparison (pre-run, blind, after fixes)

Audited: `research/tournament/oc_bookmodel_impl/` (C1 `c1_pooled_tvflow.py`, C2
`c2_rank_calibrated.py`, shared `common_impl.py`, `kpack_C1/`, `kpack_C2/`,
`REPORT.md`) vs `docs/opencode/BOOKMODEL_PLAN_20261006.md` §(c)+§(e) under the
AGENTS.md ZERO DATA LEAKAGE rule. Detail: `AUDIT.md` in this folder. Regression
tests: `tests/test_oc_bookmodel_reaudit.py` (10 tests, green).
Previous audit: `research/tournament/oc_bookmodel_audit/COMPARISON.md` FAIL on F1.
Fixes claimed: `research/tournament/oc_bookmodel_impl/REPORT.md` §'Fixes after audit'.

## Verdict

bookmodel: PASS

C1/C2 may be uploaded to Kaggle per the plan (dev anchors 2021-2024; 2025-09-24
scored once for the frozen finalist). Note: `tests/test_oc_bookmodel_audit.py:164-176`
still pins the OLD buggy behaviour (`rank42 in feats`) and fails by design after
the F1 fix — flip it to `rank42 not in feats` when re-running the old suite.

## Findings (file:line)

- F1 [FIXED] C2 label-as-feature excluded — `research/tournament/oc_bookmodel_impl/common_impl.py:279-281` (FEATURE_ALLOWLIST, 83 cols), `:284-295` (denylist + load assert), `:298-314` (allowlist select `:307`, denied asserts `:310-313`); consumed correctly at `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:166-169`; kpack copies `research/tournament/oc_bookmodel_impl/kpack_C1/common_impl.py:279-313`, `research/tournament/oc_bookmodel_impl/kpack_C2/common_impl.py:279-313`, `research/tournament/oc_bookmodel_impl/kpack_C2/c2_rank_calibrated.py:103-176`.
- W1 [FIXED] C2 calibration split is time-last 20%, no sampling — `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:103-115` (split_fit_cal, assert `fit.t.max() <= cal.t.min()`), `:156-165` (sort + deterministic time-last `iloc[-max_rows:]` cap, no `.sample()` in code). Pre-cutoff, doc true.
- W2 [FIXED] explicit denylist — `research/tournament/oc_bookmodel_impl/common_impl.py:284-295` (LABEL_DENY_EXACT + LABEL_DENY_PREFIXES + load assert) + per-call asserts `:310-313`.
- N1 [FIXED] dead FINAL_ANCHOR loop deleted — `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:147` (full writer loops `C.DEV_ANCHORS` only); `FINAL_ANCHOR` count 0 in both candidate scripts.
- PASS (1) features causal — `research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py:27-170` (pivots `:75-87`, ichimoku shift `:156-157`, vwap `:90-96`, poc `:99-110`), `research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py:27-51` (reindex `:51`), `research/tournament/oc_bookmodel_impl/common_impl.py:42-43,153-178` (order-level bind + (t,sym) merge), `research/parallel/rounds/parallel-20260906-r2/v103/v103_flow_short_horizon.py:49-65`, `research/parallel/rounds/parallel-20260906-r2/v92/v92_pooled_hgb_vt.py:53-84` (merge_asof `:71,75`), `research/parallel/rounds/parallel-20260906-r2/v142/v142_cross_sectional_features.py:33-39`, `research/tournament/oc_bookmodel_impl/common_impl.py:67-95` (alt 1m aggregation); truncation 0.0 on 3 anchors.
- PASS (2) label windows — `research/tournament/oc_bookmodel_impl/common_impl.py:98-129` (targets + train_mask, cutoff `cutoff_for:47-48` = anchor - 7d) + `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:81-112` (C1 h=3/18/42, mask `:94`); `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:67-81` (rank) + `:150-151` (mask `t+43*4h < cutoff`).
- PASS (3) fits pre-cutoff — C1 no scaler; C2 calibrator `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:84-101` fit on train fold only via `:103-115` + `:163-169`.
- PASS (4) quarterly cutoffs — `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:85-93`, `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:141-143`, `research/tournament/oc_bookmodel_impl/common_impl.py:51-57` (quarter_starts/quarter_end, cutoff = q0 - 7d).
- PASS (5) universe fixed Dec-2020 — `research/tournament/oc_bookmodel_impl/common_impl.py:60-64` (72 alts, majors excluded), `:67-95,181-222` (listed-only rows, asset=5; glob fallback `:71-72` still filtered by the same list).
- PASS (6) kpacks clean + in sync — `research/tournament/oc_bookmodel_impl/kpack_C1/`, `research/tournament/oc_bookmodel_impl/kpack_C2/` (byte-identical scripts, metadata private/no-GPU/no-net, no data/credentials; INPUTS minimal per plan).
- PASS (7) 2025-09-24 unused in training/selection — `research/tournament/oc_bookmodel_impl/common_impl.py:18-19` (DEV 2021-2024, FINAL 2025-09-24), `research/tournament/oc_bookmodel_impl/c1_pooled_tvflow.py:120,147-153`, `research/tournament/oc_bookmodel_impl/c2_rank_calibrated.py:184,211-217` (dev-only loops; smokes on DEV[0]).
