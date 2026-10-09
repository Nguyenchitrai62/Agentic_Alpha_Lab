# oc_beargate — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_beargate.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_beargate/`
+ `tests/test_oc_beargate.py`. Engine via heavy_slot (RAM tight: one engine job at a time).
Heartbeat print every 600 s in long jobs. Scratch only under `research/tournament/oc_beargate/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.

## Why (from assignment)

The vol / foundation-model dip tilts (oc_voltilt, oc_chronos) help in 2023-2026 and
hurt or do nothing in 2021-2022 (bear market). G2 already contains a frozen bear
filter (bear True in v421 R2B1D17BFG2 / bot --bear-book, op bear_state).
Conditioning the tilt on that EXISTING state adds no free parameter.

## Variants (exactly two + reference, no other parameter)

- C2_B: C2 multiplier (research/tournament/oc_chronos, frozen fits) when the bear
  state of that bar is False, else 1.0.
- GARCH_B: V_GARCH multiplier (research/tournament/oc_voltilt, frozen) when not
  bear, else 1.0.
- REF = G2 unchanged (tilt 1), reproduction row.
- C2 and V_GARCH numbers are COPIED verbatim from oc_chronos REPORT/results.json
  and oc_voltilt REPORT/results.json (reference only, NOT re-run, labelled copied).

## Bear state (exact causal definition, no new parameter)

- Definition (cited): `research/parallel/rounds/parallel-20260906-r2/v421/v421_gross_cap.py:70`
  `bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()`
  where `btc = _opens_std["BTCUSDT"].reindex(books154.index)` (line 69),
  `books154, _opens_std = eu.er.v154_books()` (engine_real v154 4h books/opens).
  Identical lines in `research/tournament/oc_chronos/run_engine.py:126-127` and
  `research/tournament/oc_voltilt/run_engine.py:114-115`.
- Evaluation at the holding-bar open: for a holding-bar open T (tz-aware UTC) on
  phase shift s, `bear_state(T) = bear_std at the latest standard-grid index
  r <= T` (ffill; `bear_std` indexed by books154.index). `bear_std[r]` uses only
  BTC opens <= r <= T (rolling mean, causal); the ffill uses only r <= T.
  Engine books use the same ffill (`sb.reindex(idx, method="ffill")`), so the
  gate sees exactly the state the books saw. NaN rolling (first <600 bars, 2017)
  compares False -> not bear. No look-ahead: no index > T is ever consulted.
- Unit-tested: hand-checked synthetic rolling example + ffill/causality test
  (truncating the btc series cannot change bear states at kept times).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (ch_q10) +
  `research/tournament/oc_chronos/fits.json` (C2 per-anchor direction/q20/q80).
- `research/tournament/oc_voltilt/vol_features_4shift.parquet` (risk_GARCH) +
  `research/tournament/oc_voltilt/fits.json` V_GARCH section.
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism +
  `assign_mult`/`anchor_of` copied verbatim; only the bear gate added).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: dev years
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica
  ledger for the placebo leg, read-only reuse; gate n == 22312,
  base sum5y == 7.718304 +- 0.002).
- Expected copied reference (frozen, labelled copied not re-run):
  C2 dev [2.711,3.460,6.250,10.721] last 4.754 DDlast 12.86 fullDD 15.42
  timing-Y4 99.20 block 98.90; V_GARCH dev [2.398,3.265,6.447,10.571] last 4.932
  DDlast 12.32 fullDD 17.12 timing-Y4 100.0 block 100.0; REF as above.

## Tilt rule (fixed)

- Base multipliers with hi/lo = 1.25/0.75, missing/NaN risk -> 1 (same as C2/V_GARCH):
  m_C2 = assign_mult(-ch_q10, fits_C2[A].direction/q20/q80);
  m_G = assign_mult(risk_GARCH, fits_G[A].direction/q20/q80).
- Gated: C2_B = m_C2 if not bear_state(T) else 1.0;
  GARCH_B = m_G if not bear_state(T) else 1.0.
- Fits of anchor A applied to all four shifts in year A. Most-recent-year fits
  are the frozen 2025-09-24 fits (harness rows t_exit < 2025-09-17, inherited).
  No ensemble, no other variant.

## Engine (fixed; exact copy of oc_chronos/run_engine.py mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books (books_bear built exactly
  as v421/run_engine copies), risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside the engine (maker 0.0002, taker 0.00055, longs
  pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through; nothing in first
  5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Rows run through the engine (ONLY these three): REF, C2_B, GARCH_B.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the three rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) for the three rows ONCE (every Y4 number
  labelled scored-once; REF Y4 must reproduce v421 G2 Y4 to the digit).
  No re-runs after seeing outcomes; any change becomes a disclosed extra row.

## Metrics / gates (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + sized
  mean multiplier (same collection as oc_chronos run_engine.py; plus bear-share
  counters among tilt calls).
- Bear share (no selection input): per year y (all 4 shifts pooled):
  bars share = fraction of decision holding-bars T in year y (per-shift grid
  [A+sh, min(A+sh+365d, live1)), step 4h) with bear_state(T) True;
  fills share = fraction of D0-replica ledger rung fills in year y whose
  holding-bar open has bear_state True. Both causal (bear ffill <= T).
- Robust pick among REF / C2_B / GARCH_B on dev4 ONLY: DD <= 20 and no losing dev
  year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return,
  ties -> higher mean.
- Timing placebo per year EXACTLY like oc_k2placebo (1000 within-year permutations
  of the GATED multipliers over decision bars, normalised by the actual realised
  mean; timing seed 20261007+y, block-42 seed 20261008+y;
  percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95) for C2_B and
  GARCH_B (D0-replica leg, light numpy, reusing k2placebo ledger read-only with
  the same gates). Bar universe per year = (sym,shift,T) decision bars from the
  union of the two frozen feature tables restricted to year y on each shift grid.

## Leakage / checks (stated in REPORT)

- Feature timing (ch_q10 / risk_GARCH frozen, inherit their truncation tests);
  bear timing (rolling <= r <= T + ffill <= T; truncation-tested in
  tests/test_oc_beargate.py); label windows (harness t_exit < A - 7d inherited);
  fit windows (frozen fits; shift-0 + 7d embargo inherited; anchor-y fit for year y;
  no statistic from any test year feeds any choice); fill timing (win_start=5 +
  1m trade-through + stop-first, engine). No statistic from any test year feeds any
  choice. Gate costs inside the engine.

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: `assign_mult` + `anchor_of` copy + `gate_mult` (unit-tested).
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job.
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json` + `tmp/last_table.json` (+ 5y means + full-path DD).
- `compute_bearshare.py`: CPU-only bars/fills bear share per year -> `tmp/bearshare.json`.
- `compute_placebo.py`: CPU-only 1000-perm timing/block placebo for C2_B + GARCH_B
  on the D0 replica (reuses k2placebo ledger read-only) -> `tmp/placebo_beargate.json`.
- Deliverables: PLAN.md (this file), tilt_rule.py, run_engine.py, analyze.py,
  compute_bearshare.py, compute_placebo.py, results.json, REPORT.md,
  tests/test_oc_beargate.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_beargate.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
