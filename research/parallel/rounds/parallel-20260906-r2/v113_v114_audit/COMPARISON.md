# v113 + v114 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v113/` / `v114/` (see `replication.json`,
`predictions_v113_v92.csv`, `predictions_v113_v94.csv`, `predictions_v114_v92.csv`,
`predictions_v114_v94.csv`, `equity_*_normal.csv` in this folder, plus
`tests/test_v113_v114_audit.py` passing). Audit scope:
`v113/v113_longer_history.py`, `v113/v113_result.json`, `v113/result_manifest.json`,
`v114/v114_bitstamp_history.py`, `v114/v114_result.json`, `v114/result_manifest.json`.
No leader files were edited. All writes are under `v113_v114_audit/` +
`tests/test_v113_v114_audit.py`.

## A. Number comparison (blind audit vs leader)

### Train rows + ICs — exact match, both extensions

v113 (blind vs leader `ic`):

| anchor | train_rows | IC v92 | IC v94 (vs y42) |
|---|---|---|---|
| 2021-09-24 | 40330 / 40330 | 0.101 / 0.101 | 0.102 / 0.102 |
| 2022-09-24 | 51280 / 51280 | -0.0048 / -0.0048 | -0.0157 / -0.0157 |
| 2023-09-24 | 62230 / 62230 | 0.1053 / 0.1053 | 0.0942 / 0.0942 |
| 2024-09-24 | 73210 / 73210 | 0.1079 / 0.1079 | 0.1095 / 0.1095 |
| 2025-09-24 | 84160 / 84160 | 0.1918 / 0.1918 | 0.2022 / 0.2022 |

v114 (blind vs leader `ic`):

| anchor | train_rows | IC v92 | IC v94 (vs y42) |
|---|---|---|---|
| 2021-09-24 | 45915 / 45915 | 0.0863 / 0.0863 | 0.1355 / 0.1355 |
| 2022-09-24 | 56865 / 56865 | -0.032 / -0.032 | -0.0333 / -0.0333 |
| 2023-09-24 | 67815 / 67815 | 0.1152 / 0.1152 | 0.089 / 0.089 |
| 2024-09-24 | 78795 / 78795 | 0.1064 / 0.1064 | 0.1065 / 0.1065 |
| 2025-09-24 | 89745 / 89745 | 0.163 / 0.163 | 0.1755 / 0.1755 |

Per-horizon v94 train rows also match (v113 e.g. 2021: 40240/40120/39910;
v114 e.g. 2021: 45825/45705/45495 — verified in `replication.json`).
`first_rows` match: v113 BTC `2015-07-20 20:00`, ETH `2016-05-18 00:00`;
v114 BTC `2013-01-01 00:00`, ETH as v113. No threshold exceeded
(IC diff > 0.01 or return diff > 1pp): nothing to explain.

### Yearly books — bit-exact in all 3 scenarios (normal / fee_stress / execution_stress)

v113 normal, blind vs leader (net % / DD % / fills — all diffs 0.00pp):

| book | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| v92 LO net | 11.22 | 60.75 | 65.49 | 56.75 | 24.67 |
| v92 LO DD | 19.58 | 9.43 | 15.89 | 13.43 | 23.46 |
| v92 LO fills | 1350 | 1402 | 1646 | 1845 | 1193 |
| v94 LS net | 2.47 | 5.57 | 58.82 | 34.84 | 58.33 |
| v94 LS DD | 23.00 | 11.40 | 10.01 | 14.15 | 11.45 |
| v94 LS fills | 1706 | 2159 | 2157 | 2130 | 2069 |
| v96 blend net | 7.13 | 30.89 | 63.08 | 46.01 | 41.41 |
| v96 blend DD | 20.73 | 8.71 | 6.94 | 13.69 | 11.90 |
| v96 blend fills | 1698 | 2159 | 2160 | 2161 | 2071 |

v114 normal, blind vs leader (all diffs 0.00pp):

| book | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| v92 LO net | -3.53 | 54.92 | 77.55 | 59.33 | 32.35 |
| v92 LO DD | 23.64 | 11.50 | 11.24 | 12.67 | 19.33 |
| v92 LO fills | 1333 | 1348 | 1571 | 1872 | 1135 |
| v94 LS net | 13.50 | 3.52 | 61.59 | 42.74 | 61.86 |
| v94 LS DD | 22.45 | 12.00 | 11.92 | 13.04 | 10.20 |
| v94 LS fills | 1599 | 2147 | 2158 | 2135 | 2045 |
| v96 blend net | 4.92 | 27.33 | 70.14 | 51.48 | 47.38 |
| v96 blend DD | 22.76 | 10.34 | 8.41 | 12.77 | 10.86 |
| v96 blend fills | 1603 | 2155 | 2160 | 2161 | 2051 |

Fee-stress and execution-stress yearly nets/DDs/fills are likewise exactly equal
(max abs net diff 0.00pp across all 90 book/scenario/year cells; verified
programmatically against `v113_result.json` / `v114_result.json`, fee 0.0006,
execution 0.0006 + slip 0.0005). Monthly-geometric figures reproduce as a
consequence of identical net paths.

