# oc_depthregime PLAN (pre-registered BEFORE computing any outcome, 2026-10-06)

DIAGNOSTIC only. No selection, no PROMISING rule, no verdict on strategy
quality. Question from the assignment: oc_contrib found the 4.0 / 5.0 sigma
dip rungs lose money in every anchor year for R2B1D17BF — do deep rungs lose
in ALL regimes, or is there a regime known at the bar open where they pay
(e.g. n = 0 idiosyncratic flushes) that a conditional rule could keep?

## Inputs (fixed, read-only)

- `research/tournament/oc_kpi/events_s{0..3}.parquet` (R2B1D17BF engine
  replicas, 4 phase sub-accounts, live 2021-09-24..2026-09-23+shift).
  Only rows with kind in {rung_fill, rung_sl, rung_tp, rung_timeout} are used.
- `research/tournament/ext/hourly_ext.parquet` (hourly OHLC, t = bar START
  UTC, 35 coins, 2020-08-01..2026-09-23) — majors legs only
  (BTC/ETH/SOL/BNB/XRPUSDT). No 1m data is read (LIGHT job).
- `research/tournament/oc_contrib/results.json` (reference: pooled 21389 dip
  rungs, depth mix% per year; used only as a cross-check, not as input).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; findings need prospective validation).
- Pre-PLAN inspection was schema-only (events kinds/columns, hourly columns,
  oc_contrib depth table); no regime-split outcome was computed before this PLAN.

## Rung pairing (fixed, copy of oc_contrib/oc_kpi)

FIFO per symbol over `t`-sorted events: `rung_fill` -> first later
`rung_sl|rung_tp|rung_timeout`. Each pair gives `fill_t, exit_t, symbol,
depth=float(fill.rung), exit=exit kind, weight=float(exit.weight),
ret=float(exit.ret)`, `pnl = weight*ret` (fraction of sub-account bar-start
equity; engine `ret` is already net of rung maker/taker fees and timeout
funding), `gross = weight`, `win = ret > 0`. Unpaired exits counted as a
check (expected 0). Year bucket = FILL time in anchor year
`[A_k, A_k+365d)`, A=(2021..2025)-09-24, end 2026-09-24 (same as oc_kpi).
Pooled over the 4 phase sub-accounts (counts summed; win rates pooled).
Depth group: `deep` = depth in {4.0, 5.0}, `shallow` = depth in
{2.5, 3.0, 3.5}.

## Regime definitions (fixed, all causal: known at the bar open)

Let `fill_t` be the rung fill time. `T0` = floor of `fill_t` to the STANDARD
4h grid (00/04/08/12/16/20 UTC, minute 0). `T0 <= fill_t < T0+4h`; the resting
bid was placed at or before `T0+` (fills occur minutes after the bar open in
this engine), so any quantity using only data with time <= `T0` is known at
the bar open. All 4h series below are built from hourly_ext only:

- `open4_c[T]` = `open` of the hourly bar of coin c with START == T, for T on
  the standard 4h grid, t < 2026-09-24 00:00 UTC, sorted ascending.
  (One value per 4h bar per coin; the open at T is known at minute 0 of bar T.)
- `sigma4_c[T]` = sample std (ddof=1) of simple 4h-open returns
  `o[T]/o[prev]-1` over the trailing 360 returns ending at T
  (`rolling(360, min_periods=120)` on `pct_change()`), evaluated at T.
  Uses opens <= T only (same formula family as v399/oc_manual3/oc_b1shape).
  NaN until 120 bar returns exist.

