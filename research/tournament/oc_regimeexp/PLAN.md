# oc_regimeexp PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

REPORTING task only (no PROMISING rule, no trading verdict).
Question: conditional on the market state at the start of a calendar month,
what does the deployment pick R2B1D17BF's monthly return distribution look
like, and what does that imply for the months ahead given the current state?

## Data (fixed here)

- Monthly returns: research/tournament/oc_kpi/results_equity.json, "monthly"
  table (61 calendar months 2021-09..2026-09, 4-phase mix, values in %).
  Used EXACTLY as stored (no recomputation of equity). 2021-09 is partial
  (mix starts 2021-09-24 04:00) and 2026-09 is partial (to g1 = Y1+12h);
  both are kept and flagged as partial.
- Market data: research/tournament/ext/hourly_ext.parquet ONLY
  (hourly OHLC 35 coins, t up to 2026-09-23 23:00 UTC). No 1m data, no fills,
  no funding/premium/dvol. BTC 4h open series is DERIVED from hourly opens:
  a 4h bar opening at T (T on a 00/04/08/12/16/20 UTC boundary) has
  open(T) = hourly open at T. All state definitions use only timestamps
  strictly causal as defined below (nothing at or after the classification
  time except the bar open exactly AT that time, which is known at that time).

## Exact causal definitions (fixed here)

Let o(T) = BTC 4h open at 4h-boundary T (from hourly_ext open at T).
Month-start time M0 = first day of calendar month M, 00:00 UTC (always a 4h
boundary, so o(M0) exists and is known exactly at M0).

1. bear flag: p0 = o(M0); mu1200 = mean of the 1200 opens with
   T in [M0 - 1200*4h, M0 - 4h] (strictly before M0; 1200 bars = 200 days).
   bear = 1 if p0 < mu1200 else 0. Requires o back to M0-200d; hourly starts
   2020-08-01 so all M0 >= 2021-03 are covered (all 61 months OK).

2. vol30 (30-day realized vol, BTC): hourly log returns
   h(t) = log(close(t)/close(t-1h)) for hourly bars with close time <= M0
   (i.e. bars t < M0; the bar 23:00 of the prior day closes exactly at M0).
   vol30(M0) = std of the 720 h(t) values ending with the bar closing at M0
   (30*24 hourly returns; scaling constant omitted, tercile is scale-free).
   Tercile label (expanding, causal): history H(M0) = {vol30 at month starts
   strictly before M0, back to 2021-03-01} (first vol30 needs 720h history
   from 2020-08-01, so 2021-03-01 is the earliest full extra point; by
   2021-09-01 there are >= 6 priors). lo,hi = 33rd/67th percentiles of H(M0)
   (linear interpolation, numpy default); label = low if v <= lo, high if
   v >= hi, else mid. (Boundary ties go to the outer bucket; documented.)

3. trend90 sign: s90 = log(p0 / o(M0 - 90d)) where o(M0-90d) is the 4h open
   exactly 540 bars before M0. up if s90 >= 0 else down. (Exact zero -> up.)

State of month M = (bear 0/1, vol low/mid/high, trend up/down) evaluated at
its M0. 2*3*2 = 12 possible combos.

## Report (fixed here)

- Per single state (bear 0/1; vol low/mid/high; trend up/down): over the 61
  months (and noting the 2 partial months): n, mean %, median %, share of
  months >= +5 %, share < 0 %, worst month (YYYY-MM + %).
- Per state combination with n >= 5: same six stats. Combos with n < 5 are
  listed by n only (no stats, too thin).
- CURRENT state: same three definitions evaluated (a) at 2026-09-01 00:00
  (the bucket September 2026 sits in) and (b) at 2026-09-24 00:00 UTC = first
  bar boundary at/after the last data (uses hourly t <= 2026-09-23 23:00;
  nothing beyond the 2026-09-24 00:00 UTC cutoff). For each, report the
  historical stats of its bucket(s) with an explicit small-n caveat.
- Plain language, no PROMISING/PROMISING-like verdict, no trading rule.

## Causality / reproducibility tests (tests/test_tournament_oc_regimeexp.py)

- 4h opens come only from hourly opens at the same timestamp.
- Every month-start state uses no hourly bar with t >= M0 (truncate test on
  3 sample months: recompute from hourly truncated to t < M0 plus o(M0), equal).
- Monthly table used byte-identical to oc_kpi/results_equity.json.
- No timestamp beyond 2026-09-24 00:00 UTC is touched.

## Deliverables

research/tournament/oc_regimeexp/: PLAN.md (this file), compute_regimeexp.py,
results.json, REPORT.md. One process, RAM < 1 GB.
