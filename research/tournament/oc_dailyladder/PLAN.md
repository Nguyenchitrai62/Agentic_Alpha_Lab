# oc_dailyladder PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Idea #21: a DAILY-timeframe dip ladder as a second, slower sleeve (the hourly
ladder failed 3x as faster noise; the slower direction is untested).
Written before any fill, return, correlation or drawdown is computed.

## Hypothesis (fixed here)

Daily dips (1.5-2.5 daily-sigma below the UTC day open) mean-revert to
+1.0 sigma within 3 days often enough that a fixed daily rung ladder is
(a) net positive on its own in most years, (b) diversifying vs the 4h BOT
dip stream (correlation < 0.5), and (c) does not worsen drawdown when
added at half weight. Tradable use if PROMISING: run it as a second,
slower sleeve beside the 4h ladder.

## Data (fixed here)

- `research/tournament/ext/hourly_ext.parquet` (hourly OHLC, 35 coins,
  t = bar START UTC, 2020-08-01 00:00 .. 2026-09-23 23:00; majors days
  all complete with 24 bars). ONLY hourly data is loaded: no 1m, no
  options/premium/DVOL. One process, one coin at a time, RAM < 1 GB.
- 4h BOT dip stream: `research/tournament/ext/fills_U_ext.parquet`
  loaded EXACTLY as `research/tournament/oc_idea7` does, i.e. via
  `research/tournament/ext/harness5.py::load` (T = t_fill - f, majors-R2
  rows joined to the deployed R2 table for size_dep/tp_dep, outcome
  y_dep = exact net at the DEPLOYED TP, fees + adverse funding inside).
- The BOT book (forward_v205.research_books_d2) and deribit/premium
  panels are listed context only and are NOT used: the sleeve is scored
  standalone against the 4h dip stream per the rule below.
- Market data up to 2026-09-24 00:00 UTC is read per the assignment
  (all five years are research data; any PROMISING finding needs
  prospective validation before real money). Disclosed against
  RULES.md-2 / VF_COMMON hidden-year conventions.

## Exact causal definitions (frozen; one fixed rule, no grid)

Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.

1. Day D (00:00 UTC) open: O_D = open of the hourly bar starting at D
   00:00. A day is traded only if all 24 hourly bars starting D 00:00 ..
   D 23:00 are present, else the day is skipped for that coin.
2. sigma_d (per coin, known at D 00:00): daily open-to-open simple
   returns r_d = O_d / O_{d-1} - 1 for d in [D-90, D-1] (90 returns,
   needs only opens <= O_{D-1}); sigma_d = std(ddof=1) of the finite
   r_d with finite positive denominators. Require >= 60 finite returns
   and finite sigma_d > 0, else skip the coin-day (no bids).
3. Rungs k in {1.5, 2.0, 2.5}. Level lv_k = O_D * (1 - k*sigma_d).
   Resting limit bids valid day D. FILL: first hourly bar of day D
   (starts 00:00..23:00) with low < lv_k*(1-0.0005) (STRICT
   trade-through, 5 bps conservative buffer). Fill price = lv_k, entry
   fee maker 0.0002. At most one fill per (D, coin, k). Hour
   granularity cannot exclude touches before 00:05 inside the 00:00 bar:
   the 00:00 bar is included and this is disclosed as an approximation
   (affects only fills inside that single bar).
4. Post-fill (long), evaluated on hourly bars with start strictly after
   the fill-hour start, through the bar starting D+2 23:00:
   tp = lv*(1+1.0*sigma_d), sl = lv*(1-2.0*sigma_d).
   - TP touch: first bar with high > tp (STRICT). The fill hour can
     NEVER take profit (even if its high > tp, ignored).
   - STOP: first bar with close <= sl -> exit at the NEXT hour's open
     (taker 0.00055). A stop on the D+2 23:00 bar exits at the D+3
     00:00 open.
   - Same-bar priority: a bar with high > tp AND close <= sl is a STOP
     (stop-first, as the 4h engine).
   - TIME exit: otherwise exit at the open of day D+3 (open of the bar
     starting D+3 00:00), taker 0.00055.
   - Day D is traded only if the D+3 00:00 bar is present (pre-checked
     per day, so time exits always exist; entries need D <= 2026-09-20
     given data to 2026-09-23 23:00; later days are skipped, disclosed).
   - A rung needing a missing in-window hourly bar is dropped (no
     trade); in practice majors days are complete.
