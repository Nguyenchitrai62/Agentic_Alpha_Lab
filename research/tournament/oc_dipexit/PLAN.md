# oc_dipexit PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

## Hypothesis
The deployed dip-rung exit (take-profit 1 sigma_4h, close5 stop 4 sigma, 8-sigma
backstop, timeout at the next 4h open) may not be the best rung-level exit.
Four fixed structural alternatives (split TP, time-capped TP, breakeven trail,
full-reversion TP) are tested as exact counterfactuals on every filled rung.

## Replica (deployed baseline D0, from v293_pooled_exit_agent.py Asset/outcomes)
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC), data/raw/majors_intraday_20260924
  (others). Minutes used: t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never
  fill and never trigger an exit touch; a fill whose timeout open is NaN is dropped.
- Standard 4h grid: holding bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC (= midnight floor("4h") grid). Bar j has 240 minute
  offsets 0..239; next-bar open is offset 240. Only bars with open in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 years 2021-09-24..2026-09-23).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b / O_{b-1} - 1
  of 4h bar opens; sigma(j) = std(r over 360 bars ending at j-1, min_periods 120,
  ddof=1) = v293 Asset (pct_change().rolling(360).std().shift(1)). Bars with
  non-finite O_j or sigma<=0/NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Level lv = O_j * (1 - k*sigma(j)).
  Resting limit BUY at lv, live window offsets 16..238 inclusive. Fill at the FIRST
  offset f with low(f) < lv (STRICT trade-through). Fill price = lv, fee maker 0.0002.
  At most one fill per (bar, k). Fill uses only minutes <= f of the same bar.
- Post-fill exits (long), evaluated on minutes t in f+1..239 then timeout at 240:
  sl = lv*(1-4*sigma), bl = lv*(1-8*sigma), tp(mu) = lv*(1+mu*sigma).
  - BACKSTOP touch: first t with low(t) <= bl -> exit at min(bl, open(t))/lv-1-maker-taker
    (gap pays the open; min() picks the worse price for a long), taker 0.00055.
  - TP touch: first t with high(t) > tp (STRICT) -> exit at tp/lv-1-2*maker.
  - CLOSE5 stop: clock minutes m with (m+1)%5==0 (absolute bar clock: 4,9,...,239);
    first m with close(m) <= sl -> exit at open(m+1) (or next-bar open o2 if m=239),
    net = px/lv-1-maker-taker.
  - TIMEOUT: else exit at next-bar open o2, net = o2/lv-1-maker-taker-fund, where
    fund = 0.0001 if (bar_open+4h).hour in (0,8,16) else 0 (v293 settle rule; longs
    pay, shorts n/a; no funding on intrabar exits).
  - Priority (stop-first, v293): backstop wins ties (kb<=ks and kb<=kt); else TP wins
    only if strictly earlier (kt<ks); else stop; else timeout. A stop and TP in the
    same minute -> stop wins.
- D0 (deployed): mu = 1.0.

## Alternative exits (fixed, at most 4; each rung gets an exact net under each)
- E1 split TP: half notional TP 0.5 sigma, half TP 1.5 sigma; stops/backstop/timeout
  shared. net = 0.5*y(0.5) + 0.5*y(1.5), where y(mu) is the replica outcome with the
  same sl/bl/timeout race vs tp(mu). Fees per half as in the replica (maker fill +
  maker TP leg / taker stop/time leg + funding on timeout legs only).
- E2 TP 1.0 sigma + 120-min time exit: same as D0 except a forced time exit at
  open(f+120). Signals evaluated only on t in f+1..f+119; if f+120 >= 240 it is the
  normal timeout at o2 (with settle funding). Early time exit: px = open(f+120),
  net = px/lv-1-maker-taker, no funding. Stop/backstop keep priority over TP and over
  the time exit (a stop signal with exit open <= open(f+120) fires first at the same
  price/fee, so outcomes coincide there by construction).
- E3 trailing (breakeven) exit: TP stays 1.0 sigma, sl/bl/timeout as D0, plus:
  activation at the first t with high(t) > lv*(1+0.5*sigma) (same strict touch as a
  0.5-sigma TP). From minutes after activation, the close5 stop level moves to the
  fill level lv (breakeven): clock minute m fires if close(m) <= (sl when m<=ka else
  lv), exit at open(m+1)/o2 taker. Backstop (8 sigma) unchanged and keeps top priority;
  TP-vs-stop keeps stop-first (kt<ks required for a TP win). If never activated,
  E3 == D0 exactly.
- E4 full-reversion TP capped at 2 sigma: tp = min(bar_open O_j, lv*(1+2*sigma));
  race/priority/fees/funding identical to D0 with this tp. (For k>=2.5 the cap binds,
  so E4 ~= fixed 2-sigma TP; the min() form is exact for all k.)

## Decision rule (fixed, from the assignment)
Per year (anchors 2021..2025, year = bars with open in [anchor, anchor+1y)): for D0
and each E alternative report over its rungs: count, mean net, win rate (net>0),
sum of nets (equal-notional), worst calendar-UTC-day sum and max drawdown of the
cumulative daily-sum curve (daily sums by EXIT date UTC, starting 0). An exit is
PROMISING iff its yearly sum >= D0's yearly sum in >= 4 of 5 years AND its worst day
is not worse than D0's worst day (per-year comparison; full-period table for context).

## Protocol / resources (fixed)
- PLAN.md written before any outcome computation. One process, one coin at a time,
  float32 1m arrays, RAM < 1.5 GB. No commits, no edits outside
  research/tournament/oc_dipexit/ (+ tests/test_oc_dipexit.py).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all 5 years are
  research data; any PROMISING exit needs prospective validation before real money).
  This is disclosed against RULES.md 2 / VF_COMMON (hidden-year) conventions.
- Scripts: exits.py (replica + E1-E4 exact outcomes, vectorised per-fill numpy on
  1m slices), run.py (per-coin loop, per-rung nets + exit-day ledger -> results.json).
  Outputs: results.json, REPORT.md (tables + one-line verdict).
