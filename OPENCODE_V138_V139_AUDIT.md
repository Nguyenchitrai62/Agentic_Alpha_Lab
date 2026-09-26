# v138 + v139 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v138_v139_audit/` and `tests/test_v138_v139_audit.py`.
Base: your audited v132_v133 replication (v133 configuration). Do NOT open v138/ or v139/ until part A is saved.
A1 (v138): for every v133 model (v92 y H=42; v94 18/42/84; v103 6/18; audited cutoffs/embargoes/row filters) fit HGB (v92
params) and Ridge(alpha=10) on standardized features: training medians fill NaN, then (x - train mean)/train std (std 0
-> 1), clip +-5, remaining NaN -> 0. sd_h = std of HGB in-sample predictions on the raw training features, sd_r = std of
ridge in-sample predictions; blend = 0.5*hgb + 0.5*sd_h*ridge/sd_r (sd_r 0 -> 1). v94/v103 = mean over horizons. Then v133
pipeline. Report v92 IC per anchor for hgb/ridge/blend and three scenarios with full-path DD.
A2 (v139): positioning features from data/raw/um_metrics_20260926/{SYM}_metrics.parquet: for each v103-panel 4h row take
the last metrics row with create_time <= t + 4h - 5min (asof backward, tolerance 4h); oi = log(sum_open_interest_value > 0),
top = log(sum_toptrader_long_short_ratio), crowd = log(count_long_short_ratio), taker = log(sum_taker_long_short_vol_ratio);
oi_chg6 = diff(oi,6), oi_chg42 = diff(oi,42), z(s) = (s - rolling180 mean(min 90))/rolling180 std(min 90); oi_z = z(oi),
top_ls = top, top_ls_chg6 = diff(top,6), top_ls_z = z(top), crowd_ls_z = z(crowd), taker_ls6 = rolling6 mean(min 3) of taker,
per asset in time order. Add to the v103 features only; v103 vol forecast uses the features without these; v133 pipeline.
Report coverage, v103 IC and three scenarios.
Save `replication.json`, compare with v138/v139 result JSONs (explain IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp),
audit both scripts for look-ahead (metrics timing!), write COMPARISON.md. Do not edit leader files.
