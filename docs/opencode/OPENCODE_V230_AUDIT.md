# v230 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v230_audit/` and `tests/test_v230_audit.py`. Use relative paths without
quoting. Do NOT open v230/v230_result.json or its logs until part A is saved (`replication.json`); read `v230/v230_korea_premium_member.py`.
A: rebuild the Korean features independently (Upbit KRW-BTC/ETH/XRP 1h -> UTC 4h bars whose close is the hour ending at the bar close;
Binance spot 4h close/quote volume; USDKRW daily close from data/raw/fx_krw_20260928 usable only from its timestamp + 2 days; premium
1e4*log(upbit/(binance*fx)); the six features as in the docstring). Check their timing (no value may use data after the bar close) and the
coverage. Rebuild member K with the v144 builder + these features (or, if the rebuild is too slow, verify the cached
artifacts/research/engine_real/member_K_annual.parquet against a rebuild of at least one anchor year). Run the v218 D2 trade mode on
D2 and K1/K2/K3/K_alone mixes; report dev4, worst first-four monthly, gate DD; robust selection among K1..K3; most recent year only for
the selected row. Save `replication.json`. B: compare with the result JSON (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a
"## Verdict" section PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing. Do not edit leader files.
