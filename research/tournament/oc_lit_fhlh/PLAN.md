# oc_lit_fhlh PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_lit_fhlh.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Idea H3 (intraday FH->LH momentum gate, UNTESTED #3) from `docs/opencode/IDEAS4_20261007.md` section C.
Write ONLY `research/tournament/oc_lit_fhlh/` + `tests/test_oc_lit_fhlh.py`.

## Hypothesis (fixed here)

Shen-Urquhart-Wang (2022): BTC first-half-hour return predicts the last-half-hour
(slope 0.968, R2 1.44%, strongest on high-volume/volatile/downturn days).
If intraday momentum persists at the daily scale, book exposure held after a
positive open should outperform exposure held after a negative open.
The gate scales book targets by the sign of the first-30-minute (FH) return of
the 24h volume day, leaving the dip sleeve untouched. Expected effect per IDEAS4:
+0.0-0.10 %/mo pre-cost (R2 1.44% ~= +-2-4 bps/day must survive 4-8 bps round-trip).
Prior 8%.

## Data and signal (fixed, no fetching, full span confirmed)

- Source: existing BTC 1m `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`
  (open_time/open/close, UTC, gap-free per manifest; probes p1-p4 confirm span).
  Coverage read 2026-10-07 without outcomes: 2020-01-01 .. 2026-09-23 continuous,
  so 2021-09-24 .. 2026-09-23 plus the 372d median lookback before anchor 2021
  is fully covered. No uncovered span, no skip, no imputation needed
  (fallback rule kept: unknown/NaN FH -> multiplier 1).
- Day D = calendar date, 00:00 UTC anchor (volume-clock day simplified to calendar
  day per IDEAS4 H3 parenthetical; trailing closes only, no volume weighting).
  FH(D) = close(00:29 1m bar) / open(00:00 1m bar) - 1, BTCUSDT perp.
  Uses only minutes <= FH close (00:29:59.999). LH is never used as a feature;
  slope is NOT refit (sign only).
- Availability (strict): FH(D) known at D + 00:30:00 UTC.
  For decision time T (4h bar time), D*(T) = latest D with D+00:30 <= T;
  i.e. T in [D 00:00, D 00:30) uses D-1's FH, otherwise D's FH.
  Implemented via searchsorted on daily avail timestamps (right-1).
- M3 noise-filter median: per anchor year A in {2021,2022,2023,2024,2025}-09-24,
  med(A) = median(|FH(D)|) over D in [A-372d, A-7d) (365 daily values + 7d embargo).
  Computed once per anchor from FH days only (no returns, no test-year fitting).
  Windows end before anchor minus 7-day embargo per common header.
- Market-wide gate: BTC FH gates ALL book symbols (paper is BTC-only; 5-majors XS
  of FH is not in the paper and would add noise; disclosed here).

## Book-gate engine (4-phase, heavy_slot)

- Base = G2 (`R2B1D17BFG2`, v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  multiplier on STANDARD book rows (T, sym) AFTER the bear-book filter
  (BTC 4h open < 1200-bar mean -> longs x0.5, same as v426) and BEFORE the
  shifted-clock forward fill. Rows before 2021-09-24 are not gated (v426 convention).
  Harness, costs, fills, reset metric, full-path DD exactly as v426/v421
  (gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h settlement
  00/08/16 UTC, shorts nothing; limit fills only on 1m trade-through, no fill
  in first 5 min after a 4h close via win_start=5; stop-first in same 1m bar).
- Pre-registered variants (ONLY these three, dip untouched):
  - M1: longs x1.0 if FH(D*(T)) > 0 else x0.6 (shorts unchanged).
  - M2: M1 longs + symmetric shorts: shorts x1.0 if FH(D*(T)) < 0 else x0.6
    (FH == 0 exactly -> longs x0.6, shorts x0.6; disclosed tie rule).
  - M3: M1 with noise filter: if |FH| < med(A) -> x1.0 (no change), else M1 rule
    (shorts unchanged; med(A) per anchor year as above).
- Exposure-matched controls (one per variant, per-year constants from realised
  exposure only, no return information):
  - CTRL_M1: per-year constant long multiplier = M1 realised mean over long cells
    (bear-filtered weight > 0) in that anchor year, applied to every long row.
  - CTRL_M2: per-year constant long multiplier (= M2 long mean, same as M1) plus
    per-year constant short multiplier = M2 realised mean over short cells
    (weight < 0) in that year, applied to every short row.
  - CTRL_M3: per-year constant long multiplier = M3 realised mean over long cells.
- Rows run: G2, M1, M2, M3, CTRL_M1, CTRL_M2, CTRL_M3 (7 rows, Pool(2), RAM < 2.5 GB).
- Step 1 reproduces cached G2 exactly from `v421/v421_runs.pkl` + `v421_result.json`
  (5.41 %/mo 4-phase reset metric, W 2.588, max yearly DD 16.91, full-path DD 16.82,
  yearly rows [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9])
  via `reset_metric.year_reset` + `v388.mix` full-path DD; else STOP, no overlay.
- Selection ONLY on four dev years (anchors 2021-09-24 .. 2024-09-24, each [A, A+365d))
  with the template rule vs G2: candidate iff dev4 mean > G2 dev4 5.601
  AND dev4 worst year > G2 dev4 2.588 AND max yearly DD <= 16.91 + 0.5
  AND beats its own control on dev4 mean. Robust view also reported
  (DD <= 20, no losing dev year; prefer dev4 mean >= 5%, then highest dev4 worst-year).
  Score the most recent year 2025-09-24..2026-09-23 ONCE, only for a candidate
  (+ G2 and its control); otherwise the most recent year is not a selection input
  (engine necessarily integrates the full span; dev4 numbers decide, year-4 labelled).
- Report per dev year: 4-phase reset R (%/mo), yearly DD, full-path DD, share of book
  long/short cells gated (mult<1), mean multiplier, and variant vs control rows.
  Full tables in results.json/engine_results.json.

## Leakage statement (pre-registered checks)

- Feature timing: FH(D) uses 1m bars with open_time in [D 00:00, D 00:29] only;
  asof D+00:30 <= T (searchsorted right-1); sampled-T truncation test must leave
  FH(T) unchanged; boundary test at D+00:30 +-1s.
- Label windows: no labels fitted (engine uses realised 1m path).
- Fit windows: no fits except M3 per-anchor medians on FH days in [A-372d, A-7d)
  (ends before anchor minus 7d embargo; thresholds/signs fixed here; CTRL means
  are realised-exposure only per year, reported not selected on year-4).
- Fill timing: engine win_start=5 + 1m trade-through + stop-first (v426 harness,
  G2 bit-exact). Tests assert win_start/trade-through path via harness reuse
  and the FH timing unit tests.

## Deliverables

- `research/tournament/oc_lit_fhlh/`: PLAN.md (this file), `fhlh_signal.py`
  (daily FH + asof + medians + multipliers), `compute_fhlh_engine.py`
  (heavy_slot 4-phase), `engine_results.json`/`results.json`, REPORT.md
  (per-year tables, what failed, 3-line Vietnamese verdict).
- `tests/test_oc_lit_fhlh.py`: >=1 causality/truncation test + >=1 hand-checked
  synthetic case; run `.venv/Scripts/python.exe -m pytest tests/test_oc_lit_fhlh.py -q`.
  Stop when done.

## Post-hoc log

- (empty; filled only if definitions change after outcomes — original row kept,
  change added as disclosed extra row per common header).
