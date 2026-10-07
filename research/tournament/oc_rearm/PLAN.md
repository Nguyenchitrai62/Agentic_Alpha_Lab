# oc_rearm PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #67: dip rung RE-ARM (aims at RETURN, the missing stretch metric).

## Hypothesis (fixed here)

Today each dip rung bid fills at most once per 4h bar: after a fill, the rung
is done for the bar even when its take-profit fires early and the price
re-dips through the same bid level. Hypothesis: re-placing the same rung bid
(same price, same B1 size recomputed with the live number of flushing majors)
from the next minute after its take-profit fills, for at most one second fill
in the same bar, adds positive-expectancy trades and raises the yearly
size-weighted sum at no material tail cost. Pre-registered direction: the
re-arm rule beats the base on 4-phase-mean yearly sums with maxDD not worse
by more than 1 pp and re-armed fills winning >= 60%. Fixed rule, no fitted
parameters.

## Universe and years (fixed)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths).
- Bars: 4 clock phases s in {0,1,2,3}h (dip results swing with the 4h phase):
  phase-s bar j covers [START_s + 4h*j, START_s + 4h*j + 4h) with
  START_s = 2020-08-01 00:00 UTC + s hours. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full H/L in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector;
  RAM < 3 GB.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens ON THE SAME phase grid; sigma = std(r over 360 bars ending at T-1,
   min_periods 120, ddof=1) = v293/oc_dipexit/oc_b1deeper definition. Known
   at the bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped
   (no rungs that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)). B1 (size only,
   oc_b1deeper arm B1 exact replica): resting limit BUY at lv, live offsets
   16..238. Fill at FIRST offset f with low(T+f) < lv (STRICT trade-through).
   Fill price = lv. n_fill = n(a,T,f) at its own fill minute (item 3).
   size w = 1/(1+n_fill).
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   oc_b1deeper/v399-exact): n(a,T,m) = number of OTHER majors b != a with
   finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). At the fill minute this uses closes up to
   m-1 only (same as v399_corr_dip_size at m = f-1).
4. Post-fill exits (long), oc_b1deeper D0 replica measured from the fill
   price px (= lv for every fill here): sl = px*(1-4*sg),
   bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes t in
   f+1..239 then timeout at 240 (next-bar open o2 = 1m open at T+240):
   backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
   taker; else TP touch (first t with high(t) > tp, STRICT) exits at tp
   maker; else close5 stop (clock minutes m with (m+1)%5==0, first m with
   close(m) <= sl) exits at open(m+1) (or o2 if m=239) taker; else timeout
   at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16). Priority
   stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP wins only if
   strictly earlier (kt<ks); else stop; else timeout. A stop and TP in the
   same minute -> stop wins. Fees: fill maker 0.0002; TP leg maker 0.0002
   (total 2*maker on TP); stop/backstop/time legs taker 0.00055. Net
   returns are fractions of px. Fills whose exit price is missing (NaN
   open, NaN o2 on a stop-at-239/timeout path) give NaN net and are DROPPED
   (base and re-armed identically).
5. RE-ARM rule (fixed, bot-executable): for each (phase, bar T, coin a,
   rung k) with a kept base fill (f, exit x, how): iff how == "tp" (the
   take-profit touched strictly inside the bar, x in f+1..239), the same
   rung bid at the SAME price lv is re-placed from the NEXT minute x+1 and
   may fill ONCE more in the same bar: f2 = first offset in [x+1, 238]
   with low(T+f2) < lv (STRICT; empty -> single fill). Max 2 fills per rung
   per bar: a re-armed fill never re-arms again even if it TPs. Its size is
   the same B1 rule recomputed at its own fill minute: w2 = 1/(1+n(a,T,f2)).
   Its exit is item 4 from f2+1 with px = lv. If the base exit is a stop,
   backstop or timeout (or the base fill is dropped/capped to zero), there
   is no re-arm. All inputs to the re-arm (TP touch at x, low at f2,
   n(f2) from closes up to f2-1) are observable at or before f2.
6. Gross cap G = 2.0 (engine_user `sleeve_gross_cap` replica): per (phase,
   holding bar), pool the arm's candidate fills across all coins/rungs
   (base arm: base fills; rule arm: base + re-armed fills), sort by
   (fill offset f ASC, rung k ASC, coin ASC), and walk in order keeping
   engine state: open_w = sum of kept w of fills with exit x > f (a fill
   whose exit minute has passed is observably closed; one with x > f is
   still open); room = 2.0 - open_w; skip when room <= 1e-12, else keep
   w_kept = min(w, room) (cut to room, engine-exact). A re-armed candidate
   whose parent base fill kept 0 is dropped (no position, hence no TP).
   Both arms run under the identical G = 2.0, so the comparison isolates
   the re-arm. Weights here are B1 size_mult units, not equity fractions;
   the cap therefore binds only in crowded bars (disclosed).
7. Scoring (PRIMARY = raw exposure, no renormalisation, because the re-arm
   changes exposure by construction and the assignment tests added P&L):
   contribution = w_kept * y per kept fill (w_kept = 0 fills contribute 0
   and count as no trade). Daily sums per (phase, arm, year): group w*y by
   EXIT date (calendar UTC date of T+x, x = exit offset, 240 = next-bar
   open date). Yearly sum S = sum of daily sums. Worst day W = min daily
   sum. Cumulative path over exit dates sorted ascending from 0:
   C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q)) in w*y units (0 when
   monotone non-decreasing). 4-phase mean per year: mean over s of S, of
   trade count, of W, of maxDD. Win rates and the re-armed P&L share pool
   fills across the 4 phases per year: win = fraction of kept fills with
   y > 0 strictly; re-armed share = re-armed w*y / rule-arm total w*y
   (0/0 -> 0). Side row only: renormalised (w' = w/mean(w per
   phase-year-arm)) sums, to check the verdict does not hinge on exposure.

## Decision rule (fixed, from the assignment)

Per anchor year Y0..Y4, 4-phase means: S_base(Y), S_rule(Y), DD_base(Y),
DD_rule(Y); pooled re-armed win rate RW(Y) per year and RW_all pooled over
5 years x 4 phases. PASS_sum(Y) iff S_rule(Y) > S_base(Y) (strictly higher;
equal fails; NaN -> FAIL). PASS_dd(Y) iff DD_rule(Y) <= DD_base(Y) + 0.01
(not worse by more than 1 pp, where 1 pp = 0.01 in w*y sum units;
NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5 years AND
(b) PASS_dd in >= 4 of 5 years AND (c) RW_all >= 0.60. Otherwise
NOT PROMISING. One-line verdict in REPORT.md. The generic tournament
default rule (same sign 4/5 + LOOY 4/5) is superseded by this
assignment-specific rule.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts: `rearm.py`
  (vendored copy of oc_b1deeper deeper.py pure-numpy core: n vector,
  static fill, D0-from-fill exit, identical constants, plus the re-arm
  search and the G = 2.0 open-notional cap walk), `run_rearm.py`
  (per-coin loop x 4 phases, base ledger + re-arm candidates + per-bar cap
  -> results.json). Outputs: results.json, REPORT.md (tables + one-line
  verdict). Tests: `tests/test_oc_rearm.py` (synthetic hand checks: re-arm
  only after an inside-bar TP, no re-arm after stop/timeout, max 2 fills,
  size recomputed at f2, cap cut-to-room and parent-skip drop, scoring
  helpers).
- No commits; no edits outside research/tournament/oc_rearm/
  (+ tests/test_oc_rearm.py).
