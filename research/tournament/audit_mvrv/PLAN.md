# audit_mvrv PLAN (pre-registered BEFORE any outcome, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_audit_mvrv.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md` + `research/tournament/oc_lit_position/PLAN.md`
(H8/M1 only). Blind replication of the MVRV-z cycle gate M1 on G2.
Write ONLY `research/tournament/audit_mvrv/` + `tests/test_audit_mvrv.py`.

## Pre-registered variants (ONLY these reach the engine)

- G2 (reference, reproduce first): `R2B1D17BFG2` in v421 (rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Must reproduce exactly: 4-phase reset 5.41 %/mo, W 2.588, max yearly DD 16.91,
  full-path DD 16.82, yearly rows [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9].
  Else STOP, no overlay.
- M1 (H8 blind replica): ALL majors' book LONG weights x0.5 when BTC `z(T) > 2.0`, else x1.0.
- CTRL_M1 (exposure-matched control, TEMPLATE): constant per-year multiplier equal to M1's
  realised mean multiplier over LONG rows (bear-filtered weight > 0) in that anchor year,
  applied to every long row of that year (shorts unchanged). Mean is realised exposure only.

M2/M3/O1/O2 are OUT OF SCOPE for this audit (not implemented, not scored).

## Data (read 2026-10-07, no outcomes)

- H8: `data/raw/onchain_20260924/btc.csv` (CoinMetrics free, daily UTC, 2019-01-01..2026-09-23,
  2823 rows per manifest). Column `CapMVRVCur` used directly as MVRV(D) (ratio ~0.75..3.96).
  Single frozen vintage downloaded 2026-09-24 (manifest sha256 e64aca4f...); realised-cap
  revision bias is an audit question (see REPORT/COMPARISON), not a second data pull.
- No ETH MVRV history used. No live CoinMetrics pull in backtest.

## Signal M1 (fixed, nothing fitted; thresholds literature-frozen)

- `MVRV(D) = CapMVRVCur(D)`, daily UTC day D.
- `zM(D) = (MVRV(D) - mean(W)) / std(W, ddof=1)`, W = trailing up-to-365 daily MVRV values
  ending at D inclusive, min 180 non-NaN else NaN; std==0 -> NaN. Causal in D (days <= D only).
- Availability (strict): day D usable from D+1 02:00 UTC.
  `D*(T) = max{D : D+1 02:00 UTC <= T}`, `z(T) = zM(D*(T))` (NaN -> multiplier 1).
  For 4h-aligned T the signal is 1-2 days stale by design.
- Gate: on STANDARD book rows (T, sym) with bear-filtered weight > 0, multiplier 0.5 if
  `z(T) > 2.0` else 1.0. Shorts/flats/NaN unchanged. Rows with T < 2021-09-24 UTC never gated
  (v426 convention). Applied AFTER the bear-book filter (BTC 4h open < 1200-bar mean ->
  longs x0.5) and BEFORE the shifted-clock forward fill — same slot as v426_book_brake.
- Standard grid = `eu.er.v154_books()` index (STANDARD book index); gate is computed on that
  grid, then forward-filled onto each shifted phase grid identically to v426.

## Engine (4-phase, heavy_slot)

- Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`
  on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0). Harness, costs, fills, reset
  metric, full-path DD exactly as v426/v421: gate costs maker 0.0002, taker 0.00055 (stops and
  market exits taker), longs pay 0.0001 per 8h settlement 00/08/16 UTC, shorts nothing; limit
  fills only on 1m trade-through, no fill in first 5 min after 4h close (`win_start=5`);
  stop-first in same 1m bar. Dip leg: R2 agents ON (pipe v321, R2_TABLE per shift), inv/kd 1.7,
  gross cap G=2.0. 4 phases s=0/1/2/3h, Pool(2), RAM < 2.5 GB, via
  `scripts/heavy_slot.py run --tag audit_mvrv --min-free-gb 2.0 -- ...`.
- Anchors: 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 (dev4), 2025-09-24 (most recent year);
  each year = [A, A+365d). Scoring: `reset_metric.year_reset` per year (4-phase reset),
  dev4 geometric mean / worst / max-DD, 5y geometric mean, `v388.mix` full-path DD
  (continuous equity since 2021-09-24). No selection on year-4 here (audit replica, not a pick);
  TEMPLATE candidate rule reported as a row only (dev4 mean > G2 5.601 AND worst > 2.588 AND
  maxDD <= 17.41 AND beats CTRL_M1 on dev4 mean).

## Deliverables

- `research/tournament/audit_mvrv/`: PLAN.md (this file), `signals_mvrv.py` (zM/z(T)/multipliers),
  `compute_engine.py` (4-phase G2/M1/CTRL_M1, heavy_slot), `replication.json` (saved BEFORE opening
  oc_lit_position/oc_mvrvrobust anything), `results.json`, `REPORT.md`, `COMPARISON.md`
  (PASS/FAIL/PASS-WITH-NOTES + 3-line Vietnamese verdict).
- `tests/test_audit_mvrv.py`: >=1 causality/truncation test + >=1 hand-checked synthetic case;
  run `.venv/Scripts/python.exe -m pytest tests/test_audit_mvrv.py -q`. Stop when done.

## Leakage statement (pre-registered checks)

- Feature timing: MVRV daily as-of `D+1 02:00 <= T`; rolling window ends at D inclusive (days
  <= D only); truncation tests must leave z(T) unchanged when future CSV rows are removed.
- Label windows: no labels fitted (engine uses realised 1m path).
- Fit windows: no fits; rolling norms are causal features; thresholds (2.0) frozen here;
  CTRL means are realised-exposure only per year.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first. Tests assert these call args.

## Post-hoc log

- (empty at pre-registration; any change after an outcome keeps the original row and adds the
  change as a disclosed extra row.)
