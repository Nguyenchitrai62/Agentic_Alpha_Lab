# v243 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v243_audit/` and `tests/test_v243_audit.py`. Use relative paths without
quoting. Do NOT open v243/v243_result.json or its logs until part A is saved (`replication.json`); read `v243/v243_sleeve_flow_bandit.py`
and `v235/v235_sleeve_bandit_tv.py`.
A: on the O1 books reproduce the unfiltered run (dev4 5.690), the filled-bid dataset, the per-year HGB models (bids exited before
Y - 7 days; training sizes, q25/q75) with the state = v235 state + the six order-level flow features at the decision row, and the filters
S1..S3; report dev4, worst first-four monthly, gate DD, dev sleeve win rate / average; robust selection; most recent year only for the
selected row. Check the state causality and the fit windows. Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month,
DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing.
Do not edit leader files.
