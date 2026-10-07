# oc_idea2wf PLAN (pre-registered BEFORE any outcome statistic, 2026-10-05)

Walk-forward version of oc_idea2 (research/tournament/oc_idea2: per-coin dip
close-stop 4.0 vs 5.5 sigma, rung-level replica of oc_dipexit D0). oc_idea2
picked XRP from in-sample anatomy; this task removes that look-ahead. This
PLAN is written before any outcome is computed.

## Hypothesis

A per-coin close-stop distance chosen walk-forward (5.5 sigma when the coin's
own past favours it, else 4.0 sigma) beats the uniform 4.0-sigma close-stop
out of sample. Expected direction (from oc_idea2 in-sample: D>0 in 4/5y, all
from XRP): the walk-forward rule should pick 5.5 for XRP at most anchors and
4.0 elsewhere, with a small positive total D and no worse worst-day in >=4/5
years. Null: past (V-U) does not predict the next year (choices ~ coin flip,
D ~ 0, PROMISING bar missed).

## Universe, data, years (fixed)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used: t <= 2026-09-24
  00:00 UTC. One coin in memory at a time (float32), one process, RAM < 1 GB.
- 4h grid: holding bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC (midnight floor("4h") grid, same as oc_dipexit /
  oc_idea2). Bar j has 240 minute offsets 0..239; next-bar open is offset 240.
- Bars computed: ALL bars with open in [2020-08-01 00:00, 2026-09-24 00:00)
  UTC (as early as sigma_4h exists). Bars with non-finite O_j or sigma <= 0 /
  NaN are skipped (so the first scored bars start ~20d after START given
  min_periods 120).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b / O_{b-1}
  - 1 of 4h bar opens; sigma(j) = std(r over 360 bars ending at j-1,
  min_periods 120, ddof=1) = v293 Asset = oc_dipexit run.py =
  oc_idea2 analyze_idea2.py (pct_change().rolling(360).std().shift(1)).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Level lv = O_j * (1 - k*sigma(j)).
  Resting limit BUY at lv, live window offsets 16..238 inclusive. Fill at the
  FIRST offset f with low(f) < lv (STRICT trade-through). Fill price = lv, fee
  maker 0.0002. At most one fill per (bar, k). Fill uses only minutes <= f of
  the same bar.
- Market data up to 2026-09-24 00:00 UTC per assignment (all 5 years are
  research data; any PROMISING rule needs prospective validation before real
  money). Disclosed vs RULES.md hidden-year convention.

## Anchors and years (fixed, literal formula)

- Anchors A_k = 2021-09-24 00:00 UTC + k*365 days, k = 0..4, i.e.
  A0 = 2021-09-24, A1 = 2022-09-24, A2 = 2023-09-24, A3 = 2024-09-23,
  A4 = 2025-09-23 (all 00:00 UTC; A3/A4 shift 1 day early vs calendar years
  because 2024-02-29 falls inside; verified in python before any outcome).
- Anchor year k = bars with bar open in [A_k, A_k + 365 days). Year 4 =
  [2025-09-23, 2026-09-23); the single day 2026-09-23..2026-09-24 is computed
  (for exit opens) but belongs to no anchor year (disclosed 1-day gap).
- Cutoff per anchor: C_k = A_k - 7 days (00:00 UTC).

## Exact causal definitions (frozen, one pair of distances only)

- Uniform U (baseline): close-stop distance M = 4.0 sigma for ALL coins.
- Wide leg Vc (per coin c): close-stop distance M = 5.5 sigma for coin c
  (computed for EVERY major, not just XRP), M = 4.0 is U.
- No other candidate distances. One rule only (next section).
- Everything else identical between U and Vc (8-sigma native backstop
  unchanged, 5m-block CLOSE evaluation as v266 B1 / oc_idea2, exit next minute
  open), verbatim copy of oc_idea2.analyze_idea2.outcome_m with parameterized
  stop M:
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
    whose timeout open is NaN is dropped. Paired rungs: kept only if BOTH U
    and Vc nets are finite (fills identical by construction; stop affects
    exits only).
