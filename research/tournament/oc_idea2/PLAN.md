# oc_idea2 PLAN (pre-registered BEFORE any outcome statistic, 2026-10-05)

Implements idea #2 of research/tournament/oc_ideas/IDEAS.md EXACTLY as described
there ("Per-coin dip close-stop distance"). This PLAN is written before any
outcome is computed.

## Hypothesis

17/20 worst rungs are full-size (n=0) single-coin XRP stop-outs (oc_ddanat17);
SOL drove the FTX cascade. One global 4-sigma close-stop cannot fit both a
whipsaw coin and a trending one. Widening ONLY XRP's close-stop to 5.5 sigma
(keeping BTC/ETH/SOL/BNB at 4 sigma) keeps exposure but trims the tail where
stops concentrate: expected return -0.1-+0.1 pp/mo, DD -0.5-1.5 pp (tail trim,
not edge, per IDEAS.md).

## Universe, data, years (fixed)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used: t < 2026-09-24
  00:00 UTC. One coin in memory at a time (float32), one process, RAM < 1 GB.
- 4h grid: holding bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC (midnight floor("4h") grid, same as oc_dipexit /
  v293). Bar j has 240 minute offsets 0..239; next-bar open is offset 240.
  Only bars with open in [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded
  (5 anchor years 2021-09-24..2026-09-23).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b / O_{b-1}
  - 1 of 4h bar opens; sigma(j) = std(r over 360 bars ending at j-1,
  min_periods 120, ddof=1) = v293 Asset = oc_dipexit run.py
  (pct_change().rolling(360).std().shift(1)). Bars with non-finite O_j or
  sigma <= 0 / NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Level lv = O_j * (1 - k*sigma(j)).
  Resting limit BUY at lv, live window offsets 16..238 inclusive. Fill at the
  FIRST offset f with low(f) < lv (STRICT trade-through). Fill price = lv, fee
  maker 0.0002. At most one fill per (bar, k). Fill uses only minutes <= f of
  the same bar.
- Market data up to 2026-09-24 00:00 UTC per assignment (all 5 years are
  research data; any PROMISING rule needs prospective validation before real
  money). Disclosed vs RULES.md hidden-year convention.

## Exact causal definitions (frozen, ONE pair only)

- Uniform U (baseline = oc_dipexit D0): close-stop distance M = 4.0 sigma for
  ALL coins.
- Per-coin V (single pre-registered variant): close-stop distance M = 5.5 sigma
  for XRP, M = 4.0 sigma for BTC/ETH/SOL/BNB.
- Everything else identical between U and V (8-sigma native backstop unchanged,
  5m-block CLOSE evaluation as v266 B1, exit next minute open):
  sl(M) = lv*(1-M*sigma), bl = lv*(1-8*sigma), tp = lv*(1+1.0*sigma).
  - BACKSTOP touch: first t in f+1..239 with low(t) <= bl -> exit at
    min(bl, open(t))/lv-1-maker-taker (gap pays the open; min() picks the worse
    price for a long), taker 0.00055.
  - TP touch: first t with high(t) > tp (STRICT) -> exit at tp/lv-1-2*maker.
  - CLOSE5 stop: clock minutes m with (m+1)%5==0 (absolute bar clock:
    4,9,...,239); first m with close(m) <= sl(M) -> exit at open(m+1) (or
    next-bar open o2 if m=239), net = px/lv-1-maker-taker (minus 0.0001 funding
    if the exit is at a settling timeout open).
  - TIMEOUT: else exit at next-bar open o2, net = o2/lv-1-maker-taker-fund,
    where fund = 0.0001 if (bar_open+4h).hour in (0,8,16) else 0 (longs pay,
    shorts n/a; no funding on intrabar exits).
  - Priority (stop-first, v293): backstop wins ties (kb<=ks and kb<=kt); else
    TP wins only if strictly earlier (kt<ks); else stop; else timeout. A stop
    and TP in the same minute -> stop wins.
  - Missing minutes (NaN) never fill and never trigger an exit touch; a fill
    whose timeout open is NaN is dropped. Paired rungs: kept only if BOTH U and
    V nets are finite (non-XRP legs coincide by construction).
- No threshold search, no other pair. One variant only (V vs U).

## Statistics (fixed, no fitting)

- Per year (anchors 2021..2025, year = bars with open in [anchor, anchor+365d);
  2025 year = [2025-09-24, 2026-09-24)): for U and V report over its rungs:
  count, mean net, win rate (net>0 strictly), sum of nets (equal-notional),
  worst calendar-UTC-day sum and max drawdown of the cumulative daily-sum curve
  (daily sums by EXIT date UTC, starting 0).
- Effect D = S_V - S_U per year; LOO D_{-i} = mean(D over years != i).
- Also report per-coin yearly sums (XRP vs non-XRP split) for context, plus
  XRP stop-hit rate under U vs V (share of XRP rungs exiting via "stop").

## Decision rule (fixed, assignment default + sizing/filter tail bar)

- PROMISING only if ALL three hold:
  (a) D > 0 in >= 4 of 5 anchor years, AND
  (b) leave-one-year-out D_{-i} > 0 in >= 4 of 5 cases, AND
  (c) yearly worst-day of V not worse than yearly worst-day of U
      (V_worst >= U_worst, tolerance 0) in >= 4 of 5 years.
- (a)+(b) = the assignment default decision rule; (c) = the extra worst-day
  bar stated in this task ("worst day not worse in >= 4/5 years") and
  pre-registered in IDEAS.md idea #2 ("worst-day not worse in >= 4/5 years").
- One-line verdict in REPORT.md (PROMISING / NOT PROMISING).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process, one coin at a
  time, float32 1m arrays, RAM < 1 GB. No commits, no edits outside
  research/tournament/oc_idea2/ (+ tests/test_oc_idea2.py).
- Scripts: analyze_idea2.py (per-coin replica with per-coin stop leg ->
  results.json); outputs results.json, REPORT.md (tables + one-line verdict).
- Replica cross-check: uniform leg U must reproduce oc_dipexit D0 yearly sums
  exactly (same fills, same exit code); assert max |U - D0| < 1e-9 per year.
