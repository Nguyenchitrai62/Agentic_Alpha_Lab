# v111 + v112 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v111_v112_audit/` and `tests/test_v111_v112_audit.py`.
Base: your audited v103_v105 replication (v103 panel/features/targets/embargo/HGB, v94 weights_ls, vol targets, v92
book). Do NOT open v111/ or v112/ until part A is saved (`replication.json`).

A1 (v111): for P in BTC, ETH: Binance spot 4h = concat(data/raw/spot_majors_20260925/{P}USDT_spot_4h_2017.parquet,
{P}USDT_spot_4h.parquet) on open_time/close, dedup, sorted. Coinbase = data/raw/coinbase_20260925/{P}-USD_1h.parquet.
For each Binance 4h bar T: Coinbase close of the 1h candle with open_time <= T+3h (asof backward, tolerance 2h, else NaN);
cbp = 1e4*log(cb_close / binance_close). p6 = rolling-6 mean (min 4), p42 = rolling-42 mean (min 30), m540/s540 =
rolling-540 mean/std of cbp (min 270). Features joined on t to every asset: cb_btc_dev = p6-m540 (BTC), cb_btc_z =
(p6-m540)/s540, cb_btc_chg = p6-p42, cb_eth_z, cb_eth_chg (ETH). Primary: v103 + these 5 features (LS book). Secondary:
v92 + these 5 (v92 7d model, long-only book, v92 vol target). Report ICs and yearly normal/fee/execution net/DD.
A2 (v112): v103 setup but per horizon HistGradientBoostingClassifier (max_depth 4, lr 0.03, max_iter 400,
min_samples_leaf 300, l2 1.0, random_state 0) on target (y_h > 0); pred = 2*mean_h P(up) - 1; v94 weights_ls LS with own
20% vol target; secondary 0.5*v96 books + 0.5*(LS * scale), scale 1. Report ICs and yearly net/DD.

Save `replication.json`, compare with v111/v111_result.json and v112/v112_result.json (explain IC diff > 0.01 or
return diff > 1pp), audit both scripts for look-ahead (Coinbase time alignment!), write COMPARISON.md. Do not edit
leader files.
