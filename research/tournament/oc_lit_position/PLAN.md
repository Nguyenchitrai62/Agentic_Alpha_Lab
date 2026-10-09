# oc_lit_position PLAN (pre-registered BEFORE any outcome, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_lit_position.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`. Ideas H6 (open-interest level throttle)
+ H8 (MVRV-z timing gate) from `docs/opencode/IDEAS4_20261007.md` section C.
Write ONLY `research/tournament/oc_lit_position/` + `tests/test_oc_lit_position.py`.

## Hypotheses (fixed here, exactly the IDEAS4 C variants, no others)

- H6 OI-level throttle (PARTIALLY #26, rank 6): crowded open interest = late/long-squeeze risk,
  so halve book longs when the per-coin 7d OI change is extreme. LEVEL form (not the failed
  `oc_i2_oiguard` change-triggered unwind skip).
- H8 MVRV-z timing gate (PARTIALLY #13, rank 8, data-limited): high crypto "value" vs network
  activity predicts low future returns; halve longs at euphoria (z>2), small bounded add at
  despair (z<0, M2 only).

## Data and span (read 2026-10-07, no outcomes)

- H6: `data/raw/um_metrics_20260926/{BTC,ETH,SOL,BNB,XRP}USDT_metrics.parquet`
  (`sum_open_interest`, 5-min `create_time`). Manifest: BTC 2020-09-01..2026-09-24 (2215d, no gaps);
  ETH/SOL/BNB/XRP 2021-12-01..2026-09-24 (1759d; 456d missing before 2021-12-01).
  `data/raw/metrics_ext_20260924/metrics_ext.parquet` is a redundant BTC-only 2026-03-23..2026-09-23
  subset (per manifest), UNUSED (same convention as `oc_i2_oiguard`). No new pull.
  Consequence: for anchor year 2021-09-24..2022-09-23, non-BTC coins have no OI for the first
  ~68 days + warmup; those (T,sym) default to NO gate (multiplier 1), never imputed (disclosed).
- H8: `data/raw/onchain_20260924/btc.csv` (CoinMetrics free, `CapMVRVCur` + `CapMrktCurUSD`,
  daily UTC). Manifest: 2019-01-01..2026-09-23 (2823 rows), so 2021-09-24..2026-09-23 fully covered;
  no skipped anchor year for M1/M2. `CapMVRVCur` values 0.75..3.96 (mean 1.76) are the MVRV ratio
  itself (not a USD cap), used directly as MVRV(D) — a ratio of ~1e12 USD caps would be ~1e12,
  not ~1.6. No ETH MVRV history exists in `onchain_20260924/` (only btc + stablecoins), so M3
  (ETH-MVRV analogue) is SKIPPED, disclosed, never imputed (binding IDEAS4 rule).
  Live CoinMetrics free tier is paper-only, not used in this backtest.

## Signals (fixed, nothing fitted on test years)

H6 OI 7d-change z, per coin c, per decision time T (4h bar time, STANDARD book index):
- `OI_now(c,T)` = last `sum_open_interest` with `create_time <= T - 5min` (5-min lag per
  metrics_ext manifest note); `OI_7d(c,T)` = last with `create_time <= T - 7d - 5min`.
  `d7(c,T) = ln(OI_now / OI_7d)`, NaN if either missing/non-positive.
- `z(c,T) = (d7 - mean(W)) / std(W, ddof=1)`, W = trailing up-to-2190 prior 4h-bar d7 values
  (365d x 6) on the same STANDARD grid strictly before T, min 540 finite else NaN; std==0 -> NaN.
  Rolling norm is a causal feature (only values <= T, each as-of its own T); thresholds below are
  literature-fixed constants.
- Availability: OI rows used as-of (no restated series); trailing stats strictly pre-T, so the
  7-day embargo is satisfied (book horizon 4h, all stats end >= 7d before any fitted use — nothing
  is fitted per anchor).

H8 BTC MVRV-z, per decision time T (all majors share the BTC cycle signal):
- `MVRV(D) = CapMVRVCur(D)` (daily UTC day D, direct ratio, see above).
- `zM(D) = (MVRV(D) - mean(W)) / std(W, ddof=1)`, W = trailing up-to-365 daily MVRV values ending
  at D inclusive, min 180 non-NaN else NaN; std==0 -> NaN. Causal in D (days <= D only).
- Availability (strict, per onchain manifest note): day D usable from D+1 02:00 UTC.
  `D*(T) = max{D : D+1 02:00 UTC <= T}`, `z(T) = zM(D*(T))` (NaN -> multiplier 1). For 4h-aligned T
  the signal is 1-2 days stale by design. Thresholds (2/0) frozen from literature, never refit;
  D+1 application (daily caps known after day-end).

## Leg 1 — book gates (4-phase engine, heavy_slot)

- Base = G2 (`R2B1D17BFG2`, v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  STANDARD book rows (T, sym) whose bear-filtered weight > 0 get a multiplier, applied AFTER the
  bear-book filter (BTC 4h open < 1200-bar mean -> longs x0.5, same as v426) and BEFORE the
  shifted-clock forward fill. Shorts/flats/NaN-z unchanged. Rows before 2021-09-24 are not gated
  (v426 convention). Harness, costs, fills, reset metric, full-path DD exactly as v426/v421
  (gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h settlement 00/08/16 UTC,
  shorts nothing; limit fills only on 1m trade-through, no fill in the first 5 min after a 4h
  close (`win_start=5`); stop-first in the same 1m bar).
- Pre-registered book variants (ONLY these reach the engine):
  - O1 (H6): per-coin longs x0.5 when `z(c,T) > 2.0`, else x1.0.
  - O2book (H6 combined, ENGINE ONLY IF its dip leg passes the replica+placebo gate below):
    per-coin longs x0.5 when `z(c,T) > 1.5`, else x1.0. The engine row for O2, if gated through,
    applies the book throttle PLUS the dip-skip (dip fills removed in the sleeve); if the dip
    leg fails, NO O2 engine row is run at all (combined rejected at the screen).
  - M1 (H8): ALL majors' longs x0.5 when BTC `z(T) > 2.0`, else x1.0.
  - M2 (H8): ALL majors' longs x0.5 when `z(T) > 2.0`, x1.1 when `z(T) < 0.0`, else x1.0
    (bounded greed add; engine gross cap G=2.0 still enforced, so no leverage breach).
  - M3 (H8 ETH analogue): SKIPPED — no ETH MVRV history to 2021 (disclosed, never imputed).
- Exposure-matched controls (one per engine variant, per TEMPLATE): constant per-year multiplier
  equal to that variant's realised mean multiplier over LONG rows (bear-filtered weight > 0) in
  that anchor year, applied to every long row of that year (shorts unchanged). Names: CTRL_O1,
  CTRL_O2 (only if O2 gated), CTRL_M1, CTRL_M2. Mean is realised exposure only, no returns.
- Reproduce G2 exactly first from `v421/v421_runs.pkl` + `v421_result.json`
  (5.41 %/mo 4-phase reset metric, W 2.588, max yearly DD 16.91, full-path DD 16.82,
  yearly rows [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9]) via
  `reset_metric.year_reset` + `v388.mix` full-path DD; else STOP, no overlay.
- Selection ONLY on four dev years (anchors 2021-09-24..2024-09-24, each [A, A+365d)).
  Candidate iff ALL of (TEMPLATE rule): dev4 mean > G2 dev4 5.601 AND dev4 worst year > G2 2.588
  AND max yearly DD <= 16.91 + 0.5 AND beats its own control on dev4 mean. Robust view also
  reported (DD<=20, no losing dev year; prefer dev4 mean>=5%, then highest dev4 worst-year).
  Score the most recent year 2025-09-24..2026-09-23 ONCE, only for the chosen candidate + G2 and
  its control; otherwise the most recent year is not scored for gated variants. Engine necessarily
  integrates the full span; dev4 numbers decide, year-4 is labelled POST-HOC.
- Report per dev year: 4-phase reset R (%/mo), yearly DD, full-path DD, share of book long rows
  gated (mult!=1), mean multiplier, and variant vs CTRL. Full tables in results.json.

## Leg 0 — O2 dip leg (dip replica, gates O2 engine; no engine if failed)

- Replica copied from `research/tournament/oc_placebo_dip/compute_placebo_dip.py`
  (D0 exits TP1sg/sl4sg-close5/bl8sg/timeout next-bar open, maker 0.0002/taker 0.00055, v293 settle
  funding, B1 sizes w=1/(1+n), majors x R2 depths 2.5/3.0/3.5/4.0/5.0, live offsets 16..238 strict
  trade-through, 4 clock phases from 2020-08-01 +0/1/2/3h, bars open in [2021-09-24, 2026-09-24)).
  Reproduce base 5y 4-phase-mean sum 7.718 first (`base_sum5y` 7.718304; phase-0 ref
  [2.388, 0.183, 3.810, 2.579, 0.712]); else STOP.
- O2dip rule (ONLY dip variant): skip NEW dip bids on (phase, coin, bar) bars where the H6 O2
  condition fires (`z(c,Tbar) > 1.5` with Tbar = bar OPEN time, same 5-min-lag OI as-of; NaN ->
  no skip). Holds/exits unchanged. Guard = subset sums, NO renormalisation. Minute-5 fill ban kept
  (live>=16). Daily sums of w*y by exit date; per-year 4-phase means (S, DD of cumulative
  daily-sum path from 0).
- Judge with the oc_placebo_dip gate: PROMISING iff sum>=base in >=4/5 years AND DD<=base+0.01
  in >=4/5 years AND 5y 4-phase-mean sum delta >= +0.273 (pooled placebo p95 0.272796).
  O2 engine runs ONLY if O2dip is PROMISING; else NO O2 engine row (combined rejected at screen,
  disclosed). 2025 handling follows the same rule (screen uses all 5y per placebo calibration;
  dev4 view 0-3 also reported, LABELLED).

## Leakage statement (pre-registered checks)

- Feature timing: H6 OI as-of `<= T-5min` (searchsorted right-1); H8 daily as-of `D+1 02:00 <= T`;
  truncation tests must leave z(T) unchanged when future rows are removed.
- Label windows: no labels fitted (engine uses realised 1m path; dip uses realised exits).
- Fit windows: no fits; rolling norms are causal features (windows end at/before T, all inputs
  known at their own availability); thresholds (2.0/1.5/0) fixed here; CTRL means are
  realised-exposure only per year (reported, not selected on year-4).
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first; dip live 16..238 strict
  `low<level`, stop-first race, timeout at next-bar open. Tests assert these.

## Deliverables

- `research/tournament/oc_lit_position/`: PLAN.md (this file), `signals.py` (H6/H8 z + multipliers),
  `compute_dip_o2.py` (Leg0 replica+O2dip, heavy_slot), `compute_engine.py` (Leg1, heavy_slot),
  `results.json`, `REPORT.md` (per-year tables, what failed, 3-line Vietnamese verdict).
- `tests/test_oc_lit_position.py`: >=1 causality/truncation test + >=1 hand-checked synthetic case;
  run `.venv/Scripts/python.exe -m pytest tests/test_oc_lit_position.py -q`. Stop when done.

## Post-hoc log

- (empty at pre-registration; any change after an outcome keeps the original row and adds the
  change as a disclosed extra row.)
