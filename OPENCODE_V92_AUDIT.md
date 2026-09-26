# v92 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Reproduce BEFORE opening `research/parallel/rounds/parallel-20260906-r2/v92/*`. Write only under
`research/parallel/rounds/parallel-20260906-r2/v92_audit/` and `tests/test_v92_audit.py`.
Start from your own v89 audit replication (`research/parallel/rounds/parallel-20260906-r2/v89_audit/replicate.py`;
use the LEADER conventions for NaN: ribbon=0 when SMA unavailable; funding rolling min_periods 3 and 9).
Changes for v92: (1) prefix each of BTC/ETH/BNB/XRP with Binance SPOT 4h/1d bars from
`data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet` for open_time before the first USD-M bar
(funding NaN there); (2) for each anchor 2021-09-24..2025-09-24 train as in v89 and predict the next 365 days;
concatenate the five forward prediction sets into one continuous out-of-sample series.
(3) Weights per asset at 4h close t: s = min(max(pred,0)/0.5, 1), zeroed when the asset's daily ribbon is -1;
raw = s / (std42 * sqrt(6*365)); normalise raw to sum 1 across assets (when any > 0) then multiply by
min(1, count(raw>0)/5); keep only every 6th bar (daily) and forward-fill. (4) Vol target: book return realised at
bar t = sum_i W_{i,t-2} * (open_{i,t}/open_{i,t-1} - 1); vol = rolling std over 360 bars (min 120) * sqrt(2190);
scale_t = min(0.20/vol_t, 2), NaN -> 1. (5) Execution: W_t*scale_t earns open_{t+2}/open_{t+1} - 1; fee 0.0002
per unit turnover; long funding 0.00005 per 4h bar on long gross.
A. Save `replication.json`: per-anchor IC and hidden-year (2025-09-24..) net %, max DD, and 5-year geometric
   monthly return (normal costs). B. Then compare with `v92_result.json` (explain any IC diff > 0.01 or return diff
   > 1pp) and audit v92_pooled_hgb_vt.py for look-ahead, especially the spot prefix join, the continuous OOS
   series and the vol-target timing. Write COMPARISON.md. Do not edit leader files.
