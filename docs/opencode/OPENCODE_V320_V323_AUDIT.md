# v320 + v321 + v322 + v323 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Scripts / docstrings in research/parallel/rounds/parallel-20260906-r2/: v320/v320_member_weight_evolution.py (MANUAL member-weight GA; eval cache
v320/eval_cache.jsonl), v321/v321_bot_walkforward_seed_choice.py (BOT seed choice R2 + its most-recent-year score), v322/v322_manual_theta_target.py
(MANUAL theta x target grid), v323/v323_bot_r2_book_management.py (BOT R2 + pullback / loss_act variants).
Write only under `research/parallel/rounds/parallel-20260906-r2/v320_v323_audit/` and `tests/test_v320_v323_audit.py`; relative paths without
quoting; do NOT open the four result JSONs, logs or evolution.log before replication.json is saved.
Part A: v320 - re-simulate the 15 seeds and 8 random cached weight vectors (seed 7320) with your own member mix (nine member groups as listed in
init_worker; annual + quarterly averages; normalised integer weights) under the fixed rules (pullback entry 0.75 sigma_4h, n_valid 3, target 0.25,
cap 2, G2 grid trader, sleeve off); check the fold protocol (fitness on years [:k], flat choice, best seed baseline) in the code. v321 - re-simulate
the 12 v306 seeds, the dev4 choice by the v306 BOT fitness and the chosen seed's most-recent-year metrics. v322 - the nine grid rows, fold choices
and the final row. v323 - the four rows (R2 with / without the pullback entry and loss_act tighten), fold choices and the final row. Check
explicitly: no most-recent-year number enters any choice; fills / timing as engine_user; members are cached walk-forward books.
Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict"
PASS/FAIL per version. Do not edit leader files.
