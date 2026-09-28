# v214 blind audit - offline RL trader agent (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v214_audit/` and `tests/test_v214_audit.py`. Use relative paths
without quoting. Do NOT open v214/v214_result.json or v214/run.log until part A is saved (`replication.json`); you may read
`v214/v214_trader_fqi.py` (the pre-registration) and `rl/trader_rl.py`.
A (leakage first): write an independent check that for every walk-forward year Y the training transitions end before Y - 7 days
(recompute TEND from the behaviour runs), that every state feature at decision i uses only 4h opens up to the decision close
(o1 up to row i), the decision-row books/members and the position state; that rewards are the coin's PnL of holding bars
i..next decision - 1; that the Monte Carlo return stops when the next decision is flat. Verify that the policy hook with the S3
rule reproduces v212 S3 (dev4 4.826). Then re-run the v214 driver end to end (it is deterministic: seeds 0-19) or an
equivalent independent driver, and report dev4, worst first-four monthly, gate DD, fills, adds, reduces, limit exits for
ref_v205, rule_S3, v213_E1, Q1_fqi, Q2_mc_margin, Q3_mc_averse. Robust selection over Q1..Q3; most recent year only for the
selected row. Save `replication.json`.
B: compare with `v214/v214_result.json` (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL; list any leakage
finding explicitly. Do not report the most recent year of non-selected rows. Do not edit leader files.
