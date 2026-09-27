# v97 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v97_audit/` and `tests/test_v97_audit.py`.
Base: your audited `v92_audit/replicate_5asset_leader_run.py`. Do NOT open v97/ until A is saved.
Spec: for each anchor train on the v92 training rows (same features, target, cutoff/embargo) an ensemble of 16 models:
HistGradientBoostingRegressor(max_depth in {3,4,6}, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
l2_regularization=1.0, max_features=0.7, random_state in {0,1,2,3,4}) and ExtraTreesRegressor(n_estimators=300,
min_samples_leaf=300, max_features=0.5, random_state=0, n_jobs=-1) fitted on features with NaN replaced by the
TRAINING-ROW medians (same medians applied to prediction rows). Prediction = mean of all 16. Report per-anchor IC,
then the v92 long-only book with the causal 20% vol target (yearly normal net/DD).
Save `replication.json`; then compare with v97/v97_result.json (IC diff > 0.01 or return diff > 1pp: explain), audit
v97_tree_ensemble.py for look-ahead (especially the imputation medians), write COMPARISON.md. Do not edit leader files.