Regimes per fill (applied to the fill's `T0` / `fill_t`):

1. `bear` (v410 exact): `MA1200[T0]` = mean of BTC `open4` over
   `[T0-1199 .. T0]` (`rolling(1200, min_periods=600)`); `bear` iff both
   finite and `open4_BTC[T0] < MA1200[T0]` (strict); NaN MA -> `bull`
   (non-bear, exactly as v410/mirror.is_bear). Values: {bear, bull}.
2. `btc30` (BTC 30-day return sign): `r30 = open4_BTC[T0]/open4_BTC[T0-180]-1`
   (180 4h bars = 30 days, both <= T0). `up` iff finite and `r30 > 0`, else
   `down` iff finite (zero counts as down); NaN -> `unknown` (counted;
   expected 0 — history starts 2020-08-01). Values: {up, down[, unknown]}.
3. `sigma_terc` (walk-forward, per coin): for anchor year Y with anchor A,
   cutoffs `p33, p66` = 33rd/66th percentiles of that coin's `sigma4` values
   on the 4h grid with `T < A - 7 days` (fill-time embargo convention; grid
   history from 2020-08-01). Cutoffs are fixed per (year, coin) before the
   year starts. Fill labelled `low` iff `sigma4_c[T0] <= p33`, `high` iff
   `> p66`, else `mid`; NaN sigma -> `unknown` (counted; expected 0).
   Values: {low, mid, high[, unknown]}.
4. `n_evt` (event-based proxy for B1 n; NO 1m read per LIGHT): distinct other
   majors `b != sym` in the SAME phase shift (same sub-account) with >= 1
   `rung_fill` (any depth) with `fill_t - 60min <= t_b <= fill_t`. Counts
   0..4. Bucketed {n0, n1, n2p} (n2p = 2+). Causal note: uses only rung_fill
   event times <= fill_t (same-minute ties included and disclosed; exact 1m-based
   `C<=O*(1-2.5*sig)` B1 n is NOT recomputed — that needs 1m, forbidden by
   the LIGHT rule; this proxy measures "other majors filling about the same
   time", i.e. joint-flush breadth as seen by the engine).
   Post-PLAN fix (logged 2026-10-06, before REPORT): first implementation
   counted fills pooled over all 4 shifts, which put every fill in n2p (no
   variation); corrected to same-shift counts. No outcome was kept from the
   pooled version except the degenerate n histogram that motivated the fix.
5. `hour` (hour-of-day bucket of `fill_t`, UTC): {h00_05, h06_11, h12_17,
   h18_23} from `fill_t.hour`. Known at the fill.
6. `exit` (exit kind, NOT a pre-trade regime — reported as the realised
   split, same as oc_contrib): {rung_tp, rung_sl, rung_timeout}.

## Evaluation (fixed here)

Per anchor year k (0..4) and pooled, per regime dimension d above, per
(depth_group g in {deep, shallow}) x (regime value v): `n` = rung count,
`pnl_sub` = sum(pnl) (sub-account equity fraction), `pnl_mix_pct` =
`pnl_sub/4*100` (% of mix equity, additive approximation as in oc_contrib),
`win` = mean(ret > 0), `pnl_per_gross` = sum(pnl)/sum(gross).
Also per year: deep total and shallow total (sum over regime values), and the
replication check vs oc_contrib depth mix% (tolerance: exact match to the
rounded 2-decimal mix% after the same pairing/weight convention).
Descriptive question (NOT a rule): for each regime value v, in how many of
the 5 years is deep `pnl_mix_pct` >= 0? A value with deep >= 0 in >= 4/5
years would be flagged descriptively as "the only regime where deep pays"
(if any); a value with deep < 0 in all 5 years is "loses everywhere".
No PROMISING/REJECT label, no threshold is fit, no parameter is chosen.

## Causality / accounting tests (tests/test_oc_depthregime.py)

- test_pairing_math: synthetic fills/exits pair FIFO with pnl = w*ret.
- test_year_boundaries: year_of() maps anchor edges exactly.
- test_regime_causal_truncate: 5 sampled T0; bear/btc30/sigma recomputed from
  hourly truncated to START <= T0 equal stored values; no retained bar has
  START > T0.
- test_tercile_walkforward: stored cutoffs equal percentiles of the
  pre-anchor-minus-7d sigma history; a fill's bucket matches its sigma vs
  its year's cutoffs.
- test_nevt_causal: synthetic fills -> n_evt counts distinct other majors in
  [t-60min, t] only (future fills excluded, own coin excluded, 60min+old
  excluded).
- test_consistency: per-dimension per-year n sums to the year's deep/shallow
  totals; pooled = sum of years; depth-group pooled n = 21389 split as in
  oc_contrib; exit win rates are 1.0/0.0 for tp/sl.
- test_plan_predates_results + files present.

## Resources

LIGHT: one process, RAM < 1 GB (events ~80k rows + 5-coin 4h opens ~13k
bars/coin as float64), no 1m data, runtime < 10 min.

## Outputs (fixed)

- `research/tournament/oc_depthregime/PLAN.md` (this file),
  `analyze_depthregime.py` (single script), `results.json` (all tables +
  cutoffs + checks + methods note), `REPORT.md` (tables + one plain paragraph
  + one-line descriptive verdict; no selection).
- Test `tests/test_oc_depthregime.py`. No commits, no edits outside these two
  paths.