5. Funding: longs pay 0.0001 per 8h settlement held. N = #{S in {00:00,
   08:00, 16:00 UTC hour starts} : F_start < S <= E_start}, F_start =
   fill-hour start, E_start = TP-trigger hour start / stop-exit hour
   start / D+3 00:00. fund = 0.0001*N (hour-start proxy, disclosed).
6. Net per filled rung (unit size): TP: tp/lv-1-0.0002-0.0002-fund;
   stop/time: px/lv-1-0.0002-0.00055-fund. Win = net > 0 (strict).
7. Anchor years: entry day D in [A_k, A_k+365d), A_k in
   {2021-09-24 .. 2025-09-24} UTC. Per year report: fills n, win rate,
   mean net bps (mean(net)*1e4), sum of nets, worst exit-day sum,
   maxDD of the exit-day-sum cumsum path (P_0 = 0 included in the
   running peak; DD = peak - path; maxDD >= 0).
8. Exit-day stamp (for daily sums): TP -> TP-trigger hour start floored
   to UTC day (exit occurs inside that hour; disclosed proxy, midnight
   straddlers negligible); stop -> exit hour start floored; time ->
   D+3 date.
9. 4h stream daily sums: harness5 test-row mask per year (majors, x1 in
   R2 {2.5,3,3.5,4,5}, size_dep non-NaN, T in [A_k, A_k+365d)),
   UNWEIGHTED sum(y_dep) grouped by UTC exit date (floor(t_exit)).
   Unit matches the daily sleeve (per-unit-rung net), so streams combine.
10. Correlation: Pearson of aligned exit-day sums (missing day = 0).
    PRIMARY: full-period grid every UTC day 2021-09-24 .. 2026-09-26
    (covers all exit spill). Per-year correlations on [A_k, A_k+368d)
    grids are descriptive. NaN (zero variance) = FAIL.
11. Combined-DD test per year: align b (4h exit-day sums, entry-year
    trades) and s (daily exit-day sums, entry-year trades) on the union
    grid [A_k, A_k+368d), missing = 0. c = b + 0.5*s. S_b = sum(b),
    S_c = sum(c). If S_b > 0 and S_c > 0: scaled-4h path =
    cumsum(b * S_c/S_b); PASS iff maxDD(cumsum(c)) <= maxDD(scaled-4h
    path). Else FAIL (disclosed; expected not to trigger).
12. LOYO (descriptive, NOT part of the rule): pooled daily sum over the
    other 4 entry-years > 0 (strict) per held-out year.

## Decision rule (fixed here; idea-specific rule governs)

The assignment's header default (4/5 sign + 4/5 LOYO) is SUPERSEDED by
idea #21's own PROMISING rule (stated in the assignment body):
PROMISING iff (a) daily sleeve sum > 0 in >= 4/5 entry years, AND
(b) full-period daily-P&L correlation with the 4h stream < 0.5, AND
(c) combined (4h + 0.5*daily) maxDD not worse than scaled 4h-alone in
>= 3/5 years. Otherwise NOT PROMISING. One variant only, scored once;
any change after seeing scores is a disclosed extra variant.

## Deliverables

research/tournament/oc_dailyladder/: PLAN.md (this file),
analyze_dailyladder.py, results.json, trades.parquet, REPORT.md
(tables + one-line verdict). tests/test_oc_dailyladder.py. No commits,
no edits outside these two paths.