- Exit timestamp of a rung leg: t_exit = t_bar + x minutes, where x is the
  leg's exit offset (x = 240 means the next-bar open = t_bar + 4h). This is the
  actual exit time (timeout opens settle at that timestamp).

## Walk-forward choice rule (fixed, no fitting beyond the pre-registered sign)

- For each anchor A_k and each major coin c: let TRAIN(k,c) = paired rungs of
  coin c with max(t_exit_U, t_exit_Vc) < C_k = A_k - 7 days (conservative: BOTH
  legs must have exited before the cutoff, so no exit information at/after the
  cutoff is used; fills themselves are <= their exits, hence also pre-cutoff).
- Training statistic: S(k,c) = sum over TRAIN(k,c) of (ret_Vc - ret_U)
  (equal-notional sum of paired net-return differences, exact nets incl.
  fees/funding as above).
- Choice: m_c(A_k) = 5.5 if S(k,c) > 0 (strictly), else 4.0. Ties (incl. empty
  training, S = 0) -> 4.0. No other candidate distances, no thresholds, no
  re-tuning.
- Save choice.json as exactly {anchor_iso: {SYMBOL: m}} with anchor_iso =
  A_k date iso ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-23",
  "2025-09-23"), SYMBOL in {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT}, m in
  {4.0, 5.5} (JSON numbers). This file will be used by a registered engine run.

## Scoring (fixed, no fitting)

- For each anchor year k (rungs with bar open in [A_k, A_k+365d)): WF net of a
  rung = ret_Vc if m_c(A_k) == 5.5 else ret_U; uniform net = ret_U.
- Per year, for WF and U, report over its rungs: count, mean net, win rate
  (net>0 strictly), sum of nets (equal-notional), worst calendar-UTC-day sum
  and max drawdown of the cumulative daily-sum curve (daily sums by EXIT date
  UTC of the respective leg's exit -- WF path uses WF exits, U path uses U
  exits -- starting 0; same daily_stats as oc_idea2).
- Effect D_k = S_WF,k - S_U,k per year; LOO D_{-i} = mean(D over years != i).
- Also report: training table S(k,c) + n_train per anchor/coin (context), and
  per-coin yearly WF-vs-U sums for context.
- Replica cross-check: on the overlapping window (bars with open in
  [2021-09-24, 2026-09-23)) the U leg is the same replica as oc_idea2's U;
  assert per-year U sums match a re-aggregation within 1e-9 where windows
  coincide is NOT required (windows differ by the A3/A4 1-day shift), so
  instead assert the outcome_m function is a byte-identical copy of
  oc_idea2's (synthetic hand-checks in tests) and report U sums on the new
  windows.

## Decision rule (fixed, oc_idea2 three-part rule)

- PROMISING only if ALL three hold:
  (a) D_k > 0 in >= 4 of 5 anchor years, AND
  (b) leave-one-year-out D_{-i} > 0 in >= 4 of 5 cases, AND
  (c) yearly worst-day of WF not worse than yearly worst-day of U
      (WF_worst >= U_worst, tolerance 0) in >= 4 of 5 years.
- (a)+(b) = the assignment default decision rule; (c) = the extra worst-day
  bar from oc_idea2 (pre-registered in IDEAS.md idea #2 context).
- One-line verdict in REPORT.md (PROMISING / NOT PROMISING) + the choice table.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process, one coin at a
  time, float32 1m arrays, RAM < 1 GB. No commits, no edits outside
  research/tournament/oc_idea2wf/ (+ tests/test_oc_idea2wf.py).
- Scripts: analyze_idea2wf.py (per-coin replica with per-coin stop legs ->
  results.json + choice.json); outputs results.json, choice.json, REPORT.md
  (tables + one-line verdict).
