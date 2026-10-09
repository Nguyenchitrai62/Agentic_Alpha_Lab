# oc_horizonfix PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Suspicion (leader assignment)

`oc_presampleshort` and `oc_bookichorizon` scored predictions against
`y = (open[t+h]/open[t]-1)/sigma[t]`. If the prediction row indexed `t`
was computed from features that include bar `t`'s CLOSE, then
`open[t] -> open[t+1]` is bar `t`'s own move, already known to the
features: a contemporaneous leak in the YARDSTICK (not in any strategy).

## Pre-registered timing audit (Task 1, code-only, no outcomes)

- (a) `preds_*.csv` of `oc_presamplebook` / `oc_presampleflow`:
  read `presamplebook.py` (`build_spot_4h`, `tv_features` import, `add_label`,
  test-row selection) and `presampleflow.py` (same + `flow_features`,
  `add_cb`); cite exact lines proving: `open_time` = bar OPEN timestamp,
  features at row `t` use bars `0..t` including `close[t]`
  (`tv_indicators.py` docstring, `v236/flow_features.py` docstring,
  `v111_coinbase_premium.py` docstring), label `fwd = log(o[t+1+H]/o[t+1])`
  and `r_next = o[t+2]/o[t+1]-1`. Conclusion fixed here:
  prediction at `T` becomes available at `T+4h` (close of bar `T`).
- (b) member caches / blended book rows used by `oc_bookichorizon`:
  read `scripts/forward_v205.py::research_books_d2` (reindex/fillna blend),
  `engine_real.py::v154_books`, `v144_deploy_v3.py::books_v142`
  (`r_next = o.shift(-2)/o.shift(-1)-1`, `books.shift(2)` execution),
  `v103_flow_short_horizon.py::build` (`x["t"] = b["open_time"]`,
  features from bars closed at `t`, labels from `o[t+1]`).
  Conclusion fixed here: cached row at `T` is the decision known at the
  close of the bar opening at `T`; executable base is `open[T+4h]`.

## Pre-registered corrected yardstick (Task 2, fixed here)

- Availability moment of a row indexed `T` (bar-open timestamp) =
  `T + 4h` (close of bar `T`).
- `t_trade` = first bar open at/after availability = `T + 4h`.
- Corrected target, per (coin, row `T`, horizon `h` in 4h bars):
  `y_corr[T,h] = (open[t_trade+h]/open[t_trade]-1) / sigma[t_trade]`,
  where `sigma[S] = std(r1[k] for k in S-359..S)`, `r1[k]=open[k]/open[k-1]-1`,
  pandas std ddof=1, min_periods=120, else NaN (identical math to old code,
  only the anchor shifts by +1 bar). Rows with `sigma<=0/NaN` or missing
  `open[t_trade+h]` are dropped for that `h` (same drop rule as old).
- Old target (reproduced verbatim for side-by-side):
  `y_old[T,h] = (open[T+h]/open[T]-1) / sigma[T]`.
- Histories, test sets, sigma math, horizons `{1,2,6,18,42}`, metrics
  (pooled Spearman IC, per-coin IC, TS mean = mean of per-coin ICs,
  XS mean across coins per bar), years (presample 7 anchors incl.
  2019/2020 + book 5 years 2021-2025) are otherwise IDENTICAL to the two
  original studies. Bootstrap CIs are NOT recomputed (point ICs only;
  old CIs quoted from the published `results.json` for reference).
- Series rescored: presample TV/FLOW/PREMIUM/BLEND (4 coins) and
  book A/Aq/B/Bq/D/Dq/O1/CB/FULL/FINAL (5 coins). No refits, no new
  thresholds, no tuning.

## Pre-registered synthetic proof (Task 3, fixed here)

- Synthetic 4h opens: 3000 bars, `r1 ~ N(0, 0.01)` iid, seed 0.
- Feature `f[T] = r1[T]` (current bar's return, known at close of bar `T`).
- Old IC(`f[T]`, `y_old[T,1]`) must be strongly positive (~+1 rank, since
  `y_old[T,1] = r1[T+1... wait: open[T+1]/open[T]-1 = r1[T+1-index?]` — exact
  statement in test: old target's first-bar component equals the feature's
  bar; corrected target `y_corr[T,1] = open[T+5h]/open[T+4h]-1` is
  independent of `f[T]`, so corrected IC must be ~0 (|IC|<0.1).
  Detail: with open-indexed series, `y_old[T,1] = open[T+1]/open[T]-1`
  is the return of the bar OPENING at T, i.e. bar T's own move, which is
  a deterministic function of information available at close[T]
  (open[T+1] is close[T] up to the 4h sampling); the test asserts
  old IC > 0.5 and corrected |IC| < 0.1 on the synthetic seed.
- Second synthetic: `f[T] = r1[T+1]` (next bar's return, genuinely
  predictive one bar ahead): corrected IC at h=1 must be strongly
  positive (>0.5), proving the corrected yardstick still detects real
  one-bar-ahead skill and is not a null machine.

## Deliverables (fixed)

- `research/tournament/oc_horizonfix/`: PLAN.md (this file),
  `audit_timing.py` (prints cited lines + timestamp conclusions),
  `recompute.py` (old-vs-corrected point-IC tables from read-only inputs),
  `results.json` (old + corrected pooled/TS/XS per series/year/h + meta),
  `REPORT.md` (timing verdict, side-by-side tables, Vietnamese verdict),
  `tmp/` scratch only.
- Test `tests/test_oc_horizonfix.py` (>=1 causality/truncation test +
  >=1 hand-checked synthetic case incl. the inflation proof), run with
  `.venv/Scripts/python.exe -m pytest tests/test_oc_horizonfix.py -q`.
- Write ONLY `research/tournament/oc_horizonfix/` + that test file.
  No commits. No selection, no deployment change. Light job (4h only).

## Post-hoc log

- 2026-10-07 (before REPORT, after seeing recompute outcomes; definition
  unchanged): synthetic feature clarified from `f[T]=r1[T]` to the
  close-based bar return `close[T]/open[T]-1` (with exact 4h sampling
  `close[T]==open[T+1]` this equals the old h=1 numerator). An open-to-open
  `open[T]/open[T-1]-1` would not inflate; the leak is via `close[T]`.
  Test thresholds met as pre-registered (old 0.9998>0.5, corrected
  |.|=0.002<0.1, true-skill 0.9998>0.5).
