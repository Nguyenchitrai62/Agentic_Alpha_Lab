# v118 + v119 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v118_v119_audit/` and `tests/test_v118_v119_audit.py`.
Base: your audited v115 (books, v110 engine) and v113_v114 (v114 panel) replications. Do NOT open v118/ or v119/ until
part A is saved (`replication.json`).
A1 (v118): v115 primary (target 0.15, ungoverned) in a sequential loop where per asset the held weight h changes to the
target w only if |w - h| > band (band 0.02 primary, 0.05 secondary, 0 reference); outside the live span weights are 0
(targets 0 are taken immediately); turnover = sum|new - held|; carry exposure 0.6*s unchanged with the v110 carry cost;
long funding 0.00005 on the held long gross. Report yearly net/DD/fills (bars with turnover > 1e-6) and full-path DD.
A2 (v119): on the v114 panel, per anchor: cutoff = anchor - 102*4h; training rows t < cutoff with y and t + 43*4h <
cutoff; validation = training rows with t >= cutoff - 730 days; inner-train = training rows with t + 43*4h < val_start -
102*4h. Grid max_depth (3,4,6) x min_samples_leaf (300,1000), lr 0.03, max_iter 400, l2 1.0, seed 0; score = Spearman
on validation; refit best on all training rows; predict the test year. Report chosen configs, val scores, test IC, v92
LO book (v92 vol target) and v96 blend with the v114-panel v94 LS book.
Save `replication.json`, compare with v118/v118_result.json and v119/v119_result.json (explain return diff > 1pp or DD
diff > 0.5pp), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
