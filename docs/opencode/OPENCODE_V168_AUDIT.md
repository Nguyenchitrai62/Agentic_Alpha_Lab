# v168 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v168_audit/` and `tests/test_v168_audit.py`.
Do NOT open v168/ until part A is saved (`replication.json`). Base: your v154 replication (members A = v144 books,
B = + v150 options features, D = + v111 Coinbase premium features; import the leader modules, do not copy logic).
A: in all three members replace ONLY the v103 model (`v103.train_predict`), per anchor, keeping the audited v103
cutoff (anchor - 4h * v103.EMBARGO), per-horizon row filter (t + 4h*(h+1) < cutoff, y{h} not NaN) and h in v103.HS:
for each h and q in (0.25, 0.5, 0.75) fit HistGradientBoostingRegressor(loss="quantile", quantile=q, max_depth=4,
learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0) on the training rows.
Test rows = [anchor, anchor + 365 d). m = mean over h of the q=0.5 test predictions; s = mean over h of
max(q75 - q25, 1e-3). On training rows common to both horizons: c_tr = |mean_h median| / mean_h spread (same floor),
c_ref = median(c_tr). k = clip((|m|/s)/c_ref, 0.5, 1.5); pred = m * k. v92/v94 books unchanged. Books = (A+B+D)/3,
v144 `simulate` rows (0.15 ungoverned, 0.20/0.25 governed). ALSO report (diagnostic, not in v168) the same with k = 1
(median only) so the effect of the quantile median and of the multiplier are separated, plus Spearman IC per anchor of
m vs y6 and of the audited v103 regressor prediction vs y6. Save `replication.json`.
B: compare with `v168/v168_result.json` (return > 1pp, DD > 0.5pp must be explained), audit
`v168/v168_quantile_confidence.py` for look-ahead (c_ref from training rows only), write COMPARISON.md with a verdict.
Do not edit leader files.
