# v118 + v119 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v118_v119_audit/` +
`tests/test_v118_v119_audit.py` only. Base: audited v115 replication
(books, v110 engine) and v113_v114 (v114 panel) replications. No leader files edited.

Blind protocol: `replication.json` (+ `predictions_v119.csv`,
`replicate_v118_v119.py`, `tests/test_v118_v119_audit.py` passing) was saved
BEFORE opening `v118/` / `v119/`. Pre-save reads were limited to the allowed
base (`v115_audit/`, `v113_v114_audit/`, `v110_audit/`, `v117_audit/`,
`v103_v105_audit/` listing, `v115/v115_result.json` for the v115-primary
reference check — not in the forbidden set). `v118/` / `v119/` (scripts,
results, manifests, logs) were first opened after Part A save. Part A imports
no v118/v119/v115/v114 leader module (all formulas inline from the assignment
text + audited OOS CSVs + raw data).

## A. Number comparison (blind vs leader)

Key maps: blind `primary_band002`/`secondary_band005`/`reference_band000` <->
leader `primary_band002`/`secondary_band005`/`reference_band0_v115`;
blind `v92_lo_new_*` <-> leader `primary_v92_lo_nested`;
blind `v96_blend_new94_*` <-> leader `secondary_v96_blend`.

### v118 (bands on v115 primary t15 ungoverned) — bit-exact, all 3 scenarios

- Yearly net/DD/fills/sharpe/monthly: max abs net diff 0.00pp over
  3 bands x 3 scenarios x 5 years (45 cells); max abs DD diff 0.00pp
  (45 yearly + 9 full-path DDs); fills exact; monthly exact.
  No 1pp return / 0.5pp DD threshold exceeded.
- Headlines blind = leader (`run.log` lines 1-9):
  band002 normal monthly 2.65 / worst DD 16.98 / full-path 16.98;
  fee 2.457/17.44/17.52; exec 2.218/18.01/19.29.
  band005 normal 2.679/15.91/15.91; fee 2.525/16.35/16.35; exec 2.332/16.89/17.13.
  band0 reference normal 2.608/16.78/16.78 (= v115 primary); fee 2.388/17.31/17.31;
  exec 2.114/17.96/19.13.
- Yearly blind = leader, normal:
  band002 nets 15.31/16.18/62.46/53.56/43.69; DDs 16.98/13.54/7.39/10.76/8.95;
  fills 298/372/327/380/357.
  band005 nets 14.83/15.80/62.39/62.37/39.34; DDs 15.91/11.47/7.18/8.67/8.39;
  fills 195/247/187/282/260.
  band0 nets 13.91/16.73/63.52/51.22/42.55 (= v115); fills 1831/2180/2180/2177/2115.
- Fee/exec yearly cells likewise exact. Fills identical across scenarios per
  band (held path cost-independent), monotone 1831+… > 1734 > 1171 total
  (band0 > band002 > band005).

### v119 (nested grid on v114 panel) — bit-exact

- Selection blind = leader (`run.log` lines 1-5), all 30 val scores + chosen + test IC:
  2021 val d3_l300 0.1141 / d3_l1000 0.0968 / d4_l300 0.1221 / d4_l1000 0.1005 /
  d6_l300 0.0888 / d6_l1000 0.0903, chosen d4_l300, ic_test 0.0863.
  2022 val 0.0201/0.0299/-0.0119/0.0377/-0.0071/0.0070, chosen d4_l1000, ic -0.0334.
  2023 val 0.0648/0.0520/0.0581/0.0629/0.0641/0.0543, chosen d3_l300, ic 0.1089.
  2024 val 0.0679/0.0737/0.0723/0.0763/0.0714/0.0825, chosen d6_l1000, ic 0.0949.
  2025 val 0.1001/0.1026/0.1043/0.1091/0.1211/0.1153, chosen d6_l300, ic 0.1501.
- Train rows blind = v114 audit (45915/56865/67815/78795/89745); inner
  28028/34686/45405/56385/67335; val 17311/21599/21685/21685/21685.
