# oc_optctx PLAN (pre-registered BEFORE any outcome statistic is inspected)

Question: do Deribit options skew / put-call taker flow, and the Coinbase-vs-Binance
premium, observed strictly before a dip-rung bar open, separate good from bad dip
fills (beyond what DVOL already explains)?

## Hypothesis (fixed here)

Elevated downside protection demand (high put-vs-call IV skew, high put-buy
share) and US-spot premium/discount at the bar open predict dip-fill outcomes
y1.0 with a year-stable sign. A feature is PROMISING only if its relationship
with y1.0 is sign-consistent across anchor years AND survives regressing out
DVOL level (rule below). Sign direction is read from the data; consistency is
what matters.

## Data (fixed here)

- Deribit options 4h: `data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet`
  (columns bar, call_buy, call_sell, put_buy, put_sell, n_trades, iv_otm_put,
  iv_otm_call). `research/mj/fetch_deribit_options_4h.py` floors each trade's
  timestamp to 4h (`d["bar"] = ts.floor("4h")`), so `bar` is the 4h bar START;
  the row aggregates trades in [bar, bar+4h) and is usable only once its bar
  END (bar+4h) has passed. Only bars with START < 2026-09-24 00:00 UTC are used.
- Coinbase spot 1h: `data/raw/coinbase_20260925/BTC-USD_1h.parquet` (open_time =
  bar START) vs Binance BTCUSDT 1h closes from
  `research/tournament/ext/hourly_ext.parquet` (t = bar START). Only bar STARTs
  < 2026-09-24 00:00 UTC are used.
- Fills: `research/tournament/ext/fills_U_ext.parquet`, majors
  {BTC,ETH,SOL,BNB,XRP} x R2 depths {2.5,3.0,3.5,4.0,5.0} (6876 rows).
  T = t_fill - f minutes (all T on 4h boundaries, minute 0). Outcome = y1.0.
- DVOL z90: `research/tournament/oc_dvol/features_dvol.parquet` column dvol_z90
  (definition in `research/tournament/oc_dvol/PLAN.md`), merged read-only on
  (TT, sym, x1) for the incremental (residual) tests only.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; findings still need prospective validation).
- Track note: docs/opencode/OPENCODE_VF_COMMON.md describes the vf pattern
  track (compute/events over BTC bars). This task is a tournament rung-context
  study with its own battery (below); the VF_COMMON causality spirit (strict
  as-of, causal cut-offs, definitions fixed before results) is honoured, and a
  <=15-line SUMMARY.md is added alongside the assigned REPORT.md + results.json.

## Features (exact, causal — value at T uses ONLY bars with END strictly before T)

As-of rule (same as oc_dvol): a 4h/1h bar is usable at T iff its bar END is
strictly before T (implemented as end <= T - 1s via searchsorted). For the
4h-aligned rung opens T this implies: last usable 4h options bar is [T-8h,T-4h)
(4-8h staleness); last usable hourly bar is [T-2h,T-1h) (1-2h staleness).
Staleness is immaterial for these slow features and required for strict
compliance. Rolling z-windows below EXCLUDE the current value (history only).

Coin mapping: PRIMARY = BTC options features for every major rung; SECONDARY
sensitivity = the same 7 features built from ETH options, evaluated on ETH
rungs only (same battery). No Deribit options exist for SOL/BNB/XRP (BTC is
the market-fear proxy, as in oc_dvol).

Per options coin c in {BTC, ETH}, on its 4h grid (ends e_i = bar+4h):

1. `skew` = iv_otm_put - iv_otm_call at the last usable bar (NaN if either IV
   NaN; ETH has ~0.6%/0.2% IV NaNs, pairwise-dropped, coverage reported).
2. `skew_z90` = (skew - mean(W)) / std(W, ddof=1), W = up to 540 prior skew
   values (90 days, current excluded); require >= 432 non-NaN else NaN;
   std == 0 -> NaN. Unit: standard deviations.
3. `putbuy_share6` = S_put / (S_put + S_call), S_put (S_call) = sum of put_buy
   (call_buy) notional over the last 6 usable 4h bars; denominator 0 -> NaN.
4. `putbuy_share6_z90` = z of putbuy_share6 vs up to 540 prior share6 values,
   same >= 432 / ddof=1 / std==0 rules.
