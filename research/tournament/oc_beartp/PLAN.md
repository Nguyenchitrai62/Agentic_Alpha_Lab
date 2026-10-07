# oc_beartp PLAN (pre-registered BEFORE any outcome is computed)

Idea #14: bear-regime faster dip take-profit.

## Hypothesis (fixed here)

In bear regimes (BTC below its 200-day 4h-open mean) dip bounces are weaker
and reversals fail more often, so waiting for the deployed per-rung TP
(usually 1.0-1.5 sigma) gives back gains and rides deeper adverse paths.
Taking profit faster (TP 0.5 sigma) on bear-bar rungs only should cut the
daily-sum path drawdown without systematically lowering the yearly sum.
Direction pre-registered: bear bars -> TP 0.5 sigma; non-bear bars unchanged.

## Data (fixed here, all in repo — no fetch, no 1m)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23) via `research/tournament/ext/harness5.py::load`,
  which joins the deployed R2 table
  (`research/parallel/rounds/parallel-20260906-r2/v376/tables_hidden/r2_table_s0.parquet`)
  and builds exact net outcomes `y0.5/y1.0/y1.5` (fees + adverse funding
  inside) plus `y_dep` (net at the deployed per-rung `tp_dep`) and T.
  Universe = majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2
  depths {2.5, 3.0, 3.5, 4.0, 5.0} with `size_dep` non-NaN (harness5 test
  rows; expected 5498 fills, ~990/1045/1330/989/1144 per anchor year).
  T = t_fill - f minutes (all T on 4h boundaries, verified).
- Regime input: `research/tournament/ext/hourly_ext.parquet` hourly OHLC
  (t = bar START UTC), BTCUSDT leg only. No 1m data is loaded (LIGHT job:
  RAM < 1 GB, one process).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation). This is disclosed against RULES.md-2 / VF_COMMON hidden-year
  conventions.

## Exact causal definitions (frozen)

As-of rule: the bear flag for a rung placed at bar open T uses only 4h bar
OPENs with start <= T (the open at T is known at minute 0 when the dip
limit is placed — same timing as v410 / bot/mirror.is_bear).

1. `open4[T]` = open of the BTCUSDT hourly bar with START == T, restricted
   to T on the 4h grid (hour in {0,4,8,12,16,20}, minute 0), t < DEV_END
   (2026-09-24 00:00 UTC), sorted ascending. Source is hourly_ext only.
2. `MA1200[T]` = simple mean of `open4` over the window [T-1199 .. T]
   (up to 1200 bars including T), requiring >= 600 non-NaN bars else NaN
   (exactly v410 / mirror.is_bear: rolling(1200, min_periods=600)).
3. `bear[T]` = True iff `open4[T]` and `MA1200[T]` are both finite and
   `open4[T] < MA1200[T]` (strict); NaN MA -> False (non-bear). One value
   per 4h bar T, applied to all 5 coins' rungs filling from bids placed at T.
4. `tp_new` = 0.5 where `bear[T]` is True, else `tp_dep` (deployed per-rung
   TP from harness5.load). `y_new` = `y0.5` where `bear[T]`, else `y_dep`.
   Sizes are held fixed at `size_dep` (pure take-profit decision, scored
   like `harness5.score_tp` with sizes fixed).
5. Zero fitted parameters: no thresholds, cut-offs, or normalisation are
   estimated. Sequential scoring and leave-one-year-out scoring coincide
   (the rule is identical in every fold); LOYO sign-stability is reported
   descriptively (same fixed rule, no refit).

Anchor years: Y_k = [A_k, A_k + 365d) by T, A in
{2021-09-24 .. 2025-09-24} UTC.

## Evaluation (fixed here — one variant only)

Per anchor year k, over the harness5 test rows in Y_k:

- `n` = test rung count; `n_bear` = test rungs with bear[T] True;
  `bear_share` = n_bear / n; `changed` = fraction with tp_new != tp_dep.
- Sums (native size*y_dep units, costs already inside y):
  `S_dep = sum(size_dep * y_dep)`, `S_new = sum(size_dep * y_new)`;
  `gain = S_new - S_dep`. PASS_sum(Y): S_new >= S_dep - 1e-9.
- Win rate (unweighted, rung-level): `win_dep = mean(y_dep > 0)`,
  `win_new = mean(y_new > 0)` over test rungs (descriptive, not in rule);
  bear-only win rates reported descriptively.
- Worst day: daily sums of size*y grouped by floor(T) calendar day UTC;
  `W_dep = min`, `W_new = min` (descriptive, not in rule).
- Path maxDD (absolute, native units): sort distinct days ascending, daily
  sums d_1..d_m, cumulative path c_0 = 0, c_i = sum(d_1..d_i);
  running peak p_i = max(c_0..c_i); `DD = max_i(p_i - c_i)` (>= 0).
  Computed separately for the deployed daily sums (DD_dep) and the rule
  daily sums (DD_new). PASS_dd(Y): DD_new <= DD_dep + 1e-9 (not worse).
- DECISION RULE (assignment-specific, frozen): PROMISING iff
  (a) PASS_dd in >= 4 of 5 years, AND (b) PASS_sum in >= 3 of 5 years.
  Otherwise NOT PROMISING. NaN/degenerate year counts as a miss.
- Descriptive only (NOT part of the rule): S in bps x1e4 for scale;
  per-year W_dep/W_new; win rates; bear_share; changed share; mean
  (y0.5 - y_dep) on bear rungs; harness5.score_tp graduation row.

## Causality / accounting tests (tests/test_oc_beartp.py)

- test_bear_causal_truncate: 5 sampled T; bear[T] recomputed from the 4h
  opens truncated to start <= T equals the stored value; no retained open
  has start > T.
- test_tp_mapping: synthetic bear flags map tp_new/y_new exactly
  (bear -> 0.5/y0.5, non-bear -> tp_dep/y_dep), incl. NaN-MA -> non-bear.
- test_decision_counts_match: results.json pass counts recomputed from
  yearly passes equal the stored decision strings.
- test_score_tp_match: stored per-year S_dep/S_new/gain equal an
  independent harness5.score_tp recomputation with the stored tp_new.
- test_T_and_bounds: T = t_fill - f; no test T >= 2026-09-24; no hourly bar
  with START >= 2026-09-24 00:00 UTC used; all test T on the 4h grid.
- test_universe_counts: majors-R2 join yields 5498 rows with
  990/1045/1330/989/1144 rows per anchor year.

## Deliverables

research/tournament/oc_beartp/: PLAN.md (this file),
analyze_beartp.py, results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_beartp.py. No commits, no edits outside these two paths.
One process, hourly data only, RAM < 1 GB.
