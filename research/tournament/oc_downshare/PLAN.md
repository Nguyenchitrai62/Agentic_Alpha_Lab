# oc_downshare — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_downshare.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS5_20261008.md idea #3 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_downshare/` + `tests/test_oc_downshare.py`. Scratch only under
`research/tournament/oc_downshare/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one engine job at a
time, load one coin at a time, float32). Long jobs: nohup + log file under tmp/, poll the log; never
inspect /proc or folders outside the workspace. Heartbeat print every 600 s in long jobs.
Progress print every 10 minutes (this study is CPU-light; prints at each stage).

## Why (IDEAS5_20261008.md idea #3, rank 3 — quoted, not refit)

Concordia HAR thesis 2025 (HAR-J best 1d, HAR-RS best 1w/1m; downside semivariance +
continuous variation robust; asymmetry beta- 0.34 vs beta+ 0.18) + HAR-RS-DOW 2026
(MCS-singleton, DM p < 0.005). Total vol says "how much"; downside share says "what kind" —
crash-type vol (high downside share) vs rebound-type vol. Expected effect (frozen):
+0.0-0.12 %/mo, DD -0.0-0.4 pp. Prior 11 %. Round-trip ~4-8 bps bounds every effect below.
NEAR-DUPLICATE NOTE (inherited): `oc_voltilt` (RV6-total/GARCH-total tilt, CLOSED as tilt) is
LEVEL; this is downside COMPOSITION — kept as the distinct HAR-RS axis. Disclosed as 1 of ~6
vol-tilt family members (multiplicity): C2/K2/T3/RV6/GARCH/downshare share the x1.25/x0.75
outer-quintile tilt form, so a positive here is family evidence, not an independent discovery.
CLOSED rows read first: `oc_voltilt` (PLAN/REPORT/tilt_rule/analyze/compute_placebo — LEVEL
tilt, C2 7/9 legs pattern, dev-mean +0.02..+0.04 but WORST-year dent, clean year < 5 % gate),
`oc_presampletilt` (pre-sample ledger method + frozen-2021-rule convention + COVID-leg failure),
`oc_chronos` (C2 tilt mechanism + `assign_mult` + placebo method copied), `oc_k2placebo`
(D0+B1 replica ledger reused read-only), `oc_crashgate` (replica+gate template for a dip tilt
that FAILED the gate with no engine run — the valid negative-outcome path followed here).

## Variants (exactly two + reference, thresholds frozen ex-ante, never fit)

- REF = G2 unchanged (tilt 1), reproduction row (v421 R2B1D17BFG2) — engine stage only.
- D1 = trailing-6d downside-RV share tilt (definition below), K2/C2 quintile form hi/lo 1.25/0.75.
- D2 = HAR-RS-style daily/weekly downside-share blend 0.6/0.4 (frozen weights) tilt, same form.
- hi/lo = 1.25/0.75 frozen (same K2/C2 outer-quintile form); missing/NaN risk -> 1.0.
- No other variant, no ensemble, no weight/threshold tuning (0.6/0.4 and 6d/1d/5d are frozen
  ex-ante from the assignment text, never scanned).

## Downside-share definitions (frozen, causal, existing 4h closes only — no new data)

- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open).
- Close-to-close log returns: r[i] = log(C[i]) - log(C[i-1)], r[0] = NaN (float64).
- Window helper (pure, unit-tested): share(rs) = sum(min(r,0)^2) / sum(r^2) over a finite
  window rs; NaN if any element non-finite, if len == 0, or if total <= 0 / non-finite.
  share in [0,1] by construction (0 = all upside, 1 = all downside, 0.5 ~ symmetric).
- D1 (6d share): at bar index E (bar open T[E]), window = r[E-36 .. E-1] (36 returns =
  6d x 6 bars/day, all of bars closing <= T[E]); requires E >= 37 and all 36 finite,
  else NaN -> causal by construction (only closes of bars closing <= T).
- D2 (HAR-RS blend): daily share_d = share(r[E-6 .. E-1]) (1d = 6 bars); weekly share_w =
  share(r[E-30 .. E-1]) (5d = 30 bars, HAR weekly convention); blend = 0.6*share_d +
  0.4*share_w (weights frozen); NaN if either leg NaN -> causal (same return timing).
- Output: `downshare_features_4shift.parquet` (sym, shift, T, risk_D1, risk_D2).
  T range = all T with E >= 37 (superset fine; engine/replica join is missing -> 1).
- Unit-tested: hand-checked synthetic windows (all-down=1, all-up=0, symmetric=0.5,
  zero-vol=NaN) + blend arithmetic + causality/truncation test (recompute from bars
  truncated at a cut date -> identical on the kept prefix).
- If the data named does not cover an anchor year: disclose and skip that year for that
  variant (never impute). N/A expected (4h closes from 2020-08-01 cover all anchors with
  full 36-bar windows; missing -> mult 1, counted and disclosed).

## Fits (frozen; harness rows only, shift-0, 7d embargo — identical to oc_voltilt)

- Per-anchor fit on harness training rows EXACTLY like oc_voltilt/make_fits.py: majors rows
  of harness.load() with t_exit < A - 7d AND shift-0 feature present (join on (sym, T)):
  risk = risk_D1 (resp. risk_D2); direction = sign of Spearman(risk, y_dep) (+1 if rho > 0
  else -1); edges q20/q80 of risk. Output `fits.json` with `D1` and `D2` sections
  (direction/q20/q80/rho/n). Exactly TWO variants. Most-recent-year fits use all harness
  rows with t_exit < 2025-09-17. Fits of anchor A applied to year A on all four shifts.
- Quintiles pre-anchor + 7d embargo; no statistic from any test year feeds any choice.

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (closes for D1/D2).
- `research/tournament/harness.py` (per-anchor fits; harness.load/folds/score).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json`
  row R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82) — engine stage only.
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica ledger
  read-only; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism + `assign_mult`
  copied verbatim; only the risk lookup changes) — engine stage only.
