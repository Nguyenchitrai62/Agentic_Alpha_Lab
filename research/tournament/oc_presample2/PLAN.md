# oc_presample2 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

## Purpose (labelled PRE-SAMPLE, fixed rules, no tuning)

Do the dip-sleeve DESIGN CHOICES made on 2021-2026 also hold on the
never-used 2017-2020 pre-sample data? oc_presample showed the frozen G2 dip
sleeve is profitable on 2017Q4-2020 with no losing year (4-phase mean). That
period is a SECOND untouched validation set. Every dip-sleeve design choice
of the deployment was selected on 2021-2026 (research/CLOSED_DIRECTIONS map,
docs/CLOSED_DIRECTIONS.md sections 1 and 6). If the same ranking of choices
holds on 2017-2020, the choices generalise; if not, they were partly fitted
to 2021-2026.

Seven fixed rows (same harness as oc_presample's G2 arm, 4 clock phases,
dip-only, R2 agent size 1, gate costs; change ONE knob per row). No parameter
may be changed after seeing a pre-sample number; extra rows must be labelled
post-hoc.

## Rows (fixed; ONE knob each vs G2)

- G2: the oc_presample G2 arm (reproduce its numbers exactly first). B1 sizes
  mult=1/(1+n) x kd=1.7, R2 depths 2.5/3/3.5/4/5 sg, risk budget 0.442
  (=0.26*1.7, gap 0.02), gross cap G=2.0 per phase sub-account, close5 4-sg
  stop + 8-sg backstop + TP 1.0 sg + timeout at next 4h open, stop-first,
  live offsets 16..238, gate costs (maker 0.0002 / taker 0.00055, longs pay
  0.0001 per 8h settlement held).
- NOB1: no corr-aware sizing (mult = 1 instead of 1/(1+n)). Weight
  w = U*kd with U = 0.25*1.75/4/1.657, kd = 1.7. Budget/cap/exits unchanged.
- KD13: dip multiplier kd = 1.3 instead of 1.7. Budget scales with it as in
  the deployment rows D13BF / G2K20: budget = 0.26*kd = 0.338 (gap 0.02
  unchanged). Gross cap G = 2.0 unchanged. Sizing w = U*1.3/(1+n).
- KD20: dip multiplier kd = 2.0 instead of 1.7. Budget = 0.26*2.0 = 0.52.
  Gross cap G = 2.0 unchanged. Sizing w = U*2.0/(1+n).
- NOCAP: no gross cap (G = none; budget-only). All else = G2.
- TOUCH: touch stop at 4 sg instead of the close5 stop (+8 sg backstop
  unchanged). Stop trigger: first t in f+1..239 with low(t) <= sl
  (sl = lv*(1-4*sg)) -> exit at min(sl, open(t)) taker 0.00055 (gap pays the
  open, min() worse for a long; NaN open -> rung dropped). Priority
  unchanged (stop-first: backstop wins ties kb<=ks,kt; else TP only if
  kt<ks; else stop; same-minute stop+TP -> stop). TP/timeout/fees/funding
  unchanged.
- TP15: take-profit tp = lv*(1+1.5*sg) instead of lv*(1+1.0*sg). Exit at tp
  maker+mfill on first high > tp (STRICT). All stops/timeout/priority/fees
  unchanged.

Fills are identical across G2/NOB1/KD13/KD20/NOCAP by construction (same lv
fill rule; only sizing/budget/cap differ post-fill). TOUCH/TP15 share the
same fills (same lv rule); only the exit race differs.

## Research-year expectations (cited; the rank table tests these)

In the research years (2021-2026 window) these choices were judged:

1. G2 > NOB1: v399/B1 corr-aware size x1/(1+n) KEPT: DD 25.05 -> 13.88,
   R 4.82 -> 4.55 (docs/CLOSED_DIRECTIONS.md section 1, `v399/B1` row).
   Expectation on pre-sample: NOB1 earns equal-or-more per-fill but at much
   higher DD (rank: DD G2 < NOB1).
