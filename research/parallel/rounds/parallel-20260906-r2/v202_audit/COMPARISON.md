# v202 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v202_audit/replication.json
was saved before opening v202/ (see Part A script header and the C1/C2
convention asserts). Base: research/parallel/rounds/parallel-20260906-r2/
engine_user/engine_user.py (the gate engine implementing the AGENTS.md 2026-09-27
user goal, gate cost model and current execution assumptions), with the two
v188 conventions: (1) 1m-marked DD peaks over the minute path, (2) a held
stop wins a same-minute tie with a new book fill. Leader files not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v202/v202_result.json
from research/parallel/rounds/parallel-20260906-r2/v202/v202_quarterly_retrain.py.
Audit: rows in research/parallel/rounds/parallel-20260906-r2/v202_audit/
replication.json (annual v151 = (A+B)/2 from members_v154, quarterly
(Aq+Bq)/2 from members_quarterly, v197 selected rules m = 4, rung SL 5
sigma_4h, TP 1 sigma_4h, book limit (d, W) = (0.001, 239), target 0.25,
cap 2.0, gap 0.02, size_mult 1.5, budget X = 0.12, rungs (2.5, 3, 3.5, 4)).

## Quarterly schedule check

v202_quarterly_retrain.py:31 builds Q from pd.date_range 2021-09-24,
periods 20, DateOffset months 3, END maps each anchor to the next (last
until 2026-09-24). For 24th dates this equals calendar months +3. The
audit generates the same 20 anchors by year/month arithmetic and the
same next mapping; the reported anchors_quarterly list equals the audit
quarterly_anchors exactly. PASS.

## Member rebuild check (two quarterly anchors IN FULL)

Audit rebuilt member A (v144 books_v142) and member B (v151
books_with_options) for 2021-09-24 and 2021-12-24 with independent
quarterly train/predict functions copying the audited cutoffs
(v92 102 bars + label-realized 43 bars, v94 144 bars + per-h, v103 78
bars + per-h, vol 102 bars + 44 bars), HGB v92 hyperparameters, v142
cross-sectional step, v150 options merge for B with OPT excluded from
vol models, tranched 6-phase weights and 0.25/0.25/0.5 books with own
causal vol targets. Train rows grow with the anchor (e.g. v92 45915 ->
48645, v103 33388/33328 -> 36118/36058, vol 46120/33293 -> 48850/36023;
identical for A and B since options add columns, not rows).

Cached-slice comparison over the rebuilt span [2021-09-24, 2022-03-24),
1086 bars each member:

| member | common bars | max abs diff | mean abs diff |
| --- | --- | --- | --- |
| A | 1086 | 0.0 | 0.0 |
| B | 1086 | 0.0 | 0.0 |

PASS — both quarterly members reproduce the cache bit-exact on the
rebuilt quarters.

## Engine rows

Annual row is bit-exact. Quarterly matches bit-exact under the driver
alignment (see note); the blind native-index run differs only by the 6
extra quarterly bars.

| row | monthly dev4 % | monthly 5y % | last-year monthly % | gate DD % | yearly nets % |
| --- | --- | --- | --- | --- | --- |
| reported ref_annual_v151 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| audit annual_(A+B)/2 | 5.562 | 4.996 | 2.761 | 19.72 | 40.67 / 51.32 / 147.63 / 154.98 / 38.66 |
| diff | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |
| reported quarterly_v151 | 5.309 | 5.11 | 4.314 | 22.47 | 49.60 / 61.63 / 96.05 / 152.70 / 66.00 |
| audit quarterly native (Aq+Bq)/2 | 5.290 | 5.094 | 4.314 | 22.47 | 49.60 / 61.63 / 95.59 / 151.09 / 66.00 |
| driver-aligned rerun | 5.309 | 5.11 | 4.314 | 22.47 | 49.60 / 61.63 / 96.05 / 152.70 / 66.00 |
| diff driver vs reported | 0.000pp | 0.000pp | 0.000pp | 0.00pp | exact |

Yearly legs: annual matches in full (net/monthly/dd_1m/mean_g).
Quarterly driver-aligned matches in full; native differs only in
2023 (95.59 vs 96.05) and 2024 (151.09 vs 152.70) with dd_4h 18.58 vs
18.25; yearly dd_1m legs match in both (17.37 / 18.10 / 22.47 / 11.19 /
15.31), last year 66.00/4.314 exact, gate DD 22.47 exact.

