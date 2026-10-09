# oc_mvrvmech PLAN (pre-registered BEFORE any new outcome, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_mvrvmech.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`.
Write ONLY `research/tournament/oc_mvrvmech/` + `tests/test_oc_mvrvmech.py`.

## Puzzle (frozen, from oc_mvrvrobust — no re-selection)

- M1 = ALL majors' book LONG weights x0.5 while BTC MVRV-z > 2.0, else x1.0
  (z trailing <= 365d, min 180, day D usable from D+1 02:00 UTC; rows before
  2021-09-24 not gated; applied AFTER the v421 x0.5 bear filter, BEFORE the
  shifted-clock ffill; shorts/flats/NaN unchanged). G2 = `R2B1D17BFG2`
  (rule inv, k 1.0, kd 1.7, bear True, G 2.0). Both frozen; NO new variants.
- oc_mvrvrobust episodes (merged <= 14d, frozen `events.json`): E2
  2023-11-02..2024-01-13 (432 bars, BTC +22.6%), E3 2024-02-10..2024-04-10
  (360 bars, BTC +48.1%), E4 2024-11-12..2024-12-01 (114 bars, BTC +10.6%).
  E0/E1/E5 are negligible blips (combined diff ~ -0.005). Task 2 covers
  E2/E3/E4 (E3 included because its window proxy was huge at +0.241 absolute).
- Hypotheses: (a) the book's longs actually lost in those windows (trade-mode
  SL/TP whipsaw), (b) smaller book longs freed budget for the dip sleeve or
  changed the bear-book/gross-cap interaction, (c) an engine artefact.

## Pre-registered rows (ONLY these reach the engine)

- FULL: G2-full, M1-full (v426 mechanism via oc_mvrvrobust/compute_engine.py
  worker replica: pipe_setup("v321"), corr_size inv/kd1.7, risk_mult 1.0,
  sleeve_risk_budget 0.15*1.7, sleeve_gross_cap 2.0, trade=v216 GRID policy,
  win_start=5, gate costs maker 0.0002/taker 0.00055, adverse long funding
  0.0001/8h, 1m trade-through, stop-first). Validated bit-exact vs cached
  oc_mvrvrobust/engine_runs.pkl (G2 5.41/W2.588/DD16.91/full16.82; M1 dev4
  6.192); else STOP.
- BOOKONLY: G2-bookonly, M1-bookonly (identical to FULL except sleeve=False,
  as oc_bookattrib/run_bookonly.py). Book P&L per episode window and per year
  comes from these runs (4-phase mean equity ratio over the window).
- DIPONLY: books=0, sleeve=True (one config; G2-diponly and M1-diponly are the
  same zero-book input by construction, so a single DIPONLY run serves both
  labels; the script still writes both labels from the same run and asserts
  bit-identity). Answers "is the dip sleeve identical with no book coupling".
- Coupling test that actually matters: dip-leg PnL inside FULL G2 vs FULL M1
  via per-bar `attrib` (book vs sleeve split) + rung-fill counts from `events`.

## Fixed methods

- Task 1: per-year 4-phase reset R (%/mo geometric) + DD for BOOKONLY G2/M1
  (reset_metric.year_reset) and DIPONLY; per-episode book window return =
  mean over 4 shifts of eq[end]/eq[start]-1 on the BOOKONLY paths (nearest
  t <= bound, same helper as compute_events.window_ret); dip window return
  likewise on DIPONLY (expected ~identical) and on FULL attrib sleeve legs.
- Task 2: book TRADE tape from BOOKONLY `events` (no dip events to confuse
  pairing): per coin, pair each book_fill (long entry, side buy) with its
  closing book_stop/book_tp/book_close (trade mode = one position per asset,
  sequential pairing); record entry/exit time/price, SL/TP hits, holding bars,
  fees from stats, trade net = exit proceeds - entry cost - fees (funding on
  longs at settlements inside the holding window counted from the engine's
  adverse rule). Report per-coin counts, SL/TP/timeout split, summed P&L in
  G2 vs M1 for bars inside E2/E3/E4, and list which trades differ (gated size
  x0.5 -> different fill qty, different SL/TP distance via same sigma on half
  size, min-notional skips) and why.
- Budget utilisation: per-bar `bars` capture (target, governor g, scale s,
  equity) + `attrib` (book/sleeve per-bar PnL) + `events` rung_fill counts in
  FULL G2 vs M1. Report per episode: mean g, mean |target|, dip rungs filled,
  sleeve PnL, risk-budget/gross-cap skip counts (recomputed from the same
  budget rule on the captured ladder inputs where the engine does not log
  skips; code states the recomputation). The engine enforces NO spot-cash +
  perp-gross/leverage 95% cap in this path (engine_user enforces only vol
  target, governor, dip risk budget 0.255, gross cap 2.0, min-notional,
  1%-MMR liquidation check); REPORT states this explicitly instead of
  inventing the named cap.
- Artefact check (c): same-bar SL/TP tie handling (stop-first), win_start=5
  no-fill minutes, limit trade-through strictness, and M1-gate vs ffill order
  (gate BEFORE ffill, verified by recomputing one gated bar's weight on two
  shifted clocks). Any (c) claim needs a minimal reproduction (<= 30 lines
  script excerpt + 1 gated bar example).

## Metrics + verdict (fixed)

- Per config: per-year reset R/DD, dev4 mean/worst/DD, 5y mean/DD/full DD.
- Verdict is exactly one bold line: **(a)** / **(b)** / **(c)** with numbers
  (mixed verdicts allowed only as e.g. "mostly (a), small (b) of size X").
- REPORT.md ends with a 3-line Vietnamese verdict on whether the M1 gain is
  an economically sensible effect.

## Leakage checks (pre-registered)

- Feature timing: MVRV gate identical code to oc_mvrvrobust/signals_mvrv.py
  (as-of D+1 02:00, searchsorted right-1); truncation test leaves mults
  unchanged (test file).
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; thresholds/windows/mult frozen from oc_mvrvrobust.
- Fill timing: win_start=5 + 1m trade-through + stop-first (harness, G2/M1
  bit-exact re-run asserted before attribution).

## Deliverables

- `research/tournament/oc_mvrvmech/`: PLAN.md (this file), `signals_mvrv.py`
  (verbatim frozen-M1 copy), `compute_mech.py` (heavy engine: FULL + BOOKONLY
  + DIPONLY with events/attrib/bars, via heavy_slot, Pool(2)),
  `analyze_mech.py` (light: window/year tables, trade tape, budgets),
  `engine_mech.pkl`, `results.json`, `REPORT.md` (+ 3-line Vietnamese
  verdict). Scratch only under `tmp/`.
- `tests/test_oc_mvrvmech.py`: >=1 causality/truncation test + >=1
  hand-checked synthetic case; run
  `.venv/Scripts/python.exe -m pytest tests/test_oc_mvrvmech.py -q`.
  Stop when done.

## Post-hoc log

- (empty at pre-registration; any change after an outcome keeps the original
  row and adds the change as a disclosed extra row.)
