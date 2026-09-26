# v136 + v137 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v136_v137_audit/` and `tests/test_v136_v137_audit.py`.
Base: your audited v132_v133 (v133 configuration) and v135 (1m bar stats, limit-offset execution) replications. Do NOT
open v136/ or v137/ until part A is saved (`replication.json`).
A1 (v136): for every model of v133 (v92 on target y with H=42 and v92 embargo; each v94 horizon 18/42/84 with the v94
embargo max(H)+60; each v103 horizon 6/18 with embargo 78) and anchor: training rows as the audited code; val = training
rows with t >= cutoff - 730 days (if > 20000 rows, pandas .sample(20000, random_state=0)); inner-train = training rows with
t + (h+1)*4h < val_start - embargo*4h. HGB (v92 params) on inner-train, sklearn permutation_importance on val with scoring
= make_scorer(Spearman of prediction vs target), n_repeats=3, random_state=0; keep features with mean importance > 0
(top 5 by importance if fewer than 5); refit on all training rows with kept features. v94/v103 predictions = mean over
horizons. Then v133 pipeline (pvol swap, tranching, portfolio 0.15). Report kept-feature counts and three scenarios.
A2 (v137): v133 books; portfolio target in (0.15, 0.17, 0.19, 0.21); execution with the v135 rule at d = 10 bps; report
monthly, yearly, full-path DD per target (0.15 must equal your v135 10 bps row).
Save `replication.json`, compare with v136/v136_result.json and v137/v137_result.json (explain return diff > 1pp, DD diff >
0.5pp), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