5. `cbprem_last` = cb_close / bin_close - 1 at the last usable hour (BTC only;
   inner join of the two hourly grids on bar START; NaN if either close NaN).
6. `cbprem_mean24` = mean of the hourly premium over the last 24 usable hours;
   require >= 20 of 24 non-NaN else NaN.
7. `cbprem_z90` = z of cbprem_mean24 vs up to 2160 prior mean24 values (90 days
   of hourly samples); require >= 1728 non-NaN else NaN; ddof=1; std==0 -> NaN.

Options history starts 2019-01 (BTC) / 2019-03 (ETH); premium grids start
2017-08 (Coinbase) x 2020-08 (Binance); all 7 features are fully warmed up long
before anchor year 1 (2021-09-24), so no warm-up exclusion is needed.

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T, A in
  {2021-09-24 .. 2025-09-24} (UTC). Primary n expected ~990/1045/1330/989/1144.
- Per anchor year, per feature: Spearman rho(feature, y1.0) over year rows
  (pairwise-complete; NaN if < 30 valid pairs — counts as a FAIL for the sign
  count, never imputed). Report n_valid and coverage.
- Tercile means per year: cut-offs q33/q67 = percentiles of the feature over
  the TRAINING pool = rows with T < A_k AND feature non-NaN (strictly previous
  data only). Require >= 100 training rows else NaN (FAIL). Assignment Lo/Hi/
  Mid; report mean y1.0 (bps) + n per tercile.
- LOYO spread: for held-out year h, training = rows of the other 4 anchor
  years; cut-offs from training; spread_h = mean(y1.0 | Hi) - mean(y1.0 | Lo)
  in the held-out year; require >= 30 rows in EACH of Hi/Lo else NaN (FAIL).
- INCREMENTAL (residual) tests: per anchor year h, OLS feature ~ dvol_z90 on
  that year's pairwise-complete rows (require >= 30 pairs and var(dvol)>0 else
  NaN); residual = feature - fitted; residual IC = Spearman(residual, y1.0);
  residual LOYO spread = tercile spread of the residual with cut-offs from the
  other years' within-year residuals (same >= 30/side rule). Same battery is
  thus run on raw and residual features.
- SECONDARY: the same full battery (raw IC, LOYO spread, residual IC/spread)
  for the 7 ETH-options features on the ETH-rungs subset (BTC-feature IC on
  ETH rungs reported alongside for reference, NOT part of any rule).
- DECISION RULE (from the assignment, per feature, primary universe): PROMISING
  iff (a) sign(raw rho) identical in >= 4/5 anchor years (NaN = fail), AND
  (b) sign(raw LOYO spread) identical in >= 4/5 held-out years (NaN = fail),
  AND (c) sign(residual rho) identical in >= 4/5 anchor years (NaN = fail).
  Residual LOYO spreads are reported descriptively (consistency expected but
  not required). ETH-only results are descriptive, never PROMISING by
  themselves.
- Cost context: y1.0 in bps (1 bps = 1e-4); round-trip cost ~4-8 bps.
- No tuning on results; any post-hoc change logged in REPORT.md. One light
  process, RAM far below the limit (no 1m data loaded).

## Causality / alignment tests (tests/test_oc_optctx.py)

- test_asof_strictly_before_T: sampled rungs; no options/hourly bar used has
  end >= T; truncating all panels to end < T leaves features unchanged.
- test_bar_is_start: all options bars lie on the 4h grid (bar is START).
- test_training_cutoffs_causal: year-1 cut-offs use no row with T >= A_1; LOYO
  cut-offs for a held-out year use no row of that year.
- test_panel_span_and_cutoff: no bar with START >= 2026-09-24 00:00 UTC is
  used; options span from 2019, premium overlap from 2020-08.
- test_universe_counts: majors-R2 join yields 6876 rows, T in
  2020-08-25 .. 2026-09-23, per-year counts 990/1045/1330/989/1144.
- test_dvol_merge: merged dvol_z90 equals oc_dvol's features file on (TT,sym,x1).

## Deliverables

research/tournament/oc_optctx/: PLAN.md (this file), analyze_optctx.py,
features_optctx.parquet, results.json, REPORT.md (tables + one-line verdict per
feature), SUMMARY.md (<= 15 lines). tests/test_oc_optctx.py. No commits.
