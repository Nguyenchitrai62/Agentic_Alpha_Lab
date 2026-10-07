# oc_condhold PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

Idea #35: conditional time exit for dip rungs. oc_holdext (hold EVERY
non-TP timeout rung one more bar) raised win rate to 0.77 but worsened DD
(full DD 1.14 -> 1.61, sum higher in only 1/5 years): the extra bar converts
timeouts into exits but the converted rungs add tail, not return.

## Hypothesis (fixed here)

A timeout rung that is already IN PROFIT at the next 4h open is a different
animal from a timeout rung sitting at a loss: letting the winner run one more
bar with the same TP/stop recovers further upside, while cutting the loser at
the open (as today) avoids holding weak tape into the tail. Hypothesis:
extending ONLY in-profit timeouts beats exiting every timeout at the next
open on yearly size-weighted sums at no worse yearly maxDD. Direction
pre-registered: CONDITIONAL beats BASE on sums at no worse maxDD. Fixed rule,
no fitted parameters, one variant only.

## Data (fixed here, all in repo - no fetch)

- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP). Minutes used:
  t <= 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths, same as
  oc_b1deeper/oc_holdext).
- Bars: standard 4h grid, bar j covers [START + 4h*j, START + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years
  Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24, keyed by
  entry bar open T).
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all five
  years are research data; any PROMISING result needs prospective validation
  before real money). Disclosed against RULES.md 2 / VF_COMMON hidden-year
  conventions.
- Resources: one process, one coin's full OHLC in RAM at a time (float32);
  all-five-coins 1m opens/closes held as float32 arrays for the n detector;
  RAM < 3 GB. Majors 1m closes of all five coins may be held as float32
  arrays per the assignment.

## Exact causal definitions (frozen)

1. Bar open: O_c(T) = 1m `open` of coin c at minute T (no ffill; NaN =
   missing). sigma_4h(c,T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar
   opens; sigma = std(r over 360 bars ending at T-1, min_periods 120,
   ddof=1) = v293/oc_dipexit/oc_b1deeper/oc_holdext definition. Known at the
   bar open T. Bars with non-finite O, sg <= 0 or NaN are skipped (no rungs
   that bar).
2. Base rung level: lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)).
3. Correlation count at minute m (live window offsets 16..238 inclusive,
   same as oc_b1deeper/oc_holdext): n(a,T,m) = number of OTHER majors b != a
   with finite O_b(T), finite C_b(T+m-1), finite sg_b(T) > 0 AND
   C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)). C uses the 1m `close` at
   minute T+m-1 (last fully closed minute; no cross-bar ffill, within-bar
   NaN stays NaN = not flushing). Own coin never counted (0..4). Flush at
   exactly 2.5 sigma counts (<=). v399-exact, copied from oc_b1deeper.
4. Entry (BOTH arms, oc_b1deeper B1 / oc_holdext BASE replica): resting limit
   BUY at lv, live offsets 16..238. Fill at FIRST offset f with low(T+f) <
   lv (STRICT trade-through). Fill price px = lv, fee maker 0.0002. At most
   one fill per (bar, coin, k). n_fill = n(a,T,f). size w = 1/(1+n_fill)
   (B1 size, both arms; entries identical so the comparison is a pure paired
   exit test).
