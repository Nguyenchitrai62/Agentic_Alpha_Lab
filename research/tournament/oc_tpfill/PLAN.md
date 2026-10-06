# oc_tpfill PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Realism check #79 = docs/opencode/IDEAS3_20261006.md idea 7
(native TP attached at fill minute, execution, BOT).

## Hypothesis (fixed here, diagnostic only)

In the engine replica a dip-rung take-profit (1-sigma limit, maker) can only
fill from the minute AFTER the fill minute, while on the exchange an attached
OCO (SL + TP) is live within seconds of the fill. The first post-fill minutes
hold the snapback that a delayed TP misses, so the replica's next-minute
convention is conservative (understates TP fills and rung sums) by a small
amount. The fixed variant attaches the TP in the fill minute itself under a
deliberately conservative proxy (close at/above the TP level, not just a high
wick). Pre-registered direction: FIX yearly size-weighted rung sums are NOT
lower than BASE (FIX >= BASE), with no worse tail; the magnitude is small
(a handful of same-minute TPs, basis points of rung-y sum).

## Replica (deployed baseline BASE = oc_dipexit D0, exact, + B1 sizes + 4 phases)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others), columns
  open_time/open/high/low/close. Minutes used: t < 2026-09-24 00:00 UTC;
  the timeout/next-minute open at exactly 2026-09-24 00:00 is allowed as an
  exit price only (oc_dipexit convention). Missing minutes (NaN) never fill
  and never trigger an exit touch; a fill whose exit price is NaN is dropped.
- Four clock phases: 4h grid from START = 2020-08-01 00:00 UTC + p*1h,
  p in {0,1,2,3}. Phase 0 == oc_dipexit grid exactly. Bar j of phase p covers
  [START + p*1h + 4h*j, +4h). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  2021-09-24..2025-09-24, +365 d; Y_k = [A_k, A_{k+1}) for k = 0..3,
  Y_4 = [A_4, 2026-09-24); year keyed by BAR-OPEN T, identical to
  oc_dipexit / oc_fillttl / oc_marktrig).
- sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of that phase's 4h bar
  opens; sigma = std(r over 360 bars ending at T-1, min_periods 120, ddof=1)
  = v293/oc_dipexit definition, computed per (phase, coin). Known at the bar
  open T. Bars with non-finite O, sg <= 0 or NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sg(T)). Resting limit BUY, live window offsets 16..238
  inclusive. Fill at the FIRST offset f with low(T+f) < lv (STRICT
  trade-through). Fill price = lv, fee maker 0.0002. At most one fill per
  (phase, bar, coin, k). Fill uses only minutes <= f of the same bar.
- B1 size (oc_b1deeper / oc_marktrig exact): n(a,T,m) = number of OTHER
  majors b != a with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T)*(1 - 2.5*sg_b(T)) (<= counts; own coin never counted,
  0..4). w = 1/(1+n_fill) at the fill minute f. Fills (lv, f, w) are
  IDENTICAL across BASE and FIX arms; only the post-fill TP timing differs,
  so weights are identical on every paired rung. No renormalisation (raw w*y
  sums; renormalisation would scale both arms identically).
- Post-fill exits BASE (long), oc_dipexit D0 replica from the fill price px
  (= lv): sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated
  on minutes t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t)) taker;
  else TP touch (first t with high(t) > tp, STRICT) exits at tp maker
  (2*maker round-trip); else close5 stop (clock minutes m with (m+1)%5==0 on
  bar-relative offsets 4,9,...,239 -- equals the global 5-min clock since
  every phase base (0/60/120/180) is a multiple of 5 -- first m with
  close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else timeout at
  o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16) (v293 settle rule;
  longs pay; no funding on intrabar exits). Priority stop-first: backstop
  wins ties (kb<=ks and kb<=kt); else TP wins only if strictly earlier
  (kt<ks); else stop; else timeout. A stop and TP in the same minute ->
  stop wins. Net returns are fractions of px. Fees: fill maker 0.0002; TP leg
  maker 0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055.
  A rung whose exit price is missing (NaN open, NaN o2 on a stop-at-239 /
  timeout path) gives NaN net and is DROPPED (paired-rung rule below).

## FIX variant (fixed, timing only; levels, stops, costs unchanged)

- FIX levels identical to BASE (sl/bl/tp from the same px = lv, same sg).
  FIX stops/backstop/timeout identical to BASE (evaluated on f+1..239 + 240,
  same priority/fees/funding).
