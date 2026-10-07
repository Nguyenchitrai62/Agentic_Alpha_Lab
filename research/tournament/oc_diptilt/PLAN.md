# oc_diptilt PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #39: regime-tilted dip size. Written and frozen before any tilt P&L,
equity proxy, or year table is computed. One fixed MAIN variant + one
fixed sensitivity pair (NOT for selection). No engine run here; a PROMISING
proxy only asks the leader to run a registered engine version.

## Hypothesis (fixed here)

oc_regimetrue (TRUE per-rung pairs of R2B1D17BF) shows every depth earns in
both bear/bull bars, bull cells more. Pre-registered direction: scaling dip
rung size UP in bull bars and DOWN in bear bars raises the dip-sleeve proxy
return without worsening the proxy drawdown. Fixed rule — ONE MAIN variant:

- `m = 1.2` in bull bars, `m = 0.8` in bear bars (dip rung notional scale).
- Bear flag = v410 exact: BTC 4h open < 1200-bar mean, causal at the bar open
  (definition below). No fitting, no threshold choice, no lookahead.

Sensitivity (fixed here, NOT for selection, reported only): `1.1 / 0.9`
with the same flag.

## Data (fixed here, read-only, all in repo)

- `research/tournament/oc_kpi/events_s{0..3}.parquet` (R2B1D17BF engine
  replicas, 4 phase sub-accounts, live 2021-09-24..2026-09-23+shift).
  Read IN PARQUET/APPEND ORDER (NOT time-sorted) — TRUE pairing needs it.
  Only rows with kind in {rung_fill, rung_sl, rung_tp, rung_timeout} used.
- `research/tournament/ext/hourly_ext.parquet` (hourly OHLC, t = bar START
  UTC, 35 coins, 2020-08-01..2026-09-23) — BTC column only, for the bear flag.
  No 1m data is read (LIGHT job).
- `research/tournament/oc_regimetrue/results.json` + `research/diagnostics/
  oc_deepcheck/results.json` — replication cross-check of base totals only.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation). No refit, no selection, no tuning. One process, RAM < 1 GB.

## Exact causal definitions (frozen)

1. TRUE pairing (exact copy of
   `research/diagnostics/oc_deepcheck/analyze_deepcheck.py::pair_true`):
   positional adjacency in the engine's append order — every `rung_fill` row
   is immediately followed by its own exit row (`rung_sl` | `rung_tp` |
   `rung_timeout`) with the same symbol (weight equality recorded as a
   check; violations counted, expected 0). Each pair gives `fill_t, exit_t,
   symbol, depth=float(fill.rung), exit kind, weight=float(exit.weight),
   ret=float(exit.ret)`, `pnl = weight*ret` (fraction of sub-account
   bar-start equity; engine `ret` is already net of rung maker/taker fees
   and timeout funding), `win = ret > 0` (unchanged by positive scaling).
2. `T0` = floor of `fill_t` to the STANDARD 4h grid (00/04/08/12/16/20 UTC,
   minute 0). `T0 <= fill_t < T0+4h`. (s=1..3 replicas run on shifted grids;
   T0 still satisfies T0 <= bar open <= fill_t, so still causal.)
3. BTC 4h opens from hourly_ext only: `open4[T]` = `open` of the hourly bar
   with START == T, T on the standard 4h grid, T < 2026-09-24 00:00 UTC,
   sorted ascending. `MA1200[T0]` = mean of `open4` over `[T0-1199 .. T0]`
   (`rolling(1200, min_periods=600)`); `bear` iff both finite and
   `open4[T0] < MA1200[T0]` (strict), else `bull` (NaN MA -> `bull`,
   exactly as v410/v410_bear_book.py:68). The multiplier of a rung is a
   function of T0 only — known at the bar open, before the fill.
4. Multipliers: MAIN `m = 0.8` if bear else `1.2`; SENS `m = 0.9` if bear
   else `1.1`. `pnl_tilt = pnl * m`, `pnl_sens = pnl * m_sens`.
