# oc_fmbookic — PLAN (pre-registered 2026-10-08/09, BEFORE any outcome)

Diagnostic only. Nothing is selected. Assignment
`docs/opencode/OPENCODE_W_oc_fmbookic.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY
`research/tournament/oc_fmbookic/` + `tests/test_oc_fmbookic.py`.
Light: 4h parquets only, no engine, no GPU. Progress print per (year,h).

## Question
Do Chronos / Toto / TimesFM median forecasts carry BOOK direction information
on the clean year?

## Template (exact)
`research/tournament/oc_kronosfeat/compute_book.py` Table 2 (book part) is the
template; its yardstick starts at the bar open T at which the features are
known — keep that timing. Week-block bootstrap CIs identical (Monday weeks,
B=500). No tuning, no thresholds, no model choice; all settings fixed below
before any IC is computed.

## Inputs (read-only, never edited)
- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (sym, shift, T, open/...; shifts 0..3, 5 majors).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet`
  (sym, shift, T, ch_q10, ch_q50, ch_q90).
- `research/tournament/oc_toto/toto_features_4shift.parquet`
  (sym, shift, T, f_q10, f_q50, f_q90).
- `research/tournament/oc_timesfm/timesfm_features_4shift.parquet`
  (sym, shift, T, f_q10, f_q50, f_q90).
- Deployed book weights = FINAL series of oc_bookichorizon / oc_kronosfeat
  `load_final_weights` (research_books_d2 = 0.8*O1+0.2*CB recomputed read-only
  from `artifacts/research/engine_real/` caches + v421 x0.5 bear filter on
  longs, on books_v154 standard grid = shift-0 grid; never refit).

## Features (6, fixed)
- `ch_q50` = chronos ch_q50; `ch_spr` = ch_q90 - ch_q10.
- `toto_q50` = toto f_q50; `toto_spr` = toto f_q90 - f_q10.
- `tfm_q50` = timesfm f_q50; `tfm_spr` = timesfm f_q90 - f_q10.
No sign flips (medians tested as-is for direction; spreads are dispersion
proxies, tested as-is for both direction and vol channels).

## Years (fixed)
Y0=[2021-09-24,2022-09-24), Y1=[2022-09-24,2023-09-24),
Y2=[2023-09-24,2024-09-24), Y3=[2024-09-24,2025-09-24),
Y4=[2025-09-24,2026-09-24). Labels by decision-bar open T.
Contamination labels (frozen from the three model REPORTs):
Y0..Y3 = dev (Chronos possibly-contaminated; Toto nearly-clean small caveat;
TimesFM possibly-contaminated upper bound); Y4 = CLEAN post-release year for
ALL THREE (after Chronos-Bolt 2024-11, Toto ~May-2025, TimesFM-2.5 Sept-2025
releases and all stated cutoffs).

## Book yardstick (fixed, = template)
- Rows: every (sym, shift, T) with T in [2021-09-24,2026-09-24) and all three
  models' features present (inner join; report coverage + rows per year).
- sigma[t] = std of trailing 360 1-bar simple open-to-open returns ending at t
  on that (sym,shift) grid (min 120; NaN / <=0 dropped). Recomputed from bars
  (never the FM sigma columns).
- Forward fh = open[t+h]/open[t]-1 on the SAME shift grid for h in {1,2,6,18};
  y_h = fh/sigma[t] (NaN dropped; rows whose label needs opens beyond
  2026-09-23 20:00 dropped). Vol target ay_h = |y_h|.

## Tables (fixed)
- Table A (directional): per year x h x feature (6): pooled Spearman(feature,
  y_h) over all (coin,shift,T) rows, n, 95% week-block bootstrap CI (B=500,
  seed (11,y,h,0)); per-coin Spearman (pooled over shifts) with same CI
  (seed (11,y,h,2+coinidx)).
- Table B (vol forecasting): same cells with ay_h as target
  (seeds (11,y,h,1) pooled, (11,y,h,12+coinidx) per coin).
- Table C (novelty vs G2): FINAL deployed weights joined to shift-0 FM rows on
  (sym,T) (grids match exactly; report join rows). Per year x feature (6):
  Spearman(feature, FINAL_weight) pooled + per coin (seed (11,y,99,...)), and
  Spearman(feature, |FINAL_weight|) pooled (magnitude channel).
- Week blocks: weeks starting Monday 00:00 UTC by T; resampling preserves all
  intra-week cross-shift/coin correlation. Significance = CI excludes 0
  (descriptive; no selection).

## Costs / leakage / selection
- No PnL, no fees/funding; book ICs are rank diagnostics with no fills claimed.
- Feature timing: FM row at T uses closes of bars closing <= T (inherited from
  the three frozen parquet builds, truncation-tested there); labels use opens
  > T; sigma uses opens <= t. No fit in this study. No test-year statistic
  feeds any choice; Y4 is reported but never used to choose (nothing chosen).
- Outputs in this folder: results.json + REPORT.md (tables per year, key
  question in bold, 3-line Vietnamese verdict) + tmp/fmbook_tables.json +
  pooled_ic.csv; pytest file tests/test_oc_fmbookic.py (causality/truncation +
  hand-checked synthetic). Scratch only under tmp/.

## Post-hoc log
- (empty; any change after an outcome is logged here with date + reason.)
