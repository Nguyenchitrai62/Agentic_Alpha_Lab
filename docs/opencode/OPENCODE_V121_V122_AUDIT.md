# v121 + v122 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v121_v122_audit/` and `tests/test_v121_v122_audit.py`.
Base: your audited v115 replication (books, v110 engine, target 0.15 ungoverned). Do NOT open v121/ or v122/ until
part A is saved (`replication.json`).
A1 (v121): v103 model replaced by a bag: for each horizon (y6, y18) and member m = 0..9: training calendar days (UTC
floor of t, sorted unique) sampled without replacement, size int(0.7 * n_days), numpy default_rng(m).choice; all rows of
chosen days; HistGradientBoostingRegressor(max_depth 4, lr 0.03, max_iter 400, min_samples_leaf 300, l2 1.0,
max_features 0.7, random_state m); pred = mean of the 20 member predictions. Report IC, the bagged LS book (own vol
target) and the v115 portfolio with it (0.25/0.25/0.5).
A2 (v122): on the v114 panel y168 = clip(log(open[t+169]/open[t+1])/(vol42*sqrt(168)), +-4) per asset; HGB (v92 params,
seed 0) on the v94 feature list, cutoff = anchor - 228*4h, rows need t + 169*4h < cutoff; LS book = v94 weights_ls with
own v94 vol scale (v114 panel). Portfolio books = 0.2 v92 LO + 0.2 v94 LS + 0.4 v103 LS + 0.2 y168 LS (each with its own
scale, union index from the first v103 t), v110 engine target 0.15 ungoverned. Report IC, book and portfolio results.
Save `replication.json`, compare with v121/v121_result.json and v122/v122_result.json (explain IC diff > 0.01, return diff
> 1pp or DD diff > 0.5pp), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
