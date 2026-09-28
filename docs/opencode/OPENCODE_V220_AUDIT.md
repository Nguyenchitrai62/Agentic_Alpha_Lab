# v220 blind audit - dip-bid bandit filter (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v220_audit/` and `tests/test_v220_audit.py`. Use relative paths
without quoting. Do NOT open v220/v220_result.json or v220 logs until part A is saved (`replication.json`); read the pre-registration
`v220/v220_sleeve_bandit.py`.
A (leakage first): check that each bid's features use only information of the decision row i (o1 up to row i, books/members of row
i, hour of the holding bar), that the model for year Y is fitted on bids whose exit is before Y - 7 days, that the filter is a function
of (i, coin, rung) only (it is queried only for touched bids, which must not change the decision), and that year 0 places every bid.
Reproduce v218 D2 (dev4 5.261) and report dev4, worst first-four monthly, gate DD, sleeve dev bids/win rate for v218_D2, F1, F2, F3;
robust selection over F1..F3; most recent year only for the selected row. Save `replication.json`.
B: compare with `v220/v220_result.json` (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL and any leakage finding.
Do not report the most recent year of non-selected rows. Do not edit leader files.
