# oc_regimetrue PLAN (pre-registered BEFORE computing any outcome, 2026-10-06)

DIAGNOSTIC only. No selection, no PROMISING rule, no verdict on strategy
quality. Assignment: oc_deepcheck proved FIFO re-pairing of rung fills and
exits misattributes P&L between depths (TRUE pairs: deep rungs really earn
in every year). Redo the regime x depth table with TRUE per-rung pairs.

Question (fixed): with TRUE pairs, is there a regime known at (or before)
the fill where some depth loses persistently (conditional-rule candidates),
or where every depth wins in all 5 years?

## Inputs (fixed, read-only)

- `research/tournament/oc_kpi/events_s{0..3}.parquet` (R2B1D17BF engine
  replicas, 4 phase sub-accounts, live 2021-09-24..2026-09-23+shift).
  Only rows with kind in {rung_fill, rung_sl, rung_tp, rung_timeout} used.
- `research/tournament/ext/hourly_ext.parquet` (hourly OHLC, t = bar START
  UTC, 35 coins, 2020-08-01..2026-09-23) — majors legs only
  (BTC/ETH/SOL/BNB/XRPUSDT). No 1m data is read (LIGHT job).
- `research/tournament/oc_manual3/n_per_fill.parquet` (exact v399 B1 n per
  grid fill; s0 cross-check only, no 1m read).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; findings need prospective validation).
- Pre-PLAN inspection was schema-only (events kinds/columns, hourly columns,
  v410 bear lines, n_per_fill columns, s0 join-key overlap counts
  5437/5466). No regime-split P&L was computed before this PLAN.

## Rung pairing (fixed, exact copy of oc_deepcheck pair_true)

Positional adjacency in the engine's append order: every `rung_fill` row is
immediately followed by its own exit row (`rung_sl` | `rung_tp` |
`rung_timeout`) with the same symbol (weight equality recorded as a check).
The parquet preserves append order (NOT time-sorted). Each pair gives
`fill_t, exit_t, symbol, depth=float(fill.rung), exit=exit kind,
weight=float(exit.weight), ret=float(exit.ret)`,
`pnl = weight*ret` (fraction of sub-account bar-start equity; engine `ret`
is already net of rung maker/taker fees and timeout funding),
`win = ret > 0`. Adjacency violations counted (expected 0, as in
oc_deepcheck). Year bucket = FILL time in anchor year `[A_k, A_k+365d)`,
A=(2021..2025)-09-24, end 2026-09-24 (oc_contrib convention). Pooled over
the 4 phase sub-accounts (counts summed; win rates pooled; pnl_mix =
pnl_sub/4*100 additive, as in oc_deepcheck/oc_contrib).

## Regime definitions (fixed, all causal)

Let `fill_t` be the rung fill time. `T0` = floor of `fill_t` to the STANDARD
4h grid (00/04/08/12/16/20 UTC, minute 0). `T0 <= fill_t < T0+4h`. All 4h
series are built from hourly_ext only:

- `open4_c[T]` = `open` of the hourly bar of coin c with START == T, for T on
  the standard 4h grid, t < 2026-09-24 00:00 UTC, sorted ascending.
  (The open at T is known at minute 0 of bar T.)
- `sigma4_c[T]` = sample std (ddof=1) of simple 4h-open returns
  `o[T]/o[prev]-1` over the trailing 360 returns ending at T
  (`rolling(360, min_periods=120)` on `pct_change()`), evaluated at T.
  Uses opens <= T only (same formula family as
  v399/oc_manual3/oc_b1shape/oc_depthregime). NaN until 120 returns exist.

Regimes per fill:

1. `bear` (v410 exact, copy of oc_depthregime): `MA1200[T0]` = mean of BTC
   `open4` over `[T0-1199 .. T0]` (`rolling(1200, min_periods=600)`);
   `bear` iff both finite and `open4_BTC[T0] < MA1200[T0]` (strict);
   NaN MA -> `bull` (exactly as v410/v410_bear_book.py:68 —
   `btc < btc.rolling(1200, min_periods=600).mean()` on 4h opens).
   Values: {bear, bull}. Known at the bar open (uses opens <= T0).
2. `sigma_terc` (walk-forward, per coin; copy of oc_depthregime): for anchor
   year Y with anchor A, cutoffs `p33, p66` = 33rd/66th percentiles of that
   coin's `sigma4` values on the 4h grid with `T < A - 7 days` (fill-time
   embargo convention; grid history from 2020-08-01). Cutoffs fixed per
   (year, coin) before the year starts. Fill labelled `low` iff
   `sigma4_c[T0] <= p33`, `high` iff `> p66`, else `mid`; NaN sigma ->
   `unknown` (counted; expected 0). Values: {low, mid, high[, unknown]}.
   Known at the bar open.