## B. Look-ahead audit

### `v113_longer_history.py` — no look-ahead found
- Aggregation: `resample(rule, label="left", closed="left")` on tz-aware hourly
  `open_time`; OHLCV from within-bar hours only (`open` first, `high` max,
  `low` min, `close` last, `volume` sum, `quote_volume = sum(volume*close)`),
  `close_time = open_time + rule - 1ms`; 4h keeps `n >= 3`, 1d keeps `n >= 20`.
  Bar `t` uses only its constituent hours. Pass.
- Prepend filter: `pb[open_time < b.iloc[0]]` / `pdly[open_time < d.iloc[0]]`
  where `b, d` are the v92 base (spot prefix + USD-M), so only rows before the
  first existing v92 4h/1d bar are added; OOS test rows unchanged (10950 rows /
  anchor confirmed). Pass.
- Missing columns (funding/taker) stay NaN in the prefix, same treatment as the
  2017 spot prefix; funding `merge_asof backward` and ribbon-via-daily-SMA stay
  causal (ribbon 0 while SMAs unavailable). Pass.
- Labels/embargo/weights/vol/execution reuse the audited `v92` / `v94` code paths
  (`train_predict`, `weights_from`, `weights_ls`, `vol_target_scale`,
  `v103.evaluate` with `scale=1.0` for the blend) — bit-exact reproduction above
  confirms no hidden logic. Pass.
- Overlap dedup (`drop_duplicates("open_time")` over pre2017+main): the single
  shared hour (2017-08-01 00:00) carries identical OHLCV in both files, so
  keep-first vs keep-last is immaterial. Pass with note.

### `v114_bitstamp_history.py` — no look-ahead found
- BTC hourly = Bitstamp rows `>= 2013-01-01` and `< first Coinbase hour`, then
  Coinbase hours: contiguous, no overlap (Bitstamp ends 2015-07-20 20:00,
  Coinbase starts 21:00), no gap. 2011-12 excluded as illiquid with an explicit
  logged reason. ETH reuses the v113 path. Pass.
- Aggregation/books/costs identical to v113 via wrapped `cb_bars_ext`. Pass.
- `HERE` redirect writes `v114_result.json` (removes the intermediate
  `v113_result.json` copy); `version` relabelled to `v114`. Reporting mechanics
  only. Pass.

## C. Junction artifacts (price gaps between sources)

Measured on the blind (bit-exact) extended panels:

| junction | last prefix close -> first next open | gap |
|---|---|---|
| v113 BTC 4h: Coinbase 2017-08-17 00:00 -> spot 04:00 | 4280.01 -> 4261.48 | -0.43% |
| v113 BTC 1d: Coinbase 2017-08-16 -> spot 2017-08-17 | 4370.01 -> 4261.48 | -2.48% (incl. overnight move, not a pure cross-exchange tick) |
| v113 ETH 4h | 299.87 -> 301.13 | +0.42% |
| v113 ETH 1d | 300.45 -> 301.13 | +0.23% |
| v114 BTC: Bitstamp 2015-07-20 20:00 -> Coinbase 21:00 | 277.73 -> 278.00 | +0.10% |

Assessment: gaps are ordinary cross-exchange level differences at the seam,
timestamped on the correct bars (prefix rows strictly before the first base bar;
no interleaving). They enter training history only (2015-2017 / 2013-2015) as
single-bar log returns inside rolling features — no forward leakage into the
2021+ OOS windows. The 1d BTC -2.48% is dominated by the day's own price action,
not a data error. v114's 2013+ Bitstamp prefix has only 29 zero-volume 4h bars
out of 10133 (the 2011-12 illiquid tail was excluded), so no flat-history
vol=0 pathology beyond HGB-NaN-native single-bar NaNs. One cosmetic note: the 1d
prepend cutoff (`< first 1d bar 2017-08-17 00:00`) and 4h cutoff (`< 04:00`) admit
the Coinbase 00:00-04:00 4h bar on 2017-08-17 while that date's 1d bar is spot —
a one-day cross-timeframe source mix, timestamp-correct and negligible.

## D. Manifest notes
- `v113/result_manifest.json` and `v114/result_manifest.json`: check track/status
  vs the registry at rotate time; both must keep `live_approved: false` (parallel
  research results are never live-approved). Content hashes in the manifests refer
  to the leader scripts audited here.
- Gate context (not an audit finding): v113 primary blend monthly 2.621%,
  worst-year DD 20.73%; v114 primary blend monthly 2.744%, worst-year DD 22.76% —
  both below the 5%/month acceptance gate and above the 20% DD limit.

## E. Verdict
- Blind replication is bit-exact for both extensions: train rows, per-anchor ICs
  (v92 vs y, v94 vs y42), and all yearly nets/DDs/fills for the v92 LO, v94 LS,
  and v96 blend books in normal, fee-stress, and execution-stress scenarios.
- Leader scripts have no look-ahead in aggregation, prepend filtering, features,
  labels/embargo, weights, vol-target, or execution. Junction gaps are small,
  correctly timestamped training-history effects, not leakage.
- Audit complete; leader files untouched.
