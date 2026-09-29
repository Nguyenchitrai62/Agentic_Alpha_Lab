# v260 + v261 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v260_v261_audit/` and `tests/test_v260_v261_audit.py`. Use relative paths
without quoting. Do NOT open v260/v260_result.json, v261/v261_result.json or their logs until part A is saved (`replication.json`); read
`v260/v260_ppo_risk_boot.py` (built on v259 with the `risk_mult` engine hook) and `v261/v261_direct_rl_member.py`.
A1 (v260): confirm the reference (risk_mult None) gives dev4 5.777; check that the bootstrap episodes draw 30-day blocks ONLY from bars
from 2021-09-24 whose holding bar ends before anchor - 7 days, that the strategy PnL and market state are resampled jointly (same
indices), that the engine-side state uses equity up to bar i-2; re-train the five seeds (report per seed dev4 / DD / most recent year and
whether they match within 0.3 pp / 1 pp), the median seed by dev4 and the pre-registered decision rule (median seed must beat the
reference under the robust criterion).
A2 (v261): check the feature timing (TradingView and flow rows at the decision-bar close, returns from next-bar opens = decision close,
trailing windows only), the reward y = open t+2 / open t+1 - 1 and that training rows end before anchor - 7 days, that standardisation and
the scale k use training rows only, the five-seed averaging; re-run and compare dev4 / DD / member IC; robust selection; most recent year
only for the selected row.
Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature
timing, label windows, fit windows and fill timing. Also note: v260 was run after its pre-registration was committed (git 06077ba) but
before the registry rotation (all tracks were held by audits) - confirm the committed script equals the run script. Do not edit leader files.