5. BASE exits (long), oc_b1deeper/oc_holdext D0 replica measured from px:
   sl = px*(1-4*sg), bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on
   minutes t in f+1..239 then timeout at 240 (next-bar open o2 = 1m open at
   T+240): backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
   taker; else TP touch (first t with high(t) > tp, STRICT) exits at tp
   maker; else close5 stop (clock minutes m with (m+1)%5==0 on the absolute
   offset-from-T clock, i.e. 4,9,...,239; first m with close(m) <= sl) exits at
   open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
   0.0001 if (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
   (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks); else
   stop; else timeout. A stop and TP in the same minute -> stop wins. Fees:
   fill maker 0.0002; TP leg maker 0.0002 (total 2*maker on TP);
   stop/backstop/time legs taker 0.00055. Net returns are fractions of px.
   Longs pay 0.0001 per 8h settlement held (gate rule; shorts are not traded
   here).
6. CONDITIONAL exits: if the BASE race ends in tp/stop/backstop (how !=
   "time"), the conditional outcome IS the base outcome (same exit, same
   net; no second-bar data needed; cond_extended = False). If and only if
   BASE how == "time", apply the profit gate at the mid open o2 (known at
   T+240, causal):
   IN_PROFIT iff base_ret > 0 STRICTLY, i.e.
   o2/px - 1 - MAKER - TAKER - (FUND if settle_mid else 0) > 0,
   equivalently mark o2 above fill px plus round-trip fees plus any funding
   due at the mid settlement. NaN o2 gives NaN base_ret (pair dropped, never
   gated). Numerical guard (no economic effect): binary-float dust within
   1e-12 of exactly flat counts as flat (gate FALSE).
   - Gate FALSE (at a loss or exactly flat): exit at o2 as today; cond =
     base (cond_extended = False).
   - Gate TRUE (in profit): the rung keeps the SAME sl/bl/tp levels (frozen
     from the original px and sg; the backstop stays on as the catastrophic
     stop) and is evaluated over the next bar's minutes t in 240..479
     (offsets from T; H/L/C/O of the same coin, NaN = no touch): backstop
     (first t with low(t) <= bl) exits at min(bl,open(t)) taker; else TP
     (first t with high(t) > tp, STRICT) exits at tp maker; else close5 stop
     (clock minutes m in 240..479 with (m+1)%5==0, i.e. the same wall-clock
     grid, first m with close(m) <= sl) exits at open(m+1) (or o3 if m=479)
     taker; else timeout at o3 = 1m open at T+480 taker. Same stop-first
     priority as BASE (backstop wins ties; TP only if strictly earlier than
     the stop; same-minute stop+TP -> stop). Same per-leg fees. Funding:
     every extended exit held through the mid open T+240 pays mid_fund =
     0.0001 if settle_mid; an extended timeout at o3 additionally pays
     0.0001 if settle_final = (T+8h).hour in (0,8,16) (0, 1 or 2 x 0.0001
     total). Identical to the oc_holdext extended leg; only the GATE is new.
7. Kept fills (PAIRED): a fill is kept iff BOTH its base net and its
   conditional net are finite. (Non-timeout fills and gate-FALSE timeouts
   need no second-bar data, so both are finite together; gate-TRUE timeouts
   near the data end or with missing second-bar exit prices drop as pairs,
   keeping the arms exactly comparable.) Fills with no fill (no
   trade-through) are not rows.
8. Year key: bar-open/entry year (T in [anchor, anchor+365d)). Daily sums per
   arm per year: group w*y by EXIT date (calendar UTC date of T+x, where
   x = exit offset; 240 = next-bar open date, 480 = bar-after-next open
   date; extended exits can print days after T's year but stay attributed to
   the entry year). Yearly sum S = sum of daily sums. Worst day W = min
   daily sum. Cumulative path over exit dates sorted ascending from 0:
   C_k = cumsum; maxDD = max(0, max_{p<q}(C_p-C_q)) in w*y units (0 when
   monotone non-decreasing). Efficiency E = S/maxDD (NaN when maxDD == 0).
   Win rate = fraction of kept fills with y > 0 strictly (equal-weight).
   Timeout share = fraction of kept fills exiting as "time" (BASE: base
   timeouts; COND: residual timeouts at o2/o3). Extended share = fraction of
   kept fills with cond_extended True. Gate-TRUE share among base timeouts
   reported descriptively.

## Decision rule (fixed, from the assignment's NEW-idea paragraph)

Per anchor year Y0..Y4: S_base(Y), S_cond(Y), DD_base(Y), DD_cond(Y), all on
the paired w*y sums. PASS_sum(Y) iff S_cond(Y) > S_base(Y) STRICTLY (equal
fails; NaN -> FAIL). PASS_dd(Y) iff DD_cond(Y) <= DD_base(Y) (not worse;
equal passes; NaN -> FAIL). PROMISING iff (a) PASS_sum in >= 4 of 5 years
AND (b) PASS_dd in >= 4 of 5 years. Otherwise NOT PROMISING. One-line
verdict in REPORT.md. Descriptive only: fills, win/win-rate, timeout shares,
gate-TRUE share, worst days, efficiencies, full-path sums/DD,
leave-one-year-out sign stability of the sum difference (LOO in >= 4/5
reported as context per the generic assignment rule, not part of the gate).

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then scripts:
  `condhold.py` (pure-numpy core: n vector copied from oc_holdext, static
  fill, D0 base exit, profit gate, extended-bar leg), `run.py` (per-coin
  loop, paired fill ledger + exit-day sums -> results.json + fills.parquet).
  Outputs: results.json, REPORT.md (tables + one-line verdict). Tests:
  `tests/test_oc_condhold.py` (synthetic hand checks: gate boundary at
  zero, gate with/without mid funding, gate-FALSE needs no second bar,
  gate-TRUE TP/stop/timeout with mid+final funding, stop-first priority,
  clock continuity, paired-drop rule + causality: fill uses only m-1
  closes; sigma excludes the bar).
- No commits; no edits outside research/tournament/oc_condhold/
  (+ tests/test_oc_condhold.py).
