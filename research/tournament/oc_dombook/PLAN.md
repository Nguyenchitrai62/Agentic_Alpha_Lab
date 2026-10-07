# oc_dombook — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

Follow-up of `research/tournament/oc_ethbtc`: the deployed BOT book earns
more per bar when BTC dominates the majors (`dom30 > 0`) than when alts
dominate, with a 5/5-sign, LOO-4/5 PROMISING flag on gross vectorised P&L
(but resting on an economically-zero 2021 and with the single LOO miss in
the most recent year). This task walk-forward tests ONE pre-registered
book scaler built on that hypothesis: scale book weights UP (x1.25) when
`dom30` is in its top tercile and DOWN (x0.75) in its bottom tercile,
middle x1.0. If the dominance effect is real and tradeable, the scaled
book should beat the unscaled (but identically vol-targeted) book on net
return in >= 4/5 anchor years without drawing down worse.

## Inputs (read-only, never edited)

- Books: rebuilt EXACTLY as `research/tournament/oc_bookic/compute_bookic.py::
  research_books_d2` (same files, same math: `o1 = 0.5*(A+B)/2 +
  0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index,
  missing -> 0.0) from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  BNB/BTC/ETH/SOL/XRP, from 2017-08).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness dev cutoff; all five anchor years are research
  data, findings still need prospective validation).
- No 1m data. One process, two small 4h frames only (RAM << 1 GB).

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of books index with opens index (dropna all), sorted 4h
  grid, tz-aware UTC. Weight `w_c[t]` is known at the close of bar `t`.
  Bars at exactly 2026-09-24 00:00 UTC or later are excluded (data cutoff).
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. The last
  grid bar has no forward return and is dropped. Same timing as oc_bookic /
  oc_bookvol.
- Regime `dom30[t] = log(O_BTC[t]/O_BTC[t-180]) - mean_s log(O_s[t]/O_s[t-180])`
  over the 5 majors (180 bars = 30 d, 6 bars/day), computed on the FULL
  opens history from 2017-08 with index `<= t` only (causal; NaN until the
  180-bar lag is available). Identical math to oc_ethbtc `dom30`.
- Anchor years (5, assignment-literal): `Y_k = [A_k, A_k + 365 d)` with
  `A_k = 2021-09-24 .. 2025-09-24` (UTC). Leap-year note (as in oc_ethbtc):
  2023-09-24 + 365 d = 2024-09-23, so the six 4h bars of 2024-09-23..24
  belong to no year; they are excluded from per-year AND pooled aggregates
  (count disclosed in results.json).
- Previous-years cut-offs: for year `k`, `lo_k/hi_k` = 33rd/67th percentiles
  of `dom30` over valid (non-NaN) grid bars with `open_time < A_k` (full
  history from 2017, strictly before the anchor; causal). Multiplier at bar
  `t` in year `k`: `m[t] = 1.25` if `dom30[t] > hi_k`, `0.75` if
  `dom30[t] < lo_k`, else `1.0` (boundary ties go mid; NaN regime -> 1.0,
  count disclosed; expected 0 inside scored years).
- Deployed vol scale (same as oc_bookvol BASE, applied to BOTH legs):
  unscaled gross `u[t] = sum_c w_c[t]*r_c[t]`; `sig0[t] = std(u[t-360..t-1],
  ddof=1)*ANN` with `ANN = sqrt(6*365)`, min_periods 120 (window ends at
  `t-1`, strictly before `t`); `s0[t] = min(2, 0.25/sig0[t])`; NaN or
  `sig0 <= 0` -> 1.0.
- Base weights `wb_c[t] = w_c[t]*s0[t]`; scaled weights
  `ws_c[t] = w_c[t]*s0[t]*m[t]`. The vol scale `s0` is IDENTICAL in both
  legs (computed once from the unscaled `u`), so the comparison isolates
  the dominance tilt.
- Turnover (L1, undrifted — disclosed simplification shared with oc_bookvol):
  `TO_base[t] = sum_c |wb_c[t]-wb_c[t-1]|`,
  `TO_scaled[t] = sum_c |ws_c[t]-ws_c[t-1]|`, first grid bar vs flat 0.
  Cost `0.0005 * TO[t]` (0.05% per unit turnover, as assigned).
- Net per-bar P&L: `pn_base[t] = sum_c wb_c[t]*r_c[t] - 0.0005*TO_base[t]`,
  `pn_scaled[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO_scaled[t]`.
- Per (leg, year) on year bars, year-rebased equity from 1.0
  (`eq = cumprod(1+pn)` in grid order): return `= prod(1+pn)-1`; max DD
  `= max(1 - eq/running_peak)` with the peak seeded at 1.0; Sharpe
  `= mean(pn)/std(pn,ddof=1)*ANN` (rf 0; NaN if < 30 bars or std == 0).
  Pooled-5y stats compound the concatenated year bars in grid order
  (orphans excluded) with the same formulas, descriptive only.
- Effects per year: `dRet_y = ret_scaled,y - ret_base,y` (positive = scaled
  earns more); `dDD_y = DD_base,y - DD_scaled,y` (positive = scaled draws
  down less; exact equality within 1e-12 counts as "not worse").
  Sharpe is reported per year/leg descriptively (no gate).

## Decision (verdict) rule — fixed now (assignment default)

- Return leg (default rule): PROMISING-return iff `dRet_y > 0` in `>= 4`
  of the 5 anchor years (NaN or `<= 0` counts as fail) AND leave-one-year-out
  holds in `>= 4` of 5 folds.
- DD leg: scaled is "not worse" in year `y` iff `dDD_y >= -1e-12`. DD gate
  iff not-worse in `>= 4/5` walk-forward years.
- LOO construction (both legs): for held-out year `h`, cuts `lo_h/hi_h` =
  33rd/67th percentiles of `dom30` over the pooled other-4-years'
  year-window bars (valid regime only); multipliers for the held-out year
  use those cuts (middle 1.0, ties mid); the vol scale `s0`, returns and
  turnover stay exactly as in the walk-forward run (no refit). Training
  gate: pooled other-4-years excess `> 0` (return) / mean per-year `dDD`
  over the other 4 `>= -1e-12` (DD); fold HOLDS iff the training gate
  passes AND the held-out year passes the same per-year criterion with
  minimum data (`>= 50` bars per tercile side in the held-out year,
  otherwise the fold fails). Return LOO needs `>= 4/5` holds; DD LOO is
  reported descriptively (not part of the verdict).
- Overall: PROMISING iff return-PROMISING (sign `>= 4/5` AND LOO `>= 4/5`)
  AND the DD gate (`>= 4/5` not-worse) both hold. Anything else =
  NOT PROMISING. First-four-year (2021-2024) counts are reported
  descriptively (repo selection window) but are NOT part of the verdict.

## Causality / coverage tests (tests/test_oc_dombook.py)

- `test_regime_causal`: truncate opens at two cuts; `dom30` at rows `<= cut`
  identical when recomputed on the truncated frame; doubling opens after `t`
  leaves `dom30[t]` unchanged.
- `test_scale_causal`: truncate books+opens at a cut; `s0` and multipliers at
  rows `<= cut` identical on the truncated frame.
- `test_cutoffs_strictly_before_anchor`: per-year `hist_bars` grow
  monotonically; year masks are disjoint and cover every scored bar exactly
  once (orphans disclosed separately); tercile `n` sums to year `n`.
- `test_turnover_cost`: costs `>= 0` everywhere; flat-weight bars cost 0.

## Outputs

`research/tournament/oc_dombook/`: PLAN.md (this file),
`compute_dombook.py`, `results.json`, REPORT.md (tables + one-line verdict).
`tests/test_oc_dombook.py`. One pre-registered scaler only; no tuning on
results; any post-hoc change logged in REPORT.md. No commits.
