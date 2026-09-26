# v120 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v120_audit/` +
`tests/test_v120_audit.py` only. Base: audited v118 replication (v115 books +
per-asset no-trade band in the sequential engine). No leader files edited.

Blind protocol: `replication.json` (via `replicate_v120.py`,
`tests/test_v120_audit.py` passing) was saved BEFORE opening `v120/`.
Pre-save reads were limited to the allowed base (`v115_audit/`,
`v118_v119_audit/`, `v118/v118_no_trade_band.py`,
`v118/v118_result.json` for the band-0.05 reference check, audit/test files —
not in the forbidden set). The parent round directory listing exposed only
`v120/` filenames (not file contents). `v120/v120_result.json`,
`v120/v120_risk_frontier.py`, `result_manifest.json`, `run.log` were first
opened after Part A save. Part A imports no v120/v118/v115 leader module
(all formulas inline from the assignment text + audited OOS CSVs + raw carry).

## A. Number comparison (blind vs leader)

Key map: blind `t010/t012/t015/t018/t020/t022/t025` <-> leader
`t10/t12/t15/t18/t20/t22/t25` (leader `f"t{tgt*100:02d}"`).

Bit-exact on all 7 targets x 3 scenarios x 5 years (105 yearly cells):
max abs net diff 0.00pp, max abs DD diff 0.00pp, fills exact,
monthly/worst-year/full-path exact. No 1pp return / 0.5pp DD threshold
exceeded, so no diff explanation is triggered.

Headlines blind = leader (`run.log` lines 1-7), monthly / full-path DD:
t10 normal 1.622/12.29; fee 1.536/12.6; exec 1.428/12.99.
t12 normal 2.199/13.11; fee 2.085/14.13; exec 1.943/15.4.
t15 normal 2.679/15.91; fee 2.525/16.35; exec 2.332/17.13 (= v118 band005).
t18 normal 3.058/20.37; fee 2.867/20.84; exec 2.628/21.42.
t20 normal 3.274/24.3; fee 3.059/24.85; exec 2.791/25.54.
t22 normal 3.576/26.07; fee 3.341/26.6; exec 3.049/27.25.
t25 normal 3.671/26.49; fee 3.412/27.02; exec 3.089/27.67.
Worst-year DD equals full-path DD except t12 (normal 12.56/13.11,
fee 12.92/14.13, exec 13.36/15.4) and t15-exec (16.89/17.13).

Yearly detail (normal, nets/DDs/fills blind = leader):
t18 12.72/20.37/223, 18.36/13.44/270, 77.54/8.39/204, 69.92/12.52/285,
51.45/10.83/269. t15 14.83/15.91/195, 15.80/11.47/247, 62.39/7.18/187,
62.37/8.67/282, 39.34/8.39/260 (= v118 secondary_band005).
Fills monotone in target per scenario (t10 851, t12 1006, t15 1171,
t18 1251, t20 1354, t22 1387, t25 1457 totals), held path cost-independent.

## B. Look-ahead audit

`v120/v120_risk_frontier.py` (41 lines) — no look-ahead found.
- Books (`v118.v115.books_v115()` :26): audited v115 books path, no new
  training. Pass (see v115/v118 audits).
- Scale (:31 via `v118.run_band(..., target=tgt)`): `v118_no_trade_band.py`
  :40-42 realized = 0.8*sum(books.shift(2)*ret1) + 0.6*carry.shift(1),
  trailing 360/min-120 *sqrt(2190), s = min(target/vol,2) NaN->1. Target
  enters only the scalar numerator; vol is target-independent and causal.
  Pass.
- Band loop (`v118.run_band` :52-58): per-asset held->tgt iff |tgt-held|>0.05,
  tgt=0 taken immediately outside live calendar [START,END); turnover
  sum|new-held|; gross new*o[i+2]/o[i+1]-1; funding 0.00005 on held long;
  carry 0.6*s unchanged with |dc|*2*0.0004/1.2. Decision uses only current
  target + past held; forward return is execution accounting (same lag as
  v110). Pass.
- Frontier loop (:28-33): same causal engine swept over 7 targets, cap 2x,
  ungoverned, three v92 scenarios; `summarize` is the audited v110 yearly /
  full-path DD reporter. No refit, no test-peek beyond reporting. Pass.
- Reporting caveat (script :4-6, manifest note): any target picked from this
  table is an EX-POST risk-budget choice on data already seen; registered
  primary t18 was fixed before running as midpoint between audited 0.15 and
  0.20/0.25 rows. Correctly labelled; not a causal defect.

## C. Manifest notes / verdict

- `v120/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Primary_t18 monthly 3.058 / full DD 20.37 and frontier
  t10..t25 monthly/full-DD rows match blind exactly; yearly_t18 normal
  12.72/18.36/77.54/69.92/51.45 matches blind t018.
- Blind replication is bit-exact on all yearly nets/DDs/fills/monthlies/
  worst-year/full-path DDs in all scenarios. No look-ahead in vol scaling,
  band timing, or execution. Effect: monthly rises monotonically with target
  (1.62 -> 3.67 normal) while full-path DD rises (12.29 -> 26.49); only
  targets <= 0.15 keep full-path DD <= 20% in all scenarios. Audit complete;
  leader files untouched.
