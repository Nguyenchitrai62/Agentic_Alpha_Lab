# v258 + v259 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v258_v259_audit/` and `tests/test_v258_v259_audit.py`. Use relative paths
without quoting. Do NOT open v258/v258_result.json, v259/v259_result.json or their logs until part A is saved (`replication.json`); read
`v258/v258_ppo_disciplined.py`, `v259/v259_ppo_risk_manager.py` and in `engine_user/engine_user.py` the hook `risk_mult(i, eq_hist)`
(multiplier on the governor of bar i; eq_hist = eq[:i-1], i.e. equity up to bar i-2).
v259 is the FIRST configuration whose selected row passes the whole gate (5y 5.114, most recent year 5.309, no losing year, DD 17.45),
so audit it with extra care.
A1 (v259): (1) confirm risk_mult None reproduces v247 B18 (dev4 5.777, DD 19.65). (2) LEAKAGE: check that the training proxy R (per-bar
book + sleeve PnL from the reference run's attribution) is used ONLY for bars whose holding bar ends before anchor - 7 days for the policy
of that anchor; that every state input at decision i uses equity only up to bar i-2 and market data only up to the decision-bar close
(truncation probes: change data after the decision and confirm the multiplier at i is unchanged); that the vol-history median uses only
earlier decisions; that the 2021 year runs with multiplier 1. (3) Re-train K1 / K2 with the same seeds (PPO may differ across hardware:
report whether your dev4 / DD are within 0.3 pp / 1 pp and whether K2 is again the only row with DD <= 20); report mean multipliers per
year. (4) The robust selection and the most recent year only for the selected row.
A2 (v258): check the simulator fidelity claim (monthly corr of rule-only book PnL vs engine attribution on the dev years), the discipline
mask in simulator and engine, the fit windows; re-train with the same seeds and compare qualitatively.
Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature
timing, label (reward) windows, fit windows and fill timing. Do not edit leader files.
ERRATUM (leader, after dispatch): the v259 docstring says "random 180-day windows"; the code uses EP_DEC = 30 decisions x 6 bars = 30-day
episodes. Audit the code as run and note the discrepancy.