5. Year bucket = FILL time in anchor year `[A_k, A_k+365d)`,
   A=(2021..2025)-09-24 UTC, end 2026-09-24 (oc_contrib/oc_regimetrue
   convention). Pooled over the 4 phase sub-accounts.
6. Equity proxy (additive, DOCUMENTED APPROXIMATION): per shift s and year k,
   take that shift's rungs with fill in year k, sort by `exit_t`, build
   `eq = 1 + cumsum(pnl_scaled)` starting at 1.0 at the anchor (base uses
   `pnl`, tilt uses `pnl_tilt`, sens uses `pnl_sens`). Mix path per year via
   time-union: at each distinct exit time across the 4 shifts (sorted),
   `eq_mix(t) = mean_s eq_s(t)` with each `eq_s` forward-filled (1.0 before
   its first exit) — i.e. 1/4 capital each, reset to 1.0 at every anchor
   (the reset_metric idea). APPROXIMATION (stated in REPORT too): additive
   (no compounding inside the year), no budget/notional interaction (a
   bigger rung does not change admission or margin of other rungs), no book
   leg (dip sleeve only), exit-time ordering inside the fill year (dip rungs
   exit inside the same 4h holding bar, so fill-year ~= exit-year up to
   boundary bars).
7. Per-year metrics from the mix path: `eq_end` (last point),
   `R_proxy = eq_end^(1/12)-1` (%/month, x100), `DD_proxy = max(1-eq/pk(eq))`
   (x100, running peak includes the starting 1.0). Base, tilt, and sens
   each get (eq_end, R, DD) per year + pooled-5y additive mix% context.

## Evaluation (fixed here — MAIN variant only for selection)

- Per year k: `PASS_ret(k)`: `R_tilt(k) > R_base(k)` (strict).
- Per year k: `PASS_dd(k)`: `DD_tilt(k) <= DD_base(k)` (strictly not worse;
  equal passes).
- DECISION RULE (the assignment's idea-specific rule, supersedes the
  default spread/LOYO rule): PROMISING iff (a) PASS_ret in >= 4 of 5 anchor
  years AND (b) PASS_dd in >= 4 of 5 anchor years. Otherwise NOT PROMISING.
  On PROMISING the leader runs a registered engine version (no engine claim
  is made here). The x1.1/x0.9 sensitivity is reported with the same two
  counts but NEVER enters the rule. No other statistic (pooled, win rate,
  per-depth, per-regime) enters the rule.

## Causality / accounting tests (tests/test_oc_diptilt.py)

- test_true_pairing_math: synthetic append-ordered fills/exits pair
  positionally with pnl = w*ret; violations counted on mismatch.
- test_year_boundaries: year_of() maps anchor edges exactly.
- test_bear_causal_truncate: 5 sampled T0; bear recomputed from hourly
  truncated to START <= T0 equals stored values; MA window holds <= 1200
  bars ending exactly at T0.
- test_multiplier_mapping: bear->0.8/bull->1.2 (sens 0.9/1.1); win unchanged.
- test_additive_mix_math: synthetic per-shift cumsums + time-union mean mix
  equal hand values; R/DD formulas match; base end equals pooled additive
  mix%.
- test_consistency: results.json base yearly/pooled mix% replicates
  oc_regimetrue totals (tolerance 0.002); tilt == bull*1.2+bear*0.8 per year;
  PASS counts recomputed from stored tables equal the verdict flags;
  PROMISING matches the AND rule; PLAN.md mtime < results.json mtime.
- test_plan_predates_results + files present.

## Outputs (fixed)

- `research/tournament/oc_diptilt/PLAN.md` (this file),
  `analyze_diptilt.py` (single script), `results.json` (year tables base /
  tilt / sens + bull/bear split + checks + methods note), `REPORT.md`
  (tables + one plain paragraph + one-line PROMISING/NOT PROMISING verdict).
- Test `tests/test_oc_diptilt.py`. No commits, no edits outside these two
  paths.