3. `n` B1 breadth at the fill (0/1/2+, bucketed {n0, n1, n2p} with
   n2p = 2+). PRIMARY (all 4 shifts, uniform): same-shift event-based
   breadth, exact copy of oc_depthregime's corrected `n_evt`: distinct other
   majors `b != sym` in the SAME phase shift (same sub-account) with >= 1
   `rung_fill` (any depth) with `fill_t - 60min <= t_b <= fill_t`. Causal
   (uses only rung_fill event times <= fill_t). This is a co-fill proxy:
   the exact 1m B1 count (`C[f-1] <= O[0]*(1-2.5*sig4)` per
   v410_bear_book.py:83-90) is NOT recomputed — no 1m read per LIGHT.
   SECONDARY (s0 only, labelled `n_exact`): stored exact v399 n from
   `n_per_fill.parquet` joined on `(sym, t_fill, depth)`; s0-only because
   that file lives on the standard grid (pre-PLAN schema check: s0 overlap
   5437/5466 = 99.5%; s1..s3 fills sit on shifted grids and do not join).
   Non-joined fills -> `unknown` (counted). The s0 exact-n table validates
   whether the proxy and the exact count tell the same story.

## Evaluation (fixed here)

Per anchor year k (0..4, fill year) and pooled, per depth
d in {2.5, 3.0, 3.5, 4.0, 5.0}, per regime dimension
(bear {bear,bull}, sigma_terc {low,mid,high}, n {n0,n1,n2p}):
`n` = rung count, `pnl_sub` = sum(pnl) (sub-account equity fraction),
`pnl_mix_pct` = `pnl_sub/4*100` (% of mix equity, additive approximation),
`win` = mean(ret > 0). Plus per depth per year totals (sum over regime
values) and the replication check vs oc_deepcheck TRUE per-depth tables
(tolerance: exact match of pooled/yearly depth mix% to 2 decimals).
Secondary: s0-only depth x n_exact x year table (same metrics).
Descriptive flags (NOT a selection rule, fixed here): for each
(depth, dimension, value) cell, count years with `pnl_mix_pct >= 0`;
flag `lose_ge4` = negative in >= 4/5 years (conditional-rule candidates)
and `win_5` = non-negative in 5/5 years. No PROMISING/REJECT label, no
threshold is fit, no parameter is chosen.

## Decision rule

DIAGNOSTIC (no rule): the assignment's default PROMISING rule does not
apply (same as oc_depthregime/oc_deepcheck). REPORT.md ends with a
descriptive one-line verdict only.

## Causality / accounting tests (tests/test_oc_regimetrue.py)

- test_true_pairing_math: synthetic append-ordered fills/exits pair
  positionally with pnl = w*ret; violations counted on mismatch.
- test_year_boundaries: year_of() maps anchor edges exactly.
- test_regime_causal_truncate: 5 sampled T0; bear/sigma recomputed from
  hourly truncated to START <= T0 equal stored values; no retained bar has
  START > T0.
- test_tercile_walkforward: stored cutoffs equal percentiles of the
  pre-anchor-minus-7d sigma history; a fill's bucket matches its sigma vs
  its year's cutoffs.
- test_n_causal: synthetic fills -> n counts distinct other majors in
  [t-60min, t] same shift only (future excluded, own coin excluded,
  other-shift excluded, 60min+old excluded).
- test_consistency: per-dimension per-year n sums to the year's depth
  totals; pooled = sum of years; pooled depth n sums to 21389 with the
  oc_deepcheck depth split; replication of oc_deepcheck TRUE depth mix%.
- test_plan_predates_results + files present.

## Resources

LIGHT: one process, RAM < 1 GB (events ~85k rows + 5-coin 4h opens ~13k
bars/coin as float64), no 1m data, runtime < 15 min.

## Outputs (fixed)

- `research/tournament/oc_regimetrue/PLAN.md` (this file),
  `analyze_regimetrue.py` (single script), `results.json` (all tables +
  cutoffs + checks + methods note), `REPORT.md` (tables + one plain
  paragraph + one-line descriptive verdict; no selection).
- Test `tests/test_oc_regimetrue.py`. No commits, no edits outside these two
  paths.
