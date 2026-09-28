# v222 blind audit - sub-account bot ensembles (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v222_audit/` and `tests/test_v222_audit.py`. Use relative paths
without quoting. Do NOT open v222/v222_result.json or v222 logs until part A is saved (`replication.json`); read the pre-registration
`v222/v222_subaccount_ensemble.py`.
A: simulate each bot alone on its sub-account (engine_user trade mode, D2 sleeve settings 0.15 / x1.75, minimum notional at share x 10k
USDT, own governor): D2 (v216 G2 grid policy), Y3 (v221 hysteresis EMA, close < 2.5%), S3 (v212 rules). Account equity = sum of
share-weighted sub-account equities without rebalancing; the 1m low of the sum = sum of the lows (conservative). Report dev4, worst
first-four monthly, gate DD for v218_D2 (100% D2), K1 (50/50 D2+Y3), K2 (50/50 D2+S3), K3 (thirds); robust selection over K1..K3;
most recent year only for the selected row. Save `replication.json`.
B: compare with `v222/v222_result.json` (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL. Do not report the most
recent year of non-selected rows. Do not edit leader files.
