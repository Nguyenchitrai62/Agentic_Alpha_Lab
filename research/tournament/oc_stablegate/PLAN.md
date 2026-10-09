# oc_stablegate PLAN (pre-registered BEFORE any outcome is computed, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_stablegate.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`.
Ideas B3 (book gate) + B7 (dip-budget dial) from `docs/opencode/IDEAS_20261007c.md`.
Write ONLY `research/tournament/oc_stablegate/` + `tests/test_oc_stablegate.py`.

## Hypothesis (fixed here)

Sustained stablecoin net-creation = incoming risk-bid (dry powder); destruction = risk-off.
The book should be longer into creation and shorter into destruction (B3); the dip sleeve is a
liquidity-provision edge so it should provision more budget when fresh supply arrives and less
when it drains (B7). Supply impulse (not price premium) is untested: prior `oc_usdtprem`
(price premium tilt, engine NO) and `oc_usdtdip` (+0.047 < gate) used the USDT price, not supply.

## Data and signal (fixed, no fetching)

- `data/raw/onchain_20260924/stablecoins.csv` (asset, time = UTC day, CapMrktCurUSD; CoinMetrics daily caps).
  Use USDT+USDC summed: `cap(D) = Cap_usdt(D) + Cap_usdc(D)` per calendar day D (UTC).
  Coverage check (read 2026-10-07, no outcomes): file spans 2019-01-01 .. 2026-09-23, both assets,
  so 2021-09-24 .. 2026-09-23 is fully covered; no uncovered span, no multiplier-1 fallback needed
  (fallback rule kept: if a decision time has no usable z, multiplier = 1).
- Availability (strict): day D usable from D+1 00:00 UTC + 4h safety = D+1 04:00 UTC.
  For a decision time T (4h bar time / bar open), `D*(T) = max{D : D+1 04:00 UTC <= T}`,
  `z(T) = z(D*(T))` (NaN -> multiplier 1). For 4h-aligned T at 00:00 the signal is 2 days stale
  by design; at 04:00+ it is 1 day stale. Never forward-filled across the boundary.
- `impulse(D) = log(cap(D) / cap(D-30))` (natural log; NaN if either cap missing/non-positive).
- `z(D) = (impulse(D) - mean(W)) / std(W, ddof=1)` where W = trailing up-to-730 impulse values
  ending at D inclusive, min 365 non-NaN values else NaN; std==0 or <365 values -> NaN.
  Rolling norm is a causal feature (uses only days <= D, each known at its own D+1 04:00);
  thresholds below are fixed constants, nothing is fitted on test years.
- No other inputs. Thresholds/multipliers fixed here, never tuned.

## Leg 1 - book gate (4-phase engine, heavy_slot)