- Books blind = leader, all 3 scenarios (max net diff 0.00pp, max DD diff 0.00pp):
  LO nested normal nets -3.53/45.85/80.81/56.76/27.72; DDs 23.64/11.97/10.80/12.79/18.04;
  fills 1333/1264/1433/1806/1181; monthly 2.75.
  Blend normal nets 4.92/23.52/71.66/50.32/44.94; DDs 22.76/11.27/8.53/12.73/10.69;
  fills 1603/2151/2162/2152/2057; monthly 2.665.
  Fee/exec cells exact (see `run.log` lines 6-11 vs `replication.json`).
  2021 LO/blend equal v114 baseline (chosen d4_l300 = v114 config).

## B. Look-ahead audit

### `v118/v118_no_trade_band.py` — no look-ahead found
- Books/s (`v115.books_v115`, `v99` wrapper :40-42): audited v115 books +
  causal s (`books.shift(2)`, `carry.shift(1)`, trailing 360/min-120, cap 2,
  NaN->1). No new training. Pass (see v115/v110 audits).
- Band loop (:52-58): per-asset `held -> tgt` iff `|tgt-held| > band`
  (else hold), `tgt=0` taken immediately outside live (`live` calendar-only
  `[START,END)`); turnover `sum|new-held|`; gross `new * o[i+2]/o[i+1]-1`;
  funding on held long gross 0.00005; carry `0.6*s` unchanged with
  `|dc|*2*0.0004/1.2`. Decision uses only current target + past held;
  forward return is execution accounting (same lag as v110). Pass.
- Band 0 reproduces v115 primary bit-exactly (confirmed blind pre-open).

### `v119/v119_nested_cv.py` — no look-ahead found
- Panel (`:48` via `v114_bitstamp_history` + `v113.cb_bars_ext`): audited v114
  extended panel (Bitstamp>=2013-01-01 + Coinbase BTC, Coinbase ETH, spot+USD-M
  base, UTC-floor agg). Pass (see v113_v114 audit).
- Splits (:55-60): `cutoff=A-102*4h`; train `t<cutoff & y & t+43*4h<cutoff`
  (v92 H=42 label embargo); `val_start=cutoff-730d`, `val=train[t>=val_start]`;
  `itr=train[t+43*4h < val_start-102*4h]` (inner embargo). All cutoffs from
  training rows only; test year never used for fitting/selection. Pass.
- Grid (:62-70): 6 configs (depth 3/4/6 x leaf 300/1000, lr 0.03, iter 400,
  l2 1.0, seed 0), Spearman on validation, best refit on all train, predict
  test year. `pd.Series.corr(spearman)` vs blind `scipy.spearmanr` agree to 4dp
  (verified). No test peek. Pass.
- Books (:75-82): `weights_from` LO + `vol_target_scale` (shift-2, trailing)
  + `v103.evaluate` forward execution; v94 LS via `train_predict` per anchor
  (audited embargoes); blend `0.5*W*s + 0.5*W94*s94` scale 1. Blind OOS-open
  recomputation matches panel-open computation bit-exactly. Pass.

## C. Manifest notes / verdict

- `v118/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  audit pending. Primary monthly 2.65 / fills 1734 / 60 months and yearly
  15.31/16.18/62.46/53.56/43.69 match blind band002.
- `v119/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Primary LO monthly 2.75 / fills 7017 and yearly
  -3.53/45.85/80.81/56.76/27.72 match blind.
- Blind replication is bit-exact on all v118 yearly nets/DDs/sharpes/fills/
  monthlies/full-path DDs and all v119 val scores/chosen/test ICs plus LO and
  blend yearly nets/DDs/fills in all scenarios. No look-ahead in band timing,
  nested splits, scales, or execution. Effect: bands cut fills ~6-9x with
  small net lift vs v115 (band002 2.65, band005 2.679 vs 2.608 monthly);
  nested grid picks d4_l300/d4_l1000/d3_l300/d6_l1000/d6_l300 with test ICs
  near v114 baseline. Audit complete; leader files untouched.