2. D17 between D13 and K20 on the return/DD frontier: v411/D17BF KEPT deploy
   5.425/DD18.33/16.90 (CLOSED section 1); v424 R2B1D13BF frontier 4.97/14.98
   (CLOSED section 6, `v424` row); v407 dips x2.0 CLOSED 5.78 but DD 20.95
   breach (CLOSED section 1, `v407` row); oc_saturation G2K20 5.874/17.79
   saturate (CLOSED section 12, `oc_saturation` row). Expectation: return
   KD13 < G2(kd1.7) < KD20 and DD KD13 < G2 < KD20 (monotone frontier).
3. Cap = same return with less tail: v421/G2 dip gross cap 2.0x KEPT deploy:
   same R 5.41, DD -1.4pp, gap-through -10% stops 58% -> 33.5% (CLOSED
   section 1, `v421/G2` row). oc_crash2020 showed G2 == NOCAP bit-for-bit in
   all 40 crash-window cells (oc_presample PLAN.md section Replica, Arm).
   Expectation: NOCAP ~= G2 on return, DD NOCAP >= G2 (cap binds calm
   markets, not crashes; oc_presample REPORT sections Leakage / Key
   question: peak gross 2.07 Y2020p s2, 2.66 R4 s1).
4. close5 > touch: deployed close5 stop stands. Closest tested faster stops:
   oc_stoptf S1 (every-1m close) sums only 2/5, DD 5/5 -> NOT PROMISING
   (CLOSED section 11, `oc_stoptf` row; REPORT: S1 fires ~1.5-2x more stops,
   bleeds 2023/2024/2025); oc_marktrig mark-trigger stops sum 4/5 but tails
   2/5 (CLOSED section 11, `oc_marktrig` row). TOUCH (1m-low touch) is
   strictly faster than S1 close1, so the research prior is close5 >= TOUCH
   on return with more stops under TOUCH.
5. TP 1.0 > 1.5: deployed TP 1-sg stands. oc_dipexit 4 alternative TP exits
   all fail; E1 split 0.5+1.5 sums 0/5 (CLOSED section 1, `oc_dipexit` row;
   REPORT: E1 0/5, E4 reversion-cap 2/5 with worse worst-day all 5 yrs);
   oc_tpbyn TP1.5 iff n>=2 gains 2023-25 only, fails 4/5 rule (CLOSED
   section 1); oc_deeptp 1/5 both legs keep TP1.0; oc_beartp sum 0/5.
   Expectation: TP10 >= TP15 on pre-sample return.

Rank table (in REPORT.md): for each of the 5 judgements above, state the
research-year direction + numbers, then the pre-sample direction (AGREE /
DISAGREE / PARTIAL), row by row.

## Data (frozen; reuse oc_presample's stores, no new download)

- Pre-sample legs: data/raw/spot_1m_presample_20261007 (Binance SPOT 1m
  2017-08..2020-09, BTC/ETH/BNB/XRP; SOL absent; every monthly zip
  sha256-verified; manifest.json). Read-only; copy nothing, edit nothing.
- Archive artefacts handled EXACTLY as oc_presample (floored sub-minute real
  rows, dropped flat zero-volume filler rows) because the packed parquets
  already contain the fix; the replay core is unchanged (no volume filter).
- G2 fidelity gate (BEFORE any pre-sample number is looked at): run the
  copied core with G2 knobs on oc_presample's four pre-sample legs and
  require bit-for-bit agreement with research/tournament/oc_presample/
  results.json presample cells Y2017/Y2018/Y2019/Y2020p s{0..3} on all
  simulate-level fields (end_equity, min_marked, max_loss_pct, max_dd_pct,
  pct_per_month, peak_gross, fills, stops, tps, timeouts, wins, win_rate,
  gap_stops, gap_max, worst_minute, worst_day, worst_day_ret, n_days). If it
  mismatches, stop and report; no other row is computed.

