# PLAN.md — oc_lit_calendar (pre-registered BEFORE any outcome; calendar book gates H1+H2+H7)

Assignment: `docs/opencode/OPENCODE_W_oc_lit_calendar.md` + common header
`docs/opencode/OPENCODE_W_COMMON_20261007.md` + shared engine protocol
`docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Specs: `docs/opencode/IDEAS4_20261007.md` §C, items H1 (TOM), H2 (overnight
21-23 UTC), H7 (halving clock). Binding windows/thresholds/leakage notes from
§C are used EXACTLY unless an operability fix is declared below (fixed here,
before any outcome). Data span required: 2021-09-24 .. 2025-09-23 — all three
Hs are calendar-only (no new data), so nothing is skipped for missing data.

## Pre-registered variants (ONLY these; no others, no tuning)

Base everywhere: G2 = `R2B1D17BFG2` (rule inv, k 1.0, kd 1.7, bear True, G 2.0),
loaded from `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl`.
Must reproduce `v421_result.json` G2 to the digit first (5.41 %/mo 5y reset
mean, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
[2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9]), else stop.

Gate mechanism (verbatim `v426/v426_book_brake.py`): per-(T,sym) multiplier on
STANDARD book rows AFTER the v410 bear-book filter (longs x0.5 where BTC 4h
open < rolling-1200 mean, min_periods 600) and BEFORE the shifted-clock
forward fill. Rows before 2021-09-24 never gated (v426 convention). Dip sleeve
untouched except H7-G2 (below). Costs/fills/funding handled by the engine:
maker 0.0002, taker 0.00055, longs pay 0.0001/8h settlement (00/08/16 UTC),
shorts zero; limits fill only on 1m trade-through; no fill in the first 5 min
after a 4h close; stop-first on same-bar SL+TP.

### H1. Turn-of-month risk window (§C-H1, Lakonishok-Smidt)

- TOM days (crypto trades daily, so "last trading day" = last calendar day):
  for month M with last calendar day L(M), TOM = {L-1, L, 1st, 2nd, 3rd}
  as UTC calendar dates (5 days; Dec/Jan cross-year handled by date logic).
- A STANDARD 4h bar T (start time) is TOM-IN iff `T.date()` is a TOM day.
  Calendar only, known decades ahead; Vasileiou optimisation NOT used.
- V1: mult 1.0 on TOM-IN bars, 0.85 otherwise (both sides, all syms).
- V2: mult 1.0 on TOM-IN bars, 0.70 otherwise (both sides, all syms).
- V3 (asymmetric; §C "long-only TOM boost (shorts x0.5 outside TOM)"):
  longs 1.0 TOM-IN / 0.85 otherwise; shorts 1.0 TOM-IN / 0.50 otherwise.
  (Interpretation fixed here: V3 longs follow V1, shorts cut harder outside;
  shorts are never boosted above 1.0.)

### H2. Overnight session filter (§C-H2, 21-23 UTC paper window)

- Operability fix (pre-registered, before outcomes): the literal §C phrase
  "bars fully inside 21:00-23:00 UTC" yields ZERO bars on the STANDARD 4h grid
  (starts 00/04/08/12/16/20 UTC), so no engine test would exist. The operable
  analogue fixed here: a bar is IN iff its holding interval [T,T+4h) OVERLAPS
  the window. UTC timestamps only, window frozen ex-ante from the paper.
  Human-schedule MANUAL variant excluded per §C.
- S1: window [21:00,23:00): IN iff T.hour == 20 (the 20:00-00:00 bar).
  Longs 1.0 IN / 0.75 otherwise; shorts 1.0 always (hedge kept per v397).
- S2 ("longs-only in window, shorts unchanged"): window [21:00,23:00):
  IN iff T.hour == 20. Longs 1.0 IN / 0.0 otherwise (flat outside);
  shorts 1.0 always.
- S3 (wider late-US+early-APAC window [21:00,01:00)): IN iff T.hour in (20,0)
  (bars 20:00-00:00 and 00:00-04:00). Longs 1.0 IN / 0.75 otherwise;
  shorts 1.0 always.

### H7. Halving-clock regime (§C-H7)

- Halvings hard-coded (public schedule): 2012-11-28, 2016-07-09, 2020-05-11,
  2024-04-19. D(T) = (T.date() - last halving date <= T.date()).days.
  Window frozen; no Stock-to-Flow exponent.
- G1: D in [400,900] (inclusive) -> book mult 0.75 (both sides, all syms),
  else 1.0. Dip untouched.
- G2: book same as G1 (0.75 both sides in [400,900]) PLUS dip budget
  0.26 -> 0.20 in window, implemented as dip fill-size scale
  0.20/0.26 = 0.7692307692 applied per holding bar whose start T is in the
  window (time-varying `sleeve_fill_size` multiplier on the shifted clock;
  budget caps G/gross unchanged). Outside the window dip scale is 1.0.
- G3: book 0.75 (both sides) for D in [525,900] (clock-paper top-to-bottom),
  else 1.0. Dip untouched.

Dip sleeve untouched for all variants except G2 (and its control, below).

## Exposure-matched controls (one per variant; timing vs mere exposure)

Per §template methodology lesson 3: for each variant V, control C_V applies a
CONSTANT per-year multiplier equal to V's realised mean multiplier on the
affected side that year (computed on the STANDARD bear-filtered index, same
cells the gate could touch; no cross-year peek; 2025 constants from 2025 only):

- V1/V2/G1/G3 (uniform both sides): c_y = mean mult over all standard cells
  that year; control applies c_y to every cell (longs+shorts) that year.
- V3 (split sides): cL_y = mean mult on long cells (w_base>0), cS_y = mean
  mult on short cells (w_base<0); control applies cL_y to all longs / cS_y to
  all shorts that year.
- S1/S2/S3 (longs-only): cL_y = mean mult on long cells that year; control
  applies cL_y to all longs that year, shorts 1.0 (same as variant shorts).
- G2: book control as uniform c_y (like G1) PLUS dip constant d_y = realised
  mean dip scale that year (fraction of in-window holding bars -> weighted
  mean of 0.7692/1.0); control dip fills are scaled by constant d_y all year.
  (Isolates timing of both legs vs flat exposure cut.)

Control rows: C_V1 C_V2 C_V3 C_S1 C_S2 C_S3 C_G1 C_G2 C_G3 (9).
Engine rows total: G2 + 9 variants + 9 controls = 19 rows
(V1 V2 V3 S1 S2 S3 G1 G2halv G3 + controls; the halving G2 row is named G2H to
avoid collision with the G2 reference in code).

## Selection (dev4 ONLY) and most-recent-year rule

- Dev4 anchors: 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24;
  each year = [A, A+365d). Metrics: `reset_metric.year_reset` R (%/mo
  geometric) / DD per year + dev4 geometric mean R / dev4 worst-year R /
  dev4 max yearly DD / losing-year count + `v388.mix` full-path DD (context).
- G2 dev4 reference (from v421_result): mean 5.601, worst 2.588, max yearly DD
  16.91. Candidate iff ALL hold: dev4 mean > 5.601 AND dev4 worst > 2.588 AND
  dev4 max yearly DD <= 16.91 + 0.5 (= 17.41) AND dev4 mean beats its own
  exposure control. Robust criterion (§template) otherwise prefers nothing.
- Most recent year 2025-09-24 .. 2026-09-23 is scored ONCE, only for the frozen
  candidate (+ G2 + its control), labelled as such. Procedure: `run_engine.py`
  (heavy) reproduces G2-5y to the digit, computes dev4 for all 19 rows, applies
  the rule, prints the pick; `make_results.py` (light, no engine) then reads
  the cache and appends the 2025 row ONLY for G2/candidate/control. Variant
  2025 equities physically exist in the engine cache (continuous simulation)
  but are never read/printed for non-candidates.
- If no candidate: no 2025 variant scoring; REPORT states the rejection and
  shows dev4 tables only (+ G2 2025 reference from the repro check).

## Leakage statement (fixed upfront)

- TOM month boundaries, overnight UTC windows, halving dates: public calendars
  known decades ahead; no fitted window/threshold (Vasileiou optimisation,
  session search, S2F exponent explicitly NOT used).
- Gate at T uses only the bar timestamp T (date/hour) and the hard-coded
  calendars — known at the close of T. Applied after the bear filter (which
  uses open[T] inclusive, known at close T) and before ffill (v426 order), so
  no forward fill of future gates.
- No fits/quantiles/norms anywhere (constants only: 0.85/0.70/0.50/0.75/0.0,
  dip 0.7692); nothing is estimated on any test year; 7-day embargo vacuous
  (no estimation window).
- Fills: engine 5-min ban + 1m trade-through + stop-first (inherited).
- Checks in REPORT: feature timing (T-only calendars), label windows (engine
  forward from next open), fit windows (none — constants), fill timing (5-min
  ban/trade-through/stop-first).

## Fixed settings / deliverables / tests

- Engine: 4-phase shifts 0..3, Pool(2), RAM < 2.5 GB, tag `oc_lit_calendar`,
  `win_start=5`, one phase per process ok; progress print per finished row
  (every row << 10 min expected; plus per-shift start/done lines).
- G2 repro gate: cached-G2 5.41/W2.588/DD16.91/full16.82 to the digit, else stop
  (no overlay judged).
- Files (ONLY these may be written): `research/tournament/oc_lit_calendar/`
  (PLAN.md this file, `make_panel.py`, `run_engine.py`, `make_results.py`,
  `panel.parquet`, `results.json`, `REPORT.md`; scratch under `tmp/` only)
  and `tests/test_oc_lit_calendar.py` (>=1 causality/truncation test + >=1
  hand-checked synthetic case; run with
  `.venv/Scripts/python.exe -m pytest tests/test_oc_lit_calendar.py -q`).
- REPORT: per-year R/DD tables (dev4 all rows; 2025 candidate-only), gated
  share of bars + mean multiplier per variant-year, control constants, what
  failed and why, leakage checks, `results.json` beside it, 3-line Vietnamese
  verdict (adopt / reject / needs prospective evidence).

## Post-hoc log

- (none yet; any change after an outcome keeps the original row and adds a
  disclosed extra row)
