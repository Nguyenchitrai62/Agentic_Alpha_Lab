# v113 + v114 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/` and `tests/test_v113_v114_audit.py`.
Base: your audited v92 / v93_v94 (v94 LS) / v95_v96 (v96 blend) replications. Do NOT open v113/ or v114/ until part A is
saved (`replication.json`).

A1 (v113): prepend to BTC and ETH (only rows with open_time before the first existing v92 4h / 1d bar of that asset) bars
aggregated from Coinbase 1h candles: concat(data/raw/coinbase_20260925/{P}-USD_1h_pre2017.parquet, {P}-USD_1h.parquet),
dedup open_time. UTC resample label/closed left: open first, high max, low min, close last, volume sum, quote_volume =
sum(volume*close); keep 4h bars with >= 3 hourly candles and 1d bars with >= 20; close_time = open_time + rule - 1ms.
Other columns absent (NaN). Build the v92 panel on these extended assets (features, y, BTC context) and retrain: v92 LO
book (v92 vol target), v94 LS (v94 ensemble on the extended panel with its own vol target), and 0.5/0.5 v96 blend
(scale 1). Report per-anchor IC (v92 vs y, v94 vs y42), train rows and yearly normal/fee/execution net/DD for the three.
A2 (v114): as A1 but the BTC hourly series is Bitstamp data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet rows with
open_time >= 2013-01-01 and before the first Coinbase hour, then the Coinbase hours; ETH as A1.

Save `replication.json`, compare with v113/v113_result.json and v114/v114_result.json (explain IC diff > 0.01 or
return diff > 1pp), audit v113_longer_history.py and v114_bitstamp_history.py for look-ahead and junction artifacts
(price gaps between sources), write COMPARISON.md. Do not edit leader files.
