# oc_dipbe PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #34: break-even protection for dip rungs (risk rule, not a return booster).

## Hypothesis (fixed here)

Moving a filled rung's close-stop up to break-even once the trade shows a
+0.6-sigma profit cuts the left tail (smaller maxDD) while giving back only a
small share of the yearly sum (opportunity cost of whipsawed winners).
Direction pre-registered: BE matches base sum within 3% and does not worsen
maxDD. Fixed rule, no fitted parameters (0.6 trigger multiple, fill+fees stop
level, 5m-block evaluation are all frozen below).

## Replica (base arm = oc_b1deeper B1, exact copy of its code/definitions)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others). Minutes used: t < 2026-09-24
  00:00 UTC. Missing minutes (NaN) never fill, never trigger any touch, and a
  fill whose exit price is NaN is dropped.
- Standard 4h grid from START = 2020-08-01 00:00 UTC (bar j = 240 offsets
  0..239, next-bar open = offset 240). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- sigma_4h(c,T): simple returns of 4h bar opens, std over 360 bars ending at
  T-1, min_periods 120, ddof=1, shifted (v293/oc_dipexit/oc_b1deeper-exact).
  Known at the bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level lv = O(T)*(1-k*sg).
  Resting limit BUY at lv, live offsets 16..238. Fill at FIRST offset f with
  low(T+f) < lv (STRICT trade-through). Fill price px = lv. At most one fill
  per (bar, coin, k). Size w = 1/(1+n_fill), n_fill = # OTHER majors with
  C(T+f-1) <= O_b(T)*(1-2.5*sg_b(T)) (v399-exact, <= counts, NaN never counts).
- Base exits (D0 replica from fill px, oc_b1deeper-exact): sl = px*(1-4*sg),
  bl = px*(1-8*sg), tp = px*(1+1.0*sg); minutes t in f+1..239 then timeout at
  240 (o2 = 1m open at T+240): backstop (first low <= bl) exits at
  min(bl,open(t)) taker; else TP (first high > tp, STRICT) exits at tp maker;
  else close5 stop (clock minutes m with (m+1)%5==0, first with close <= sl)
  exits at open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
  0.0001 if (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties;
  else TP wins only if strictly earlier; else stop; else timeout. Fees: fill
  maker 0.0002; TP leg maker 0.0002; stop/backstop/time legs taker 0.00055.
  Nets are fractions of px.

## Break-even arm (fixed rule, paired on the SAME fills)

- Trigger level be_trig = px*(1+0.6*sg). tb = FIRST t in f+1..239 with
  high(t) > be_trig (STRICT, same convention as the TP touch; NaN never
  triggers).
- BE stop level be_stop = px*(1+MAKER+TAKER) = px*1.00075 (fill price + round-
  trip fees: exiting exactly at be_stop nets 0 before gap/funding).
- Arming (causal, stop-first): let kb/kt/ks0 be the base trigger indices
  (offsets into f+1..239). BE arms IFF tb exists AND tb is strictly before
  every base trigger (kt None or tb<kt; kb None or tb<kb; ks0 None or tb<ks0).
  A same-minute tie (tb==kt possible since be_trig<tp; tb==ks0/kb possible)
  goes to the base exit; BE never arms. Before tb the close-stop is sl.
- If armed, the close-stop moves to be_stop for minutes m in tb+1..239 (the
  trigger minute itself still uses sl, as in oc_dipexit E3): ks_be = first
  clock minute ((m+1)%5==0) with close(m) <= be_stop (NaN never triggers),
  exit at open(m+1) (or o2 if m=239) taker, net = ex/px-1-MAKER-TAKER (-FUND
  if x==240 and settle). Backstop (bl) and TP (tp) are unchanged and keep
  base priority: backstop wins ties; TP wins only if strictly earlier than
  ks_be; else the BE stop; else timeout. If never armed, BE == base exactly.
- "Without hitting its TP" is enforced by tb<kt: a rung that TPs at or before
  the trigger minute exits at TP and never arms.

## Scoring (fixed)

- Paired fills: both arms share fills/weights (BE changes exits only).
- Weights w' = w/mean(w) per anchor year per arm (oc_b1deeper primary; the
  factor is identical across arms since fills are shared).
- Per anchor year, per arm: n, mean net, win rate (net>0 strictly,
  equal-weight), timeout share (how=="time" share), sum S of w'*y grouped by
  EXIT date (calendar UTC date of T+x; x=240 books to the T+4h date), worst
  day W = min daily sum, maxDD of the cumulative daily-sum path from 0.
- Full-path sums/DD for context. Base replica is validated by matching
  oc_b1deeper B1 per-year n/sums to the tick.

## Decision rule (fixed, idea-specific, from the assignment)

Per year Y: PASS_dd(Y) iff DD_BE(Y) <= DD_base(Y) (equal passes; NaN -> FAIL).
PASS_sum(Y) iff S_BE(Y) >= 0.97*S_base(Y) (equal passes; NaN -> FAIL; if
S_base(Y) <= 0 then S_BE(Y) >= S_base(Y)). PROMISING iff PASS_dd in >= 4/5
years AND PASS_sum in >= 4/5 years. Otherwise NOT PROMISING (it is a risk
rule: the sum leg tolerates a 3% give-back). One-line verdict in REPORT.md.
The generic same-sign/LOO default does not apply; this idea-specific rule
governs.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. Then `be_core.py` (copied
  D0 replica + BE outcome, pure numpy, no I/O), `run.py` (per-coin loop ->
  results.json + fills ledger), REPORT.md (tables + one-line verdict).
- Tests: `tests/test_oc_dipbe.py` (synthetic hand checks: strict trigger,
  same-minute tie to base, BE-stop price nets 0, parity when never armed,
  backstop priority, causality/future-blindness).
- No commits; no edits outside research/tournament/oc_dipbe/
  (+ tests/test_oc_dipbe.py). One process, one coin's H/L in RAM at a time,
  all-five-coins 1m closes as float32; RAM < 3 GB.
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; a PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
