# v92 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v92/` (see `replication.json`,
`predictions.csv`, `equity.csv` in this folder). Audit scope:
`v92/v92_pooled_hgb_vt.py`, `v92/v92_result.json`, `v92/result_manifest.json`.
No leader files were edited. All writes are under `v92_audit/` + `tests/test_v92_audit.py`.

## A. Number comparison (blind audit vs leader v92)

Per-anchor (blind 4-asset BTC/ETH/BNB/XRP vs leader 5-asset +SOL):

| anchor | train rows blind | train rows leader | diff | IC blind | IC leader | IC diff |
|---|---|---|---|---|---|---|
| 2021-09-24 | 31027 | 33088 | +2061 | 0.0584 | 0.1058 | 0.0474 |
| 2022-09-24 | 39787 | 44038 | +4251 | -0.0408 | 0.0010 | 0.0418 |
| 2023-09-24 | 48547 | 54988 | +6441 | 0.0818 | 0.0952 | 0.0134 |
| 2024-09-24 | 57331 | 65968 | +8637 | 0.1398 | 0.0988 | 0.0410 |
| 2025-09-24 | 66091 | 76918 | +10827 | 0.1457 | 0.1506 | 0.0049 |

Hidden-year 2025-09-24.. (normal costs):

| metric | blind audit | leader v92 model_normal | diff |
|---|---|---|---|
| net % | 22.72 | 16.70 | 6.02pp |
| max DD % | 21.92 | 28.47 | 6.55pp |
| monthly geometric % | 1.722 | 1.296 | 0.43pp |
| fills | 1083 | 1102 | — (different universe) |

5-year (normal costs):

| metric | blind audit (continuous equity) | leader model_normal_5y (geo-mean of yearly nets) | note |
|---|---|---|---|
| monthly geometric % | 2.042 | 2.934 | method + universe differ |
| net total % | 236.05 | — (annual 41.49 from yearly nets) | — |
| max DD / worst-year DD | 30.99 (continuous) | 28.47 (worst yearly) | — |

Thresholds from spec (IC diff > 0.01 or return diff > 1pp = explain):
exceeded for 4/5 anchors and hidden-year net (6.02pp). Root cause isolated below.

## B. Root cause (universe mismatch, not a coding error in the shared logic)

Spec (1) says "prefix each of BTC/ETH/BNB/XRP", which was read blind as a
4-asset universe (BTC=0,ETH=1,BNB=2,XRP=3). The leader script uses
`SYMS=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT")` (5 assets,
asset ids 0..4); SOL gets no spot prefix (no `SOL*_2017` files exist) but
participates in training, prediction, and the book.

Train-row gaps match SOL-only rows exactly (SOL `y` with same
cutoff/embargo rule, verified independently):

- 2021: 2061, 2022: 4251, 2023: 6441, 2024: 8637, 2025: 10827.
- Blind + SOL = leader for every anchor
  (e.g. 31027+2061=33088; 66091+10827=76918).

Consequences: extra SOL training rows shift every HGB split (plus asset-id
0..4 vs 0..3 encoding change), so ICs move by 0.01–0.05 except the hidden
year (0.0049). Portfolio differences (SOL weight, `n_assets/5` divisor now
reaching 1.0, vol-target path, turnover/fills) explain the 6pp hidden-year
net gap and the 5y monthly gap. Feature definitions, funding
(rolling21/min3, rolling90/min9 x1e4), ribbon-0, HGB params, cutoff/embargo
(`A-408h`, `t+172h<cutoff`), weight formula, vol window (360/min120
x sqrt(2190), cap 2, NaN->1), and execution
(`W_t*scale_t` earns `open[t+2]/open[t+1]-1`, fee 0.0002, funding 0.00005)
are otherwise identical.

## C. Look-ahead audit of `v92_pooled_hgb_vt.py`

- Spot prefix join: `pre_b[open_time < b.open_time.iloc[0]]` (same for daily),
  concat + sort. Only spot bars strictly before the first USD-M bar are added;
  funding comes from USD-M only (NaN in the spot region). No future inputs.
  Minor: comparison relies on parquet datetime ordering; `b` is already
  chronological, so `iloc[0]` is the first bar. Pass.
- Features/label/embargo: identical to audited v89 (past closes, ewm
  adjust=False, daily SMA/ribbon via merge_asof backward, funding merge_asof
  backward, volume z past 180, `y=clip(log(open[t+43]/open[t+1])/(vol42√42),±4)`,
  cutoff `A-4h*102`, train requires label realized before cutoff). Pass.
- Continuous OOS series: five `[A,A+365d)` prediction sets concatenated;
  weights (`s=min(max(pred,0)/0.5,1)`, zeroed when `rib==-1`,
  `raw=s/(vol42√2190)`, normalise to 1 then `*min(1,count/5)`, every 6th bar
  ffill) use only contemporaneous pred/rib/vol42. Pass.
- Vol-target timing: `realized=(W.shift(2)*(o/o.shift(1)-1)).sum`,
  i.e. weights decided at `t-2` times the open-to-open return realized by `t`;
  `vol=rolling(360,min120)std*sqrt(2190)`, `scale=min(0.20/vol,2)`, NaN->1.
  All inputs known at close `t`; scale applies to `W_t` earning forward
  `open[t+2]/open[t+1]-1`. No forward use. Early-OOS NaN->1 is a causal
  default (uses only OOS history, not pre-OOS — conservative, not leakage). Pass.
- Execution timing: `r=o.shift(-2)/o.shift(-1)-1`, turnover from `Wk.diff`,
  long funding `0.00005/bar`. One-bar delay, fills at `open[t+1]`. Pass.

No look-ahead found in the spot join, the continuous OOS construction, or the
vol-target timing. Non-leakage notes: stale docstring still says
"Registry … / v89" and shows the v89 run command; yearly `stats` are cut from
the single scaled OOS path while the 5y summary is the geometric mean of those
yearly nets (as in v89), not the continuous-equity compounding.

## D. Manifest note

`result_manifest.json`: v92/track A, status `rejected`, `live_approved:false`,
`audit.passed:false, replay_complete:false` ("awaiting OpenCode blind audit").
Hidden-year model_normal net +16.7%, DD 28.47%; 5y monthly 2.934% with worst-year
DD 28.47%. TSMOM/blend legs are also reported; `model_K_mean` is the mean
causal vol-target scale (not the v89 drawdown K rule).

## E. Verdict

Blind reproduced the full pipeline logic but on the wrong universe (4 vs 5
assets) due to spec wording; train-row deltas are exactly the SOL rows, and
IC/return gaps follow from that. Leader code has no look-ahead in features,
labels/embargo, spot prefix, continuous OOS series, vol-target timing, or
execution. Audit complete; leader files untouched.
