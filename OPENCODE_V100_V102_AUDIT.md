# v100 + v101 + v102 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v100_v102_audit/` and `tests/test_v100_v102_audit.py`.
Base: your audited v92 / v93_v94 / v98_v99 replications. Do NOT open v100/, v101/ or v102/ until part A is saved
(`replication.json`). All three reuse v92 features, target y, anchors, embargo (cutoff = anchor - 102*4h, training rows need
t + 43*4h < cutoff), long-only book `weights_from(...,"model")`, causal 20% vol target and costs unless stated.

A1 (v100, extra training rows only): from the perp 1h klines (BTC `data/raw/ma_ribbon_20260924/klines_1h.parquet`, others
`data/raw/majors_intraday_20260924/{SYM}_1h.parquet`) build phase-shifted 4h bars for phases 1,2,3 (a group = 4 consecutive
1h bars whose first open_time hour = phase mod 4; open first, high max, low min, close last, close_time last,
quote_volume sum; keep only complete groups of 4). Apply the unchanged v92 `features(b, d, f)` (same daily and funding
files) to each phase grid; asset id as v92; BTC context columns (btc_ret42, btc_ret180, btc_rib, btc_snr42) joined from
BTC's grid of the same phase by open_time. Training pool = v92 panel (phase 0, incl. spot prefix) + phases 1-3; test rows =
v92 panel only. HGB as v92 except min_samples_leaf = 1200 (primary) and 300 (sensitivity). Report IC and yearly normal net/DD.
A2 (v101, extra assets for training only): add ADA DOGE LINK LTC BCH DOT AVAX TRX ETC XLM UNI AAVE FIL (USD-M files in
`data/raw/xs_universe_20260924`, no spot prefix) with v92 features, asset ids 5..17 in that order, BTC context from the v92
BTC rows. Training pool = majors + extras; sample_weight 1 for majors and w for extras, w = 1 (primary) and 0.5
(sensitivity); test/trading majors only. Report IC and yearly normal net/DD.
A3 (v102, market-neutral stream): y_xs = y - mean of y over majors with a label at the same bar (NaN if fewer than 2
labelled). Extra features: xs_c = c - same-bar mean over majors for c in snr42 snr180 ret42 ret180 d50 d200 f7 vol_ratio volz.
HGB (v92 params) on v92 features + xs features, target y_xs. Weights: raw = (pred - bar mean pred)/(vol42*sqrt(2190)); W =
raw - bar mean(raw) over assets with a prediction, NaN->0, zero if fewer than 2 predictions, divided by sum|W|; daily
rebalance (keep every 6th row of the index as v92). Scale: v92 vol_target_scale with target 0.10 (cap 2). Simulate with
v92.simulate. Blend net = 0.75 * v99 net + 0.25 * neutral net per scenario (use your v99 normal replication with the
leader convention carry_exp[t]*carry[t]). Report IC (pooled spearman and mean per-bar), neutral and blend yearly normal
net/DD and the daily-return correlation of neutral vs v99 over 2021-09-24 onward.

Save `replication.json`, then compare with v100/v100_result.json, v101/v101_result.json, v102/v102_result.json (explain
IC diff > 0.01 or return diff > 1pp), audit the three scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