## Replica (oc_presample G2 arm + ONE knob per row; verbatim core copy)

- 4h grid: ORIGIN = 2020-01-01 00:00 UTC, bar j of phase s covers
  [ORIGIN + s h + 4h*j, +4h) for ALL integer j (negative j extends back to
  2017, identical to oc_presample/oc_crash2020 grids). Phases s in
  {0,1,2,3}. Bar offsets 0..239; next-bar open offset 240.
- sigma_4h per coin per phase at bar j (known at bar OPEN): simple returns
  r_b = O_b/O_{b-1}-1 of 4h bar opens; sigma(j) = std(r over 360 bars ending
  at j-1, min_periods 120, ddof=1) = crash.compute_sigma verbatim (copied,
  not imported). Bars with non-finite O_j or sigma <= 0/NaN skipped.
  Warm-up: no trading before (first finite bar open of that coin) + 60 days
  (BTC/ETH 2017-10-16, BNB 2018-01-05, XRP 2018-07-03; logged per coin).
- Rungs k in {2.5,3.0,3.5,4.0,5.0}. Level lv = O_j*(1-k*sg). Resting limit
  BUY, live window offsets 16..238. Fill at FIRST f with low(f) < lv
  (STRICT trade-through). Fill price = lv, maker 0.0002. At most one fill
  per (bar, coin, k).
- Correlation count at fill (B1, v399-exact, causal, coins-present-only):
  n(a,T,f) = number of OTHER majors b (of available coins) with finite
  O_b(T), finite C_b(T+f-1), finite sg_b(T) > 0 AND
  C_b(T+f-1) <= O_b(T)*(1-2.5*sg_b(T)) (only closes up to minute f-1).
- Sizing per row: w = mult*kd*u with u = 0.25*1.75/4/1.657, mult =
  1/(1+n_fill) except NOB1 mult = 1, kd per row (1.7 / 1.3 / 2.0). R2 agent
  size = 1.0, scale = governor = 1.0 (labelled; no walk-forward tables
  pre-2020).
- Risk budget (engine-exact): candidates processed in (f, r, a) order; keep
  iff risk_open + w*(4*sg+gap) <= budget, gap = 0.02, budget = 0.26*kd
  (G2/NOB1/NOCAP/TOUCH/TP15: 0.442; KD13: 0.338; KD20: 0.52).
  risk_open sums w*(4*sg+gap) of rungs still open (exit offset > f).
- Gross cap per row: G2/KD13/KD20/TOUCH/TP15/NOB1 G = 2.0 per phase
  sub-account (room = 2.0 - sum of open notionals; w = min(w, room); skip if
  room <= 1e-12); NOCAP G = none.
- Post-fill exits (long) from lv: sl = lv*(1-4*sg), bl = lv*(1-8*sg),
  tp = lv*(1+TPMULT*sg) with TPMULT per row (1.0 except TP15 1.5), evaluated
  on t in f+1..239 then timeout at 240: backstop touch (first low <= bl)
  exits at min(bl, open(t)) taker; else TP touch (first high > tp, STRICT)
  exits at tp maker+mfill; else stop (G2-family: close5 clock (m+1)%5==0,
  first close <= sl, exit at open(m+1) or o2 if m==239, taker; TOUCH row:
  first low <= sl, exit at min(sl, open(t)), taker) else timeout at next-bar
  open o2 taker + funding 0.0001 iff (T+4h).hour in (0,8,16). Priority
  stop-first (backstop wins ties kb <= ks, kt; else TP only if kt < ks; else
  stop). Same-minute stop+TP -> stop. Gate fees maker 0.0002 / taker
  0.00055. Ret fractions of lv. NaN exit price -> rung dropped.
- Spot-vs-perp caveat (labelled on every table): fills/exits evaluated on
  SPOT prices while fees/funding are the perp gate costs.

