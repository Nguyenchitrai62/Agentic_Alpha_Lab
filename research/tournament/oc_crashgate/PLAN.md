# oc_crashgate — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_crashgate.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_crashgate/`
+ `tests/test_oc_crashgate.py`. Scratch only under `research/tournament/oc_crashgate/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one engine job at a time, load one coin
at a time, float32). Long jobs: nohup + log file under tmp/, poll the log. Heartbeat print
every 600 s in long jobs.

## Why (IDEAS5_20261008.md idea #1, rank 1 — quoted, not refit)

Oct-2025 cascade papers (2025-26: severity = shock x map-in-path x liquidity withdrawal;
impact spikes 1.2-9x, OI clears 25-70 %): bigger rungs in high vol catch the crash, not the
rebound. `oc_presampletilt` (C2 7/9 legs, fails COVID-2020 + 2021) + `oc_voltilt` (same
signature as all 4 FMs: significant timing 2023-2026 incl. clean year 100.0, nothing in
2021-2022) say the family is regime-dependent; `oc_beargate` proved SMA1200 trend != crash
regime (bear filter 73-81 % bear in 2021 + clean year, mostly ON in 2023-2024; gating COST
clean-year return C2 -0.055 / GARCH -0.117 and DESTROYED C2 clean timing 99.2 -> 64.8).
Gate the tilt on realized crash depth instead. Expected effect (frozen): +0.0-0.15 %/mo
mostly via keeping 2021/2020p worst years, DD -0.0-0.5 pp. Prior 22 %. Round-trip ~4-8 bps
bounds every effect below.

## Variants (exactly two + reference, thresholds frozen ex-ante, never fit)

- REF = G2 unchanged (tilt 1), reproduction row (v421 R2B1D17BFG2).
- V1 = frozen C2 tilt multipliers applied ONLY when trailing-30d BTC max-DD-depth < 15 %,
  else 1.0.
- V2 = same with X = 10 %.
- X values are round numbers frozen ex-ante (15/10, never fit, never scanned). No other
  variant, no ensemble, no threshold tuning. C2 base multipliers hi/lo = 1.25/0.75,
  missing/NaN risk -> 1 (identical to oc_chronos), then the crash gate.

## Crash-depth definition (frozen, causal, no new data)

- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  BTCUSDT closes (existing 4h closes, no new data). Per phase shift s, series sorted by T
  (bar open; bar close time = T + 4h, known at the holding-bar open only for bars with
  close_time <= T).
- At holding-bar open T (tz-aware UTC) on shift s: window = BTC closes with
  close_time in (T - 30d, T] on that shift's grid (i.e. bars with open in
  [T - 30d, T - 4h]; nominal 180 bars). Let P = closes in window in time order.
  depth(T) = max_{i<j} (P_i - P_j) / P_i, floored at 0.0 (max intra-window
  peak-to-trough; 0 = no drawdown in window). NaN/empty (< 2 closes) -> NaN ->
  gate defaults to ALLOW (base C2 mult; inert in our years — history from 2020-08-01
  gives full 180-bar windows for all of 2021-09-24..2026-09-23; disclosed).
- Gate: allow(T) = depth(T) < X (strictly). Gated mult = base_C2(T) if allow else 1.0.
  Same allow(T) for all 5 coins (BTC regime). Fits of anchor A applied to year A on all
  four shifts. Most-recent-year fits = frozen 2025-09-24 fits.
- Unit-tested: hand-checked synthetic peak-to-trough + causality/truncation test
  (dropping later bars cannot change depth at kept times).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (ch_q10) +
  `research/tournament/oc_chronos/fits.json` (C2 per-anchor direction/q20/q80; all +1).
- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (BTC 4h closes for depth).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism +
  `assign_mult`/`anchor_of` copied verbatim; only the crash gate added).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline: dev years
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica
  ledger read-only; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- Expected copied C2 reference (labelled copied, not re-run): C2 dev
  [2.711,3.460,6.250,10.721] last 4.754 DDlast 12.86 fullDD 15.42 timing-Y4 99.20
  block 98.90 (oc_chronos REPORT/results.json).

## Part 1 — replica + placebo gate (CPU-only, no engine yet)

- For V1, V2: per fill in the reused ledger, key (sym, shift, T=bar open):
  base = assign_mult(-ch_q10, fits[A].direction/q20/q80, 1.25/0.75), missing -> 1;
  gated = base if depth_s(T) < X else 1.0.
- Per year y (4-phase means from ledger w*y): base(y), gated(y), realised_mean(y),
  norm(y) = gated(y)/realised_mean(y), gain(y) = norm(y) - basenorm(y).
  dSum5y = sum_y gated(y) - sum_y base(y) (4-phase-mean sums, w*y units).
- Timing placebo per year EXACTLY like oc_k2placebo (1000 within-year uniform bar-level
  permutations of the GATED multipliers over decision bars, seed 20261007+y;
  block-42 per (sym,shift) seed 20261008+y; percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95; perm norms use the ACTUAL realised-mean denominator).
  Bar universe per year = frozen chronos feature rows restricted to year y on each
  shift grid (same as oc_chronos/compute_placebo.py).
- Gate (IDEAS5 header): full PROMISING sum-half (gated sum >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). DISCLOSED LIMITATION: the
  k2placebo ledger carries no exit-date/daily path, so the replica DD-half
  (DD <= base + 0.01 in >= 4/5) cannot be scored at the replica stage; the binding DD
  check is the 4-phase engine (yearly DD + full-path DD <= 20). Timing percentiles are
  reported as supporting evidence, not binding. Engine runs ONLY for variants passing
  the sum-half + dSum5y gate. If neither passes, STOP with no engine (negative result).
- No statistic from any test year feeds any choice (depth uses closes <= T only;
  thresholds frozen; fits pre-anchor + 7d embargo inherited).

## Part 2 — 4-phase engine (only for gate-passing variants)

- Mechanism = exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware inv
  sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h,
  shorts 0; limit fill only on 1m trade-through; nothing in first 5 min after a 4h
  close; stop-first in shared 1m bar — engine handles).
- Rows run through the engine (ONLY): REF + each gate-passing variant (V1 and/or V2).
  C2 numbers stay COPIED reference (not re-run).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit, else STOP). Stage last runs [DEV0, Y1=2026-09-23)
  ONCE for REF + the dev4 robust pick only (every Y4 number labelled scored-once;
  REF Y4 must reproduce v421 G2 Y4 to the digit). No re-runs after outcomes; any change
  becomes a disclosed extra row. Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s.

## Metrics / selection (fixed)

- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + sized
  mean multiplier + crash-allow share (same collection as oc_beargate run_engine.py).
- Robust pick on dev4 ONLY among REF + engine-run gated variants: DD <= 20 and no
  losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly
  return, ties -> higher mean.
- Crash-allow share (no selection input): per year y (all 4 shifts pooled): bars share
  = fraction of decision holding-bars T in year y with depth(T) < X; fills share =
  fraction of D0-replica ledger fills in year y with depth(shift,T) < X. Both causal.

## Leakage / checks (stated in REPORT)

- Feature timing (ch_q10 frozen, inherits truncation test; depth: closes with
  close_time <= T only; truncation-tested in tests/test_oc_crashgate.py), label windows
  (harness t_exit < A - 7d inherited), fit windows (frozen C2 fits, shift-0 + 7d embargo
  inherited, anchor-y fit for year y; X frozen ex-ante, never fit; no statistic from any
  test year feeds any choice), fill timing (win_start=5 + 1m trade-through + stop-first,
  engine). Gate costs inside engine/replica. If the data named does not cover an anchor
  year, disclose and skip that year for that variant (never impute) — N/A here (4h
  closes cover all anchors).

## Compute plan (heavy_slot only for engine, resume-safe)

- `tilt_rule.py`: `assign_mult` + `anchor_of` copy + `crash_depth` + `gate_mult`
  (unit-tested).
- `build_crash.py`: CPU-only BTC closes -> `crash_depth_4shift.parquet`
  (sym=BTCUSDT, shift, T, depth) + `tmp/crashshare.json` (allow shares per year/X).
- `compute_placebo.py`: CPU-only gated replica sums + dSum5y + 1000-perm timing/block
  placebo for V1 + V2 on the reused ledger -> `tmp/placebo_crashgate.json`.
- `run_engine.py`: sequential shifts per stage, heartbeat 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl`. Via heavy_slot, one job, nohup + tmp log.
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json` + `tmp/last_table.json` (+ 5y + full-path DD).
- Deliverables: PLAN.md (this file), tilt_rule.py, build_crash.py, compute_placebo.py,
  run_engine.py, analyze.py, crash_depth_4shift.parquet, results.json, REPORT.md,
  tests/test_oc_crashgate.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_crashgate.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