- Expected copied references (labelled copied, not re-run): C2 dev
  [2.711,3.460,6.250,10.721] last 4.754; V_RV6 dev [2.271,3.399,6.235,10.848] last 4.811;
  V_GARCH dev [2.398,3.265,6.447,10.571] last 4.932 (oc_voltilt REPORT/results.json).

## Part 1 — replica + placebo gate (CPU-only, no engine yet; BINDING)

- For D1, D2: per fill in the reused ledger, key (sym, shift, T=bar open):
  mult = assign_mult(risk, fits[A].direction/q20/q80, 1.25/0.75), missing -> 1.
- Per year y (4-phase means from ledger w*y, same phase_mean_sums as k2placebo/voltilt/
  crashgate): base(y), tilt(y), realised_mean(y), norm(y) = tilt(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). dSum5y = sum_y tilt(y) - sum_y base(y) (4-phase-mean
  sums, w*y units).
- Timing placebo per year EXACTLY like oc_k2placebo (1000 within-year uniform bar-level
  permutations of the variant multipliers over decision bars, seed 20261007+y; block-42
  per (sym,shift) seed 20261008+y; percentile = 100*(1+#{perm<=actual})/1001; significant
  iff >= 95; perm norms use the ACTUAL realised-mean denominator). Bar universe per year =
  frozen downshare feature rows restricted to year y on each shift grid (same construction
  as oc_voltilt/compute_placebo.py).
- Gate (IDEAS5 header): full PROMISING sum-half (tilt sum >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). DISCLOSED LIMITATION (pre-registered,
  same as oc_crashgate): the k2placebo ledger carries no exit-date/daily path, so the
  replica DD-half cannot be scored at the replica stage; the binding DD check is the 4-phase
  engine (yearly DD + full-path DD <= 20). Timing percentiles are supporting evidence, not
  binding. Engine runs ONLY for variants passing the sum-half + dSum5y gate. If neither
  passes, STOP with no engine (negative result, valid per IDEAS5).
- No statistic from any test year feeds any choice (shares use returns <= T only;
  thresholds/weights frozen; fits pre-anchor + 7d embargo inherited).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware inv
  sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first
  in shared 1m bar — engine handles).
- Rows run through the engine (ONLY): REF + each gate-passing variant (D1 and/or D2).
  FM/vol references stay COPIED (not re-run).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit, else STOP). Stage last runs [DEV0, Y1=2026-09-23)
  ONCE for REF + the dev4 robust pick only (every Y4 number labelled scored-once; REF Y4
  must reproduce v421 G2 Y4 to the digit). No re-runs after outcomes; any change becomes
  a disclosed extra row. Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`;
  dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24; pooled book/rung/all win rates + fills/year +
  sized mean multiplier (same collection as oc_voltilt). Robust pick on dev4 ONLY among
  REF + engine-run variants: DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then
  highest dev4 WORST-year monthly return, ties -> higher mean.

## Leakage / checks (stated in REPORT)

- Feature timing (D1: 36 closes <= T; D2: 30 closes <= T via the weekly leg; truncation-tested
  in tests/test_oc_downshare.py), label windows (harness t_exit < A - 7d inherited), fit windows
  (shift-0 only + 7d embargo, anchor-y fit for year y; no labels in feature build), fill timing
  (replica live 16..238 strict trade-through + stop-first inherited; engine win_start=5 +
  trade-through + stop-first if reached). No statistic from any test year feeds any choice.
  Gate costs inside replica outcomes / engine. Coverage: disclose any skipped anchor year
  (none expected; missing feature -> mult 1, counted).

## Compute plan (heavy_slot only for engine, resume-safe)

- `tilt_rule.py`: `assign_mult` + `anchor_of` copy + `share_of`/`blend` pure helpers (unit-tested).
- `build_downshare.py`: CPU-only 4h closes -> `downshare_features_4shift.parquet` (fast, < 2 min).
- `make_fits.py`: CPU-only harness join -> `fits.json`.
- `compute_replica_gate.py`: CPU-only tilted replica sums + dSum5y + 1000-perm timing/block
  placebo for D1 + D2 on the reused ledger -> `tmp/replica_downshare.json`.
- `run_engine.py` + `analyze.py`: ONLY if a variant passes the gate (same shape as
  oc_voltilt/run_engine.py + analyze.py; REF reproduction gate first).
- Deliverables: PLAN.md (this file), tilt_rule.py, build_downshare.py, make_fits.py,
  compute_replica_gate.py, (run_engine.py + analyze.py only if gated), downshare_features_4shift.parquet,
  fits.json, results.json, REPORT.md, tests/test_oc_downshare.py (>=1 causality/truncation
  test + >=1 hand-checked synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_downshare.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
