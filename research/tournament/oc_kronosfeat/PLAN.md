# oc_kronosfeat — PLAN (pre-registered 2026-10-07/08, BEFORE any outcome)

Diagnostic only. Nothing is selected; the post-release year has been scored
once for K2 already. Dev years Y0..Y3 are INSIDE Kronos pretraining
(= UPPER BOUND); Y4 = 2025-09-24..2026-09-24 is post-release = CLEAN.
No tuning, no thresholds, no model choice; all settings below are fixed
before any IC / Spearman / quintile is computed.

## Inputs (read-only, never edited)
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet`
  (sym, shift, T, sigma_log, C0, er1, er6, vol1, vol6, rng1, low1, pdrop2,
  pdrop3; 20/20 groups, 2020-10-06..2026-09-23; feature at bar open T uses
  only 400 bars closing <= T on that shift's grid).
- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (sym, shift, T, open/high/low/close; shifts 0..3, 2020-08-01..2026-09-23).
- Dip replica core copied from
  `research/tournament/oc_placebo_dip/compute_placebo_dip.py` (exact D0 rung
  outcomes + B1 sizes; must reproduce base 5y sum 7.718).
- Book yardstick copied from
  `research/tournament/oc_bookichorizon/compute_bookichorizon.py`:
  y = (open[t+h]/open[t]-1)/sigma, sigma = trailing-360-bar std of 1-bar
  open-to-open SIMPLE returns (min 120, causal, per sym+shift).
- Deployed book weights = FINAL series of oc_bookichorizon
  (O1/CB blend + v421 x0.5 bear filter on longs, on books_v154 standard
  grid = shift-0 grid; recomputed read-only from
  `artifacts/research/engine_real/` caches, never refit).

## Years (fixed)
Y0=[2021-09-24,2022-09-24), Y1=[2022-09-24,2023-09-24),
Y2=[2023-09-24,2024-09-24), Y3=[2024-09-24,2025-09-24),
Y4=[2025-09-24,2026-09-24). Labels by holding-bar open T (dip) /
decision-bar open T (book). Y0..Y3 labelled UPPER BOUND, Y4 labelled CLEAN.

## Table 1 — DIPS (per year)
- Ledger: exact placebo replica (RUNGS 2.5/3/3.5/4/5, live offsets 16..238
  strict trade-through, TP 1sg, close5 stop 4sg, 8sg backstop, timeout at
  next-bar open, maker 0.0002/taker 0.00055, v293 settle funding,
  B1 size w=1/(1+n_fill), 4 clock phases from 2020-08-01 +0/1/2/3h, bars open
  in [2021-09-24,2026-09-24)). Per fill store: phase=shift, coin, T (bar
  open timestamp), rung, w, n_fill, y10 (TP1.0 net), how10 in
  {tp,stop,backstop,time}, exit day. Fidelity gate: 4-phase-mean 5y sum of
  w*y10 must equal 7.718 +/- 0.01 and phase-0 raw sums must match
  [2.388,0.183,3.810,2.579,0.712] approximately (pairing: all 3 TP legs
  finite, same as placebo); else STOP.
- Join: Kronos feature at (sym, shift=phase, T = holding-bar open, same
  shift). Inner join; report coverage (fills with feature / total).
- Outcome = raw y10 (unweighted, TP1.0 net). Stop flag = how10 in
  {stop, backstop}.
- Per year x feature (all 8: er1, er6, vol1, vol6, rng1, low1, pdrop2,
  pdrop3): Spearman(feature, y10) pooled over coins x shifts x rungs, n,
  95% week-block bootstrap CI (B=500, seed 7; blocks = calendar weeks by T,
  resample weeks with replacement, recompute Spearman; percentile 2.5/97.5).
- Per year x feature: quintile split of fills by that feature using THAT
  YEAR's pooled quintile edges (descriptive, disclosed in-sample edges);
  report per quintile: n, mean y10, stop rate. Edges stored in results.
- Extra: same Spearman per coin (pooled over shifts) for low1 only
  (the K2 risk feature), to see coin stability.

## Table 2 — BOOK (per year)
- Rows: every (sym, shift, T) with T in [2021-09-24,2026-09-24) and feature
  present. sigma[t] = std of trailing 360 1-bar simple open-to-open returns
  ending at t on that (sym,shift) grid (min 120; NaN/small <=0 dropped).
  Forward fh = open[t+h]/open[t]-1 on the SAME shift grid for
  h in {1,2,6,18} bars; y_h = fh/sigma[t] (NaN dropped; rows whose label
  needs opens beyond 2026-09-23 20:00 dropped).
- Features tested (5): er1, er6, low1, pdrop2, vol1.
- Per year x feature x h: pooled Spearman(feature, y_h) over all
  (coin,shift,T) rows, n, 95% week-block bootstrap CI (same week blocks,
  B=500, seed (7,y,h)); per-coin Spearman (pooled over shifts) with same CI.
- Vol forecasting: same cells with |y_h| as target:
  Spearman(feature, |y_h|) pooled + per coin with CIs.
- Week blocks: weeks starting Monday 00:00 UTC by T; resampling preserves
  all intra-week cross-shift/coin correlation. Pre-registered before seeing
  any IC.

## Table 3 — novelty vs G2 (per year)
- Book weights: FINAL deployed weights joined to shift-0 Kronos rows on
  (sym, T) (grids match exactly; verified 10950/10950). Per year x feature
  (same 8): Spearman(feature, FINAL_weight) pooled + per coin, n, week-block
  CI. Also Spearman(feature, |FINAL_weight|) pooled (magnitude channel).
- B1 flush: from the dip ledger, per holding bar (sym,shift,T) with >=1
  filled rung, flush_bar = MEAN n_fill over its filled rungs (0..4;
  pre-registered; max reported as sensitivity only if mean is significant).
  Per year x feature: Spearman(feature, flush_bar) over bars pooled over
  shifts (+ shift-0-only sensitivity), n, week-block CI.
- Interpretation is correlational only (is Kronos information new?).

## Costs / leakage / selection
- No PnL, no fees/funding beyond the dip ledger's baked-in replica costs;
  book ICs are rank diagnostics with no fills claimed.
- Feature timing: Kronos row at T uses bars closing <= T; dip outcome uses
  minutes (f+1..240) after T; book labels use opens > T; sigma uses opens
  <= t. No fit in this study (quintile edges are descriptive per-year
  summaries, not traded thresholds). No test-year statistic feeds any
  choice; Y4 is reported but never used to choose (nothing is chosen).
- Outputs: results.json + REPORT.md (tables per year, key question in bold,
  3-line Vietnamese verdict) in this folder; pytest file
  tests/test_oc_kronosfeat.py (causality/truncation + hand-checked
  synthetic). Scratch only under tmp/.
