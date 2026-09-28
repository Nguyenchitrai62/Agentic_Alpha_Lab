# v231 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v231_audit/` and `tests/test_v231_audit.py`. Use relative paths without
quoting. Do NOT open v231/v231_result.json or its logs until part A is saved (`replication.json`); read `v231/v231_quality_features.py`,
`v231/tv_indicators.py`, `v231/premium_features.py`, `scripts/fetch_binance_premium.py`.
A: (1) Independently re-implement at least SuperTrend(10,3), Williams VIX Fix z, anchored weekly VWAP, the 3/3 market-structure trend and
the POC distance on BTCUSDT 4h bars and compare with tv_indicators.tv_features (max abs diff); check that no TV value at row i changes when
bars after i are dropped (truncation test on the real BTC and XRP panels, >= 5 cut points). (2) Independently reconstruct the Binance
predicted funding from data/raw/binance_premium_20260928 (time-weighted premium average with weights 1..n + clamp(I - P, +-0.05%), I =
0.01%/8h, BNB 0) and check the reported per-symbol match with the settled rates, and that pf_* at bar t use only 1m samples with
open_time < t + 4h and settled rates published at or before t + 4h; confirm the BNB interest choice is derived from pre-2021-09-24 data
only. (3) Rebuild the three members (or verify the caches artifacts/research/engine_real/member_A_{tv,pf,all}_annual.parquet against a
rebuild of at least one anchor year each) and run the v218 D2 trade mode for D2 and V1..V3; report dev4, worst first-four monthly, gate
DD; robust selection; most recent year only for the selected row. Save `replication.json`. B: compare with the result JSON (return >
0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit windows
and fill timing. Do not edit leader files.