Stats: annual bit-exact (40078 / 4079 / 76 / 48 / 5004 / 191 / 2717 /
0 / 0.0968 / 0.1817, gross 5362.3762, bars 10944, dd 19.07/19.72).
Quarterly driver-aligned bit-exact (40997 / 4198 / 90 / 43 / 5007 / 193 /
2716 / 0 / 0.1002 / 0.1787, gross 5262.3907, bars 10944, dd 18.25/22.47).
Native quarterly has +11 fills, +8 unfilled, -3 rung TPs from the 6
extra bars (bars 10950, gross 5261.8572). No liquidations on any row.

Alignment note: members_quarterly has 10956 bars vs members_v154 and
books_v154 10950 bars; the 6 extra bars are 2024-09-23 00..20. The
driver reindexes Aq/Bq to the books154 index and prepares with books154
(v202_quarterly_retrain.py:104-106), dropping those 6 bars so both
pipelines run on identical bars. The blind audit evaluated quarterly on
its native index, hence the small 2023/2024 differences above. A
post-blind rerun with the driver alignment reproduces reported quarterly
bit-exact, confirming the difference is evaluation alignment only, not
model leakage. PASS with note.

## Selection uses no last-year statistic

v202_quarterly_retrain.py:113-115: ok = rows with gate_dd <= 20 and all
yearly[:4] net_pct >= 0; pool = ok or all rows; sel = max monthly_dev4.
monthly_dev4 in engine_user is the geometric mean of years[:4] only. The
last-year monthlies (2.761 annual, 4.314 quarterly) are reported, never
ranked on. PASS.

Eligibility: quarterly (dev4 5.309) is correctly excluded by gate_dd
22.47 > 20, so ok = ref_annual only; selection ref_annual is the only
eligible row. Audit eligible annual_(A+B)/2 only, selection annual
maps to reported selected ref_annual_v151. PASS.

## Look-ahead check

Driver plus engine_user:

- Feature timing: quarterly wrapper only slices test rows to the
  quarter (_cut on t in v202_quarterly_retrain.py:42-44); training calls
  are the original audited train_predict/vol_predict with cutoff =
  anchor - embargo (v92 102, v94 144, v103 78, vol 102 bars) and the
  per-horizon label-realized condition. Target uses books[t], s[t], g[t];
  sigma windows end at t; cubes row i is holding bar T. Member mix
  (A+B)/2 and (Aq+Bq)/2 is algebraic at bar t. PASS.
- Label windows: no forward return read; quarterly test is [anchor,
  next anchor); PnL only from 1m fills, SL/TP during T, T+4h exits.
  Each quarter predicted only by its own anchor model (tp per anchor,
  vp concat over per-anchor ovp calls). PASS.
- Fit windows: no statistic fit on any test quarter in this path; vol
  and governor are running causal filters; quarterly anchors/cutoffs
  are the pre-registered schedule (20 anchors, at most 2 pipelines),
  not tuned here; selection on first-four-years metrics only. The audit
  train-row counts increase monotonically with anchor as expected. PASS.
- Fill timing: book limit 10 bps, minutes 2..238 strict trade-through
  with expiry and no fallback; held SL/TP from minute 0 over
  [0, fill_min + 1) with stop-wins-tie and stop-first, flat after;
  sleeve trigger 16..238 strict with exits strictly after fill minute
  in budget order X = 0.12, gap 0.02; rung SL 5, TP 1, notional
  s g 1.5 0.25/4/1.657. PASS.

Fee/funding arithmetic: maker 0.0002 entries/TP, taker 0.00055
stops/market exits, longs pay 0.0001 at 00/08/16 UTC, shorts zero, no
carry (engine_user.py:33-36). The AGENTS.md gate cost model.
tests/test_engine_user.py covers limit/TP/stop/expiry/funding. PASS.

## Verdict

- Engineering REPRODUCED: annual bit-exact; quarterly bit-exact under
  the driver alignment (native differs only by 6 evaluation bars, same
  conclusion); members A/B bit-exact on two full quarterly rebuilds.
- Look-ahead PASS (quarterly cutoffs unchanged per target, per-quarter
  models only, causal features/sigma/scale/governor/fills, first-four
  selection only).
- Direction result: quarterly retraining raises 5y (4.996 -> 5.11) and
  the most recent year (2.761 -> 4.314) but lowers dev4 (5.562 -> 5.309)
  and breaches the DD gate (22.47 > 20); correctly excluded. Selected =
  annual reference (the v197 config).
- Gate: selected ref_annual is the best dev4 under the DD gate but the
  gate still fails: 5y 4.996 < 5 and most recent year 2.761 < 5 (nets
  40.67 / 51.32 / 147.63 / 154.98 / 38.66). Manifest (status rejected,
  live_approved false) must stay non-live_approved.