- FIX-TP: the TP may ALSO fill in the fill minute f itself iff
  close(f) >= tp (NON-STRICT close at/above the level; this is the
  conservative proxy for "traded through after the fill" -- it requires the
  minute to CLOSE above the TP, not just wick through it). If it triggers:
  exit at tp, net = tp/px-1-2*maker, x = f, how = "tp_same".
  Otherwise the race proceeds EXACTLY as BASE on f+1..239 + timeout
  (same stop-first priority; a stop and TP in the same later minute ->
  stop wins, unchanged).
- Priority note: a same-minute TP cannot be stop-blocked (stops start at
  f+1 by construction in both arms). Same-minute backstop overlap (a minute
  with low(f) < lv AND low(f) <= bl AND close(f) >= tp) is counted as a
  same-minute TP by this rule; such minutes are tallied separately
  (n_same_tp_with_deep_low) so the proxy's generosity is auditable. No other
  same-minute exit exists.
- Fees/funding on a same-minute TP: fill maker + TP-leg maker (2*maker
  round-trip), no taker, no funding (intrabar exit) -- identical to a later
  TP. Exit-date of a same-minute TP is the bar date (T+f).
- Causality: fill uses low(f) < lv; same-minute TP adds only close(f) >= tp
  of the SAME minute (both known at the close of minute f). No lookahead
  beyond f; sigma excludes the bar; n uses closes up to m-1; no fitted
  parameter (zero fitted parameters).

## Scoring (fixed here)

- Paired rungs: kept only if BASE net AND FIX net are both finite (same
  pairing rule as oc_dipexit across legs; fills identical, exits differ only
  by the same-minute TP, so finiteness differs only if BASE's exit price is
  NaN while FIX exits same-minute, or vice versa -- never vice versa here
  since FIX==BASE whenever no same-minute TP).
- Per (phase p, year Y, variant V in {BASE, FIX}): over kept paired fills:
  n = rung count; sum S = sum(w*y) (B1 size-weighted, raw return-fraction
  units, no renormalisation); mean = mean(y) (equal-weight, descriptive);
  win = fraction with y > 0 strictly (equal-weight, descriptive); daily sums
  group w*y by EXIT date (calendar UTC date of T+x, x = exit offset,
  240 = next-bar open date = (T+4h).date(), per arm's own exit date);
  worst day W = min daily sum; cumulative path over exit dates sorted
  ascending from 0: maxDD = max_{peak<trough}(peak - trough) (>= 0, w*y
  units); ndays; exit-split counts n_tp (incl. same-minute), n_tp_same,
  n_stop, n_backstop, n_time. Same-minute TPs also reported as share of FIX
  TPs and of fills.
- 4-phase means per year: S_bar(Y) = mean_p S(p,Y); DD_bar(Y), W_bar(Y),
  n_bar, win_bar, tp_same_bar = means across p=0..3. Per-phase sums also
  stored (clock-swing context). 5y sums: sum5y = sum_Y S_bar(Y) per variant;
  dSum5y = sum5y_FIX - sum5y_BASE (context only, NOT a decision leg).
- Default-rule context rows (assignment default: PROMISING iff same sign in
  >= 4/5 years AND LOO holds in >= 4/5): delta(Y) = S_bar_FIX(Y) -
  S_bar_BASE(Y); YEARS_GE = count of Y with delta(Y) >= 0 (equal passes);
  LOO(h) = sum_{Y != h} delta(Y); LOO_HOLDS = count of h with LOO(h) >= 0.
  Reported as context only.
- DECISION (this task is NOT a selection, per the assignment): no
  PROMISING/NOT-PROMISING verdict on a tradable rule. The REPORT answers per
  year (4-phase means + per-phase table): same-minute TP count, S/win/W/DD
  for BASE vs FIX and the delta, and states plainly whether the engine's
  next-minute convention is conservative (FIX >= BASE) and by how much
  (dSum5y, per-year deltas, same-minute TP count/share). One-line verdict =
  that conservatism sentence.

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation (this file). Then scripts:
  `tpfill.py` (pure-numpy core: n vector, B1 size, BASE D0-from-fill exit,
  FIX-from-fill exit with the close>=tp same-minute hook),
  `run.py` (per-phase/per-coin loop, paired ledger + exit-day sums ->
  results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_tpfill.py` (synthetic hand checks +
  causality: strict fill, sigma excludes the bar, stop-first ties kept,
  same-minute TP needs close>=tp not just high>tp, same-minute TP exits at
  tp with 2*maker at x=f, no-same-minute-TP path equals BASE exactly,
  NaN exit dropped).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any finding needs prospective validation before
  real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C held
  as float32 arrays for the venue-native n detector; RAM < 3 GB. Runs >
  0.4 GB via `scripts/heavy_slot.py run --tag oc_tpfill --min-free-gb 2.0 --`.
  No commits; no edits outside research/tournament/oc_tpfill/
  (+ tests/test_oc_tpfill.py).
