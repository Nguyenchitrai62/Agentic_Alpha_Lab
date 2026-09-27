# v107 + v108 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v107_v108_audit/` and `tests/test_v107_v108_audit.py`.
Base: your audited v103_v105 replication (v103 panel, flow features, y6/y18 targets, HGB, v94 weights_ls, vol target).
Do NOT open v107/ or v108/ until part A is saved (`replication.json`).

A1 (v107): 1h series per major = Binance SPOT 1h prefix `data/raw/spot_majors_20260925/{SYM}_spot_1h_2017.parquet` (rows
with open_time before the first USD-M 1h bar) + USD-M 1h (BTC `data/raw/ma_ribbon_20260924/klines_1h.parquet`, others
`data/raw/majors_intraday_20260924/{SYM}_1h.parquet`), dedup on open_time, sorted. r1 = diff(log close); sd168 = rolling
168 std of r1 (min_periods 84); tbr = clip(taker_buy_quote_volume / max(quote_volume,1), 0, 1).
 ih_last = r1/sd168; ih_jump = rolling-4 max |r1| / sd168; ih_rv = rolling-24 std r1 / sd168; ih_ac = rolling-72
 corr(r1, r1.shift(1)); ih_tbr = tbr - rolling-24 mean tbr; ih_up = rolling-24 mean of (r1>0, NaN where r1 NaN) - 0.5.
 The 4h bar opening at T takes the values of the 1h bar opening at T+3h (left join on t, sym). Features = v103 features +
 these six. Everything else as v103. Report per-anchor IC (y6, y18), LS yearly normal/fee/execution net/DD and the
 0.5*v96 books + 0.5*(v107 LS * own vol scale) blend (scale 1).
A2 (v108): v103 predictions unchanged; LS book = v94 weights_ls rule but keeping every k-th row of the weight index
 (k = 1 primary, 3 secondary; v103 is k = 6), ffill between; own 20% vol target; v92 costs. Report yearly net/DD for
 k = 1, 3, 6 in the three scenarios.

Save `replication.json`, then compare with v107/v107_result.json and v108/v108_result.json (note: v108 JSON carries the
provisional label "v106"), explain IC diff > 0.01 or return diff > 1pp, audit both scripts for look-ahead (especially
the 1h -> 4h mapping), write COMPARISON.md. Do not edit leader files.
