# oc_outage PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

## Status

DIAGNOSTIC for operations. No rule selection, no PROMISING graduation, no
deployment change. All five anchor years are research data (market data up to
2026-09-24 00:00 UTC is read per the assignment); any guidance needs
prospective confirmation before real money. Disclosed against
research/tournament/RULES.md 2 / VF_COMMON hidden-year conventions.

## Question (fixed here)

The deployed BOT (R2B1D17BF/G2 family, docs/BOT_EXECUTION.md,
docs/DEPLOYMENT_PLAN_VI.md) needs the bot online 24/7 across 4 clock phases.
What happens to the dip sleeve when the bot is offline for a bounded time?
While offline (BOT_EXECUTION.md § Failure modes + assignment): no NEW rung
bids are placed (bids already resting stay and can fill until their window
ends); fills that happen keep their native TP limit and native 8-sigma
conditional-market backstop on the exchange; the bot's close5 4-sigma software
stop (market exit on a CLOSED 5m bar close) and the time exit (market at the
bar end) do NOT run while offline and only act when the bot is back (first
minute after the outage, at that minute's open).

## Base replica (frozen: D0 exits + B1 sizes, 4 clock phases)

Exact replica of research/tournament/oc_dipexit/PLAN.md D0 (code logic copied
verbatim into `outage_core.py`, no import from other workers) with
oc_b1deeper-exact B1 sizes, on all four clock phases (oc_usdtdip convention):

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill, never trigger
  an exit touch, and never count as flushing; a fill whose timeout open is
  NaN is dropped (same as oc_dipexit).
- Four clock phases p in {0,1,2,3}: 4h grid of bars covering
  [START + p*1h + 4h*j, START + p*1h + 4h*j + 4h) with
  START = 2020-08-01 00:00 UTC. Phase 0 == the oc_dipexit grid exactly.
  Bar j has 240 minute offsets 0..239; next-bar open is offset 240. Only
  bars with open T in [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded
  (5 years Y0..Y4 = [anchor, anchor+365d), anchors 2021-09-24..2025-09-24,
  keyed by bar-open T; Y4 = [2025-09-24, 2026-09-24) = 365d).
- sigma_4h per coin at bar open T (known at T): simple returns
  r_b = O_b / O_{b-1} - 1 of that phase's 4h bar opens;
  sigma(T) = std(r over 360 bars ending at T-1, min_periods 120, ddof=1)
  (= v293/oc_dipexit; shift(1) so the bar itself is excluded). Bars with
  non-finite O, sigma <= 0 or NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level
  lv = O(T) * (1 - k*sigma(T)). Resting limit BUY at lv, live window
  offsets 16..238 inclusive. Fill at the FIRST offset f with
  low(T+f) < lv (STRICT trade-through). Fill price = lv, maker 0.0002.
  At most one fill per (bar, k).
- B1 size (oc_b1deeper-exact, causal: uses only closes up to minute m-1):
  n(a,T,m) = number of OTHER majors b != a with finite O_b(T),
  finite C_b(T+m-1), finite sg_b(T) > 0 AND
  C_b(T+m-1) <= O_b(T) * (1 - 2.5*sg_b(T)) (<= counts; NaN = not
  flushing; own coin never counted, 0..4). At the fill minute f,
  n_fill = n(a,T,f); w = 1/(1+n_fill).
- Post-fill exits (long), oc_dipexit D0 replica from fill price lv:
  sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1.0*sg), on minutes
  t in f+1..239 then timeout at 240 (next-bar open o2):
  backstop touch (first t with low(t) <= bl) exits at min(bl,open(t))
  taker 0.00055; else TP touch (first t with high(t) > tp, STRICT) exits
  at tp maker (total 2*maker with the fill leg); else close5 stop (clock
  minutes m with (m+1)%5==0, first m with close(m) <= sl) exits at
  open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
  0.0001 if (T+4h).hour in (0,8,16) (v293 settle rule; no funding on
  intrabar exits). Priority stop-first: backstop wins ties
  (kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks);
  else stop; else timeout. Stop and TP in the same minute -> stop wins.
  Net returns are fractions of lv. Fills with non-finite exit nets are
  DROPPED.

Base ledger source (frozen, no recomputation of fills): the validated
4-phase D0+B1 ledger `research/tournament/oc_usdtdip/panel.parquet`
(base arm columns: phase/sym/T/bar_ord/rung_k/f/n_fill/w_base/y/x/exit
date), which is the replica above on all 4 phases (its phase-0 raw sums
are cross-checked against oc_dipexit/oc_b1deeper refs in results.json).
This study applies the outage overlay to that ledger and recomputes exits
with exact 1m slices ONLY for fills whose base exit falls inside an outage
(see below); all other fills keep their base outcome bit-for-bit. Rationale:
keeps the run LIGHT (no full 1m replica; peak < 0.4 GB so no heavy_slot),
while deferred exits stay exact.

## Outage model (frozen)

An outage is a set of wall-clock minute intervals [s, e) (s inclusive,
e exclusive; bot offline for minutes s..e-1, back at minute e). All 4
phases share the same UTC intervals (one bot, four clocks).

- Placement (NEW bids): a bar T's rung bids are considered placed at the
  first live minute P = T+16. If P lies in any outage interval, the whole
  bar is MISSED (no rungs of that bar for any coin/phase; w*y contributes
  0 in scenarios). Otherwise bids rest for offsets 16..238 exactly as base,
  so kept bars fill at the same f as base (fill minute needs no
  recomputation).
- Exits while offline: native TP limit and native 8-sigma backstop stay on
  the exchange and fire as in base even when their touch minute is offline.
  The close5 software stop and the time exit cannot fire while offline.
  Formal rule per kept fill with base outcome (ret0, x0, how0), Te = T+x0:
  - if how0 in (tp, backstop): scenario outcome = base (native, unchanged),
    even if x0 is offline.
  - if how0 in (stop, time) and Te is online: scenario = base.
  - if how0 in (stop, time) and Te is offline: let Ce = first online minute
    >= Te (end of the covering interval). Search native touches in the
    window (f+1 .. Ce-1) in absolute offsets (inside the bar: 1m high/low
    slices; past the bar end offset>=240: global 1m high/low at those
    absolute minutes): first TP touch (high > tp, STRICT) at xw_t, first
    backstop touch (low <= bl) at xw_b (NaN bars never touch). If either
    exists before Ce (backstop wins ties xw_b<=xw_t), the scenario exits
    there (TP: tp/lv-1-2*maker, no funding; backstop:
    min(bl,open(xw))/lv-1-maker-taker, no funding). Else the scenario
    exits at the comeback open: ret = open(Ce)/lv-1-maker-taker, minus
    FUND 0.0001 iff settling ((T+4h).hour in (0,8,16)) AND Ce-T >= 240
    (held past the bar end); if open(Ce) is NaN the fill is dropped in the
    scenario (same missing-price rule as base). Exit date for daily sums is
    the scenario exit date (comeback date when delayed).
  - Fees: maker 0.0002 (fill) + maker (TP leg) or taker 0.00055 (stop /
    backstop / time / comeback legs); funding only as above (base timeout
    funding is reproduced exactly when Ce-T == 240 and settling).
- Attribution (for the missed-vs-late split and worst-episode table): a
  missed bar is attributed to the interval covering its P; a delayed exit
  is attributed to the interval covering its Te. Intervals within one
  scenario are disjoint by construction, so attribution is unique. A fill
  is never both missed and delayed.

## Scenarios (frozen, seeded)

Per anchor year Y = [A, A+365d), A in 2021-09-24..2025-09-24 UTC:

- (a) weekly-2h: 52 weeks W_w = [A+7d*w, A+7d*(w+1)), w=0..51 (364d; the
  1-day tail [A+364d, A+365d) has no outage by construction, disclosed).
  One 120-min outage per week at a uniform random start in
  [W_w.start, W_w.end-120m). Seed 101.
- (b) monthly-6h: 12 months M_m = [A+m*43800m, A+(m+1)*43800m), m=0..11
  (43800m = 365*1440/12, exact cover of 365d). One 360-min outage per
  month at a uniform random start in [M_m.start, M_m.end-360m). Seed 102.
- (c) quarterly-24h: 4 quarters Q_q = [A+q*131400m, A+(q+1)*131400m),
  q=0..3 (131400m = 525600/4, exact cover). One 1440-min outage per
  quarter at a uniform random start in [Q_q.start, Q_q.end-1440m).
  Seed 103.
- (d) adversarial-10h: the 10 worst market hours of the year. Hourly grid
  aligned to UTC midnight (hour starts 00:00 UTC). For each hour start h in
  [A, A+365d), market return = mean over the 5 majors of
  close(h+60)/close(h)-1 from 1m closes (an hour is skipped if any major's
  endpoint close is NaN). Rank ascending (most negative first); the 10
  lowest hours become 60-min outages [h, h+60). Deterministic (no seed).
  Ties broken by earliest hour.

RNG: np.random.default_rng(seed) per scenario (a/b/c independent streams),
draws in year order Y0..Y4, block order within year, one integer per block
(start offset in minutes, uniform in the closed range above). The full
interval lists are persisted in results.json (ISO timestamps).

## Scoring (frozen; diagnostic, no selection)

- Daily sums per (arm, year, phase): group w*y by EXIT date (calendar UTC
  date of the scenario exit; base uses the panel exit date). Yearly-phase
  sum S = sum of daily sums (= sum w*y); worst day W = min daily sum;
  cumulative path over exit dates sorted ascending from 0:
  maxDD = max drawdown of the cumsum (>= 0; 0 when monotone
  non-decreasing); n = kept fills; win = fraction with y > 0 strictly.
- 4-phase means per year: Sbar(Y) = mean_p S(p,Y); DDbar, Wbar, nbar, winbar
  likewise. 5y rollup: sum of yearly 4-phase-means (dSum), plus pooled full
  path (all phases, exit-date order) sum/DD as context only.
- Per scenario vs base: dS(Y) = Sbar_scen(Y)-Sbar_base(Y); loss(Y) =
  -dS(Y); full loss = base_dSum - scen_dSum. Decomposition (sums to loss by
  construction): missed(Y) = sum of base w*y over fills missed in the
  scenario; late(Y) = sum over kept fills of w*(y_base-y_scen); shares
  missed/loss, late/loss (reported when |loss|>1e-12, else null).
  5y shares use the 5y sums.
- Worst episode per scenario: rank that scenario's intervals by episode
  loss = missed part + late part attributed to the interval (5y pooled,
  all phases); report the top-1 interval (start/end UTC, duration, year,
  fills missed, fills delayed, TP-rescued count, episode loss and its
  missed/late split) plus the top-5 list in results.json.
- Cross-checks persisted: phase-0 base raw sums vs oc_dipexit/oc_b1deeper
  refs; ledger checksum of the panel base arm; counts of fills
  missed/delayed/TP-rescued per scenario-year.

## Protocol / resources (frozen)

- PLAN.md written before any outcome computation. Then scripts:
  `outage_core.py` (pure-numpy core: verbatim D0 outcome_mu, B1 helpers,
  outage interval utils, deferred-exit recomputation, worst-hour ranker,
  cell stats; no I/O), `compute_outage.py` (loads the oc_usdtdip panel as
  the base ledger, builds seeded intervals, recomputes deferred exits with
  exact 1m slices ONLY for fills with Te offline -- one coin's 1m O/H/L/C
  in RAM at a time (float32), 4h bar opens/sigmas recomputed per phase for
  lv/sg/o2/settle --, scores base + 4 scenarios -> results.json).
  Outputs: results.json, REPORT.md (tables + one-line verdict + Vietnamese
  ops guidance). Tests: tests/test_oc_outage.py (synthetic hand checks for
  placement miss, native TP/backstop firing offline, stop/time deferral to
  comeback open, TP-winning-during-delay, funding on held-past-settle,
  seed determinism, disjointness, shares-summing-to-loss, worst-hour
  ranker, NaN handling).
- No commits; no edits outside research/tournament/oc_outage/
  (+ tests/test_oc_outage.py); no other worker files touched; panel + 1m
  inputs are read-only.
- One process; peak RAM < 0.4 GB by design (base ledger ~tens of thousands
  of rows; 1m slices one coin at a time; hourly matrix tiny), so the full
  run goes directly (no heavy_slot; heavy_slot is only for runs > 0.4 GB).
  CPU < 60 min.
- Market data up to 2026-09-24 00:00 UTC is read per the assignment (all
  five years are research data; guidance is diagnostic and needs
  prospective validation). This is disclosed against RULES.md 2 /
  VF_COMMON hidden-year conventions.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
