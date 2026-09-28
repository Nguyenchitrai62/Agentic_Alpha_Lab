# v245 + v246 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v245_v246_audit/` and `tests/test_v245_v246_audit.py`. Use relative paths
without quoting. Do NOT open v245/v245_result.json, v246/v246_result.json or their logs until part A is saved (`replication.json`); read
`v245/v245_small_account.py` and `v246/v246_flow_ensemble.py`.
A: (v245) with the O1 books (cached members) and the v218 D2 settings, zero the books and the dip bids (sleeve_filter 0) of the coins
outside each universe (S1 SOL/BNB/XRP, S2 BNB/XRP, S3 = S1 with the traded books x1.5); confirm the O1 reference (5.690). Also check the
Bybit lot rules quoted in the docstring against https://api.bybit.com/v5/market/instruments-info?category=linear&symbol=<SYM>.
(v246) build the ensemble books from the cached members (E1 A = (A_whale + A_O1)/2 etc., E2 with A_tv) and confirm the W2 / O1 references.
Report dev4, worst first-four monthly, gate DD per row; robust selection per version; most recent year only for each selected row. Save
`replication.json`. B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL,
explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