- Base = G2 (`R2B1D17BFG2`, v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  standard book rows (T, sym) whose bear-filtered weight > 0 get a multiplier, applied AFTER the
  bear-book filter (BTC 4h open < 1200-bar mean -> longs x0.5, same as v426) and BEFORE the
  shifted-clock forward fill. Shorts/flats/NaN-z unchanged. Harness, costs, fills, reset metric,
  full-path DD exactly as v426/v421 (gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001
  per 8h settlement 00/08/16 UTC, shorts nothing; limit fills only on 1m trade-through, no fill
  in first 5 min after a 4h close; stop-first in same 1m bar).
- Pre-registered variants (ONLY these):
  - G1: long x0.75 when z(T) < -1.0, else x1.0.
  - G2S: long x0.75 when z(T) < -1.5, else x1.0 (asymmetric, fewer events).
  - CTRL: exposure-matched control for G1 = per-year constant long multiplier equal to G1's
    realised mean multiplier over long rows (bear-filtered weight > 0) in that anchor year,
    applied to every long row of that year (shorts unchanged). Mean is realised exposure only,
    no return information; isolates timing vs level.
- Reproduce G2 exactly first from `v421/v421_runs.pkl` + `v421_result.json`
  (5.41 %/mo 4-phase reset metric, max yearly DD 16.91, full-path DD 16.82) via
  `reset_metric.year_reset` + `v388.mix` full-path DD; else STOP, no overlay.
- Selection ONLY on four dev years (anchors 2021-09-24 .. 2024-09-24, each [A, A+365d)).
  Candidate iff (assignment rule): (G1 or G2S) beats G2 on dev4 mean with no worse dev4 worst year
  AND dev4 DD <= G2 dev4 DD + 0.3pp AND beats CTRL on dev4 mean. Robust view also reported
  (DD<=20, no losing dev year; prefer dev4 mean>=5%, then highest dev4 worst-year).
  Score the most recent year 2025-09-24..2026-09-23 ONCE, only for the chosen candidate + G2
  reference; otherwise the most recent year is not scored for gated variants. Engine necessarily
  integrates the full span; dev4 numbers decide, year-4 is labelled.
- Report per dev year: 4-phase reset R (%/mo), yearly DD, full-path DD, share of book long rows
  gated (mult<1), mean multiplier, and G1 vs CTRL. Full tables in results.json.

## Leg 2 - dip budget dial (dip replica, no engine)

- Replica copied from `research/tournament/oc_placebo_dip/compute_placebo_dip.py` into this folder
  (`compute_stablegate_dip.py` core identical: D0 exits TP1sg/sl4sg-close5/bl8sg/timeout next-bar open,
  maker 0.0002/taker 0.00055, v293 settle funding, B1 sizes w=1/(1+n), majors x R2 depths
  2.5/3.0/3.5/4.0/5.0, live offsets 16..238 strict trade-through, 4 clock phases from 2020-08-01
  +0/1/2/3h, bars open in [2021-09-24, 2026-09-24)). Reproduce base 5y 4-phase-mean sum 7.718 first
  (placebo `base_sum5y` 7.718304; phase-0 ref [2.388, 0.183, 3.810, 2.579, 0.712]); else STOP.
- z at the bar OPEN (same D+1 04:00 availability with T = bar open time; NaN -> x1).
  Pre-registered variants (ONLY these):
  - D1: every kept-fill rung weight x(0.32/0.26)=1.230769 when z > +1.0, x(0.20/0.26)=0.769231
    when z < -1.0, else x1.0.
  - D2: upside only: x(0.32/0.26)=1.230769 when z > +1.0, else x1.0.
  Same fills, same y/d legs; only weights change (pairing: kept iff y1.0 finite; y0.9/y1.1 legs
  kept for placebo parity where present, unused by D1/D2 scoring which uses y1.0).
- Judge with the established dip gate, calibrated on all five years - LABELLED, plus dev4-only view:
  PROMISING_5y iff sum>=base in >=4/5 years AND DD<=base+0.01 in >=4/5 AND 5y sum delta >= +0.273
  (pooled placebo p95 0.272796). Dev4 view uses years 0-3 only with the same per-year legs.
  Candidate iff PROMISING_5y (assignment rule). No exposure control required by assignment.
- Costs/fills as replica (gate costs above; minute-5 ban is live offsets 16..238, i.e. no fill in
  first 16 min, stricter than 5-min; stop-first priority as replica).

## Leakage statement (pre-registered checks)

- Feature timing: stablecoin day D used only at T >= D+1 04:00 (searchsorted end<=T-1s style on
  daily availability timestamps); sampled-T truncation test must leave z(T) unchanged.
- Label windows: no labels fitted (engine uses realised 1m path; dip uses realised exits).
- Fit windows: no fits; rolling 730d norm is a causal feature, thresholds fixed here, CTRL means
  are realised-exposure only per year (reported, not selected on year-4).
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first; dip live 16..238 strict
  `low < level`, exits race stop-first, timeout at next-bar open. Tests assert these.

## Deliverables

- `research/tournament/oc_stablegate/`: PLAN.md (this file), `stablegate_signal.py` (daily z),
  `compute_stablegate_engine.py` (Leg1, heavy_slot), `compute_stablegate_dip.py` (Leg2 replica+rules,
  heavy_slot), `results.json`, `REPORT.md` (per-year tables, what failed, 3-line Vietnamese verdict).
- `tests/test_oc_stablegate.py`: >=1 causality/truncation test + >=1 hand-checked synthetic case;
  run `.venv/Scripts/python.exe -m pytest tests/test_oc_stablegate.py -q`. Stop when done.

## Post-hoc log

- No definition changes after outcomes (thresholds/multipliers/windows/rules as above).
  Two indexing bug-fixes in `compute_stablegate_engine.py` before the first successful run
  (bool-mask handling; per-cell CTRL mean via broadcast); harness proven by the bit-exact G2
  re-run (5.41/16.91/16.82). Outcome: engine REJECT (G1/G2S lose dev4 to G2 and CTRL), dip REJECT
  (D1/D2 not PROMISING_5y). Most recent year not scored for gated variants (no candidate).