## Years and metrics (PRE-SAMPLE labelled)

- Pre-sample years (each, per phase, equity starts 1.0 flat, compounds per
  bar within the year, reset per year): Y2017 = [2017-10-16, 2018-01-01)
  (BTC+ETH only in 2017; BNB from warm-up if inside; XRP absent),
  Y2018 = [2018-01-01, 2019-01-01), Y2019 = [2019-01-01, 2020-01-01),
  Y2020p = [2020-01-01, 2020-09-01) (rungs opened on bars with open in the
  interval; exits may realise in the first bar of the next month).
- Per (row, year, phase): %/month geometric on full equity =
  100*(E_end^(30.4375/N_days)-1), N_days = calendar days of the interval
  (Y2017: 77, Y2018: 365, Y2019: 365, Y2020p: 244); max DD % from 1m-marked
  equity M(t) = bar-open E*(1+sum w*(C(t)/lv-1)) including open positions
  (peak-to-trough from 1.0, NaN closes hold last mark as in oc_presample);
  fills, stops (close5/touch+backstop), TPs, timeouts, win rate = fraction
  of fills with ret > 0 (after costs), peak gross, end equity.
- Per (row, year): 4-phase MEAN %/month (arithmetic mean of per-phase
  %/month), MEAN DD (mean of per-phase max DD), WORST-phase DD (max of
  per-phase max DD), fills/stops/TPs/timeouts sums, pooled win rate
  (total wins / total fills), end-equity mean. (Mean-of-mins is a
  pessimistic proxy of the true 1/4-equity mix; labelled, same as
  oc_presample.)
- Rank table: research direction vs pre-sample direction per judgement
  (1)-(5) above + per-year winner tables.

## Protocol / resources

- PLAN.md written before any outcome computation (this file). Scripts live
  ONLY in research/tournament/oc_presample2/: presample2.py (pure-numpy
  core copied from oc_presample/presample.py + row knobs + per-year driver
  -> tmp/rows.json). Outputs: results.json, REPORT.md (tables + rank table
  + 3-line Vietnamese verdict), results ledger checksum. Scratch under tmp/
  only. Data folder is read-only (no new download needed).
- RAM: one coin's 1m slice per year-chunk in RAM at a time (float32);
  per-year sequential bars; data loaded ONCE per leg, all 7 rows simulated
  from the same in-RAM arrays. Any step expected > 0.4 GB goes through
  scripts/heavy_slot.py (tag oc_presample2, never --leader). One process.
- Tests: tests/test_oc_presample2.py (synthetic hand checks: strict fill,
  stop-first, funding, budget scaling per kd, cap cut, NOB1 sizing,
  TOUCH-vs-close5 on a whipsaw path, TP15-vs-TP10 on a mid path;
  causality: sigma excludes the bar, n uses only closes up to f-1;
  truncation: legs open rungs only on bars with open in [S, E)). Run with
  .venv/Scripts/python.exe -m pytest tests/test_oc_presample2.py -q.
- Leakage statement (fixed-rule replay, no fitting): no parameter is fit on
  any data here; all rule constants are copied from the 2020-08..2026-09
  research window (kd/budget/cap/stop/TP levels), hence pre-sample years are
  out-of-sample for the RULES (in the "no selection saw them" sense).
  Feature timing (sigma/n/fill/exit), fit windows (none) and fill timing
  are checked in REPORT.md.
- Gate costs: maker 0.0002, taker 0.00055 (stops and market exits taker),
  longs pay 0.0001 per 8h settlement held (00/08/16 UTC), shorts n/a
  (long-only sleeve). Limit fills only on strict 1m trade-through; no fill
  in minutes 0..15. Stop+TP same 1m bar -> stop first.
- No commits; no edits outside research/tournament/oc_presample2/
  (+ tests/test_oc_presample2.py). Git is read-only.
