# v256 + v257 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v256_v257_audit/` and `tests/test_v256_v257_audit.py`. Use relative paths
without quoting. Do NOT open v256/v256_result.json, v257/v257_result.json or their logs until part A is saved (`replication.json`); read
`v256/v256_entry_agent.py`, `v257/v257_ppo_trader.py` and in `engine_user/engine_user.py` the flat-policy action {"open": k} (opening limit
k sigma_4h better than the bar open; adds / reduces / exits keep k_off 0.25).
A1 (v256): confirm {"open": 0.25} through the hook reproduces v247 B18 (dev4 5.777, DD 19.65). Rebuild the four fixed-k counterfactual
runs (k 0.10 / 0.25 / 0.50 / 0.75), the order outcomes (opening orders only - in-position orders carry "scale" and are ignored; net PnL
in equity-weight units with maker / taker fees, 0 if expired / cancelled unfilled, end time = position close or order end), the key
intersection, the state at the decision row (check causality: next-bar opens = decision-bar close, trailing windows only), the per-anchor
cross-fitted HGB fits on orders whose END time is before anchor - 7 days, and the E1 / E2 policies. Report matched orders, dev mean
outcome per action, action counts, dev4, worst first-four monthly, gate DD; robust selection; most recent year only for the selected row.
A2 (v257): check the simulator against the engine rules (limit fill on trade-through from minute 5, stop first, break-even, fees, adverse
funding, rule close on signal loss), that each policy for anchor Y trains ONLY on holding bars from 2021-09-24 whose bar ends before Y - 7
days, that the state uses only information at the decision-bar close, and that the engine evaluation maps actions as documented. PPO is
stochastic across hardware: re-train with the same seeds and report whether your dev4 is within 0.3 pp/month of the leader's and whether
the qualitative result (better / worse than the reference) matches; report action shares.
Save `replication.json`. B: compare with both result JSONs (v256 exact: return > 0.01pp/month, DD > 0.05pp; v257 as above). COMPARISON.md
with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
