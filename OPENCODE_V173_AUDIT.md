# v173 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v173_audit/` and `tests/test_v173_audit.py`.
Do NOT open v173/ until part A is saved (`replication.json`). Base: your v172 audit (crash-aware sleeve costs,
60-minute execution books on engine_real). Implement independently.
A: decision grid t (4h) from 2020-02-01; holding bar T = t + 4h; 1m OHLCV + taker_buy_volume (BTC: btc_intraday klines_1m,
others: majors_intraday <SYM>_1m; forward-fill prices inside a bar, missing volume = 0). sigma(t) = std of 4h
open-to-open pct changes, 360 bars (min 120). Candidate points: for c in (2, 3, 4) the first minute m in 16..238 with
close(m)/open(T) - 1 <= -c sigma. y = open(T+4h)*(1 - s_out) / (open(m+1)*(1 + s_in)) - 1 - 0.001 - funding at T+4h,
s = max(0.0002, 0.25*(high-low)/open) of minute m+1 (in) and of minute 0 of T+4h (out).
Features: depth=(close(m)/open(T)-1)/sigma; c; m/240; r5=(close(m)/close(m-5)-1)/sigma; r15 likewise with m-15;
vspike = volume(m-4..m) / (5 * mean volume(0..m-6)); taker15 = taker_buy(m-14..m)/volume(m-14..m); rng =
(high(m)-low(m))/close(m)/sigma; breadth = number of OTHER assets with depth <= -2 at minute m; btc_depth; trend =
open(T)/mean(last 42 4h opens incl. open(T)) - 1; r1d = (open(T)/open(T-24h) - 1)/sigma; funding = last non-zero
settled rate at or before t; asset code (column order BNB, BTC, ETH, SOL, XRP).
Per anchor: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
l2_regularization=1.0, random_state=0) fit on points with T+4h < anchor - 1 day and T >= 2020-03-02; test points with
t in [anchor, anchor+365d); take per (t, asset) the earliest point with pred > 0; sleeve per bar = 0.25 * sum of taken y.
Report IC (Spearman pred vs y on test points), taken count, sleeve net/DD per anchor, and the combined engine_real row
(books + g * sleeve). Save `replication.json`.
B: compare with `v173/v173_result.json`, check look-ahead (every feature at or before minute m; training cutoff), write
COMPARISON.md. Do not edit leader files.
