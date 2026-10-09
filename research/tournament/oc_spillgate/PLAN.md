# oc_spillgate — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_spillgate.md` (= IDEAS5 §4, rank 4) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS5_20261008.md` §4 + CLOSED row `oc_corrbudget` read in full).
Write ONLY `research/tournament/oc_spillgate/` + `tests/test_oc_spillgate.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched — here only the engine touches 1m; gate math is 4h/hourly
only, float32 where large). Heartbeat print every 600 s in long jobs. Progress print
every ~10 min. Scratch only under `research/tournament/oc_spillgate/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp).

## Why (IDEAS5 §4, rank 4)

SA-Log-HAR 2025 (arXiv 2507.22409: state-adaptive quantile spillovers R2oos ~0.77 vs
GARCH negative; two-tail amplification; size != systemic importance): when spillovers
spike, all 5 majors move as one block and the book's one-way concentration
(`oc_ddanat_g2`) is maximally crowded. Binary spillover gate + exposure-matched
constant control distinguishes a timing edge from a mere exposure cut.
CLOSED row read: `oc_corrbudget` (corr SCALING 30d-hourly 1/(1+c) on the DIP sleeve,
CLOSED as NOT PROMISING: E1 seq 1/5, LOYO 0/5, scaler retention 0.54-0.62) — that was
continuous DIP-budget scaling on a slow 30d level; this is a binary BOOK gate on a
fast 24h level (S1) and on the 24h CHANGE spike (S2), different leg (book), different
timescale (24h vs 30d), different functional form (binary vs continuous) + control —
so kept per the IDEAS5 near-duplicate note.

## Variants (exactly two + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- S1 = market-wide book gate on the correlation LEVEL: if gate_S1(T) true at book-bar
  T, whole book row x0.5 (longs AND shorts, after the exact v421 bear filter, before
  the shifted-clock forward fill). Dip untouched (tilt mult 1 everywhere).
- S2 = market-wide book gate on the correlation 24h CHANGE spike: if gate_S2(T) true,
  whole book row x0.5 (same placement). Dip untouched.
- C1 = exposure-matched constant control for S1 (DIAGNOSTIC, in-year, not tradable):
  per anchor year y, constant book multiplier m_C1[y] = 1 - 0.5*share_S1[y] applied to
  the whole book row every bar of that year (after bear, before ffill), where
  share_S1[y] = fraction of standard-grid 4h closes T in [A_y, A_y+365d) with
  gate_S1(T) true. Same for C2 with share_S2/m_C2. Control uses the in-year share
  (like `oc_premexpo`'s in-year average exposure) and is therefore a diagnostic that
  isolates timing from exposure; it is not a tradable rule.
- Claim rule (frozen): S1 (resp S2) "beats exposure" iff dev4 geometric mean R(S) >
  R(C) AND DDmax(S) <= DDmax(C). A gate that trails its control is an exposure story,
  not timing alpha — reported as such.
- Frozen numbers (never fit): trailing return window 24h (6x4h bars), trailing norm
  window 1y (365d), 7-day embargo, S1 threshold p90, S2 threshold p95, scale x0.5.
  All round numbers from IDEAS5, frozen ex-ante.

## Spillover gate (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited): `research/tournament/ext/hourly_ext.parquet` ONLY
  (columns t, close, sym; t = bar START UTC, bar END = t+1h; majors BTC/ETH/SOL/BNB/XRP
  gap-free over the norm windows; SOL starts 2020-08 hourly here, so every anchor norm
  window [A-372d, A-7d] is covered — if any anchor norm has <1000 valid c samples the
  gate is never true that year: disclosed skip, never imputed).
- 4h closes on the standard grid G = {00,04,08,12,16,20 UTC}: C4(sym, T) = hourly close
  of the bar starting at T-1h (the last hourly bar with END <= T); NaN if that hourly
  bar is missing. 4h log return r(sym, T) = log(C4(sym,T)/C4(sym,T-4h)); NaN if either
  close missing/non-positive.
- Level c(T): trailing 24h window W(T) = the 6 four-hour returns with end in (T-24h, T]
  (strictly <= the 4h bar close T; never future data). For each of the 10 coin pairs,
  Pearson correlation over pairwise-complete overlapping finite returns in W(T); a pair
  is NaN if <5 overlapping points or either leg has zero variance (sd<=0). c(T) = mean
  of the non-NaN pairs; NaN if <8 of 10 pairs valid. c(T) uses ONLY closes <= T.
  Warm-up: c valid from the 6th 4h bar after hourly start; earlier T are NaN (never gate).
- Change d(T) = c(T) - c(T-24h), where c(T-24h) is the level 6 grid bars earlier; NaN if
  either endpoint NaN. d(T) uses ONLY closes <= T.
- Norms (walk-forward, pre-anchor + 7d embargo, frozen per anchor year):
  ANCH5 = 2021-09-24 .. 2025-09-24. For anchor A: pool P_c(A) = {c(T): T in [A-372d,
  A-7d)} on the standard grid; pool P_d(A) = {d(T): same window}. Require >=1000 finite
  samples else thresholds NaN (gate never true that year, disclosed). q90(A) = 90th
  percentile of P_c(A); q95(A) = 95th percentile of P_d(A) (linear interpolation,
  numpy default). Year y=[A, A+365d) uses q90/q95 of its anchor A on all four phase
  shifts. No test-year statistic feeds any threshold.
- Gates at book-bar T (standard grid; engine forward-fills books to holding bars with
  the same causal ffill, so the gate sees exactly the state the books saw):
  gate_S1(T) = finite(c(T)) AND finite(q90[A(T)]) AND c(T) > q90[A(T)];
  gate_S2(T) = finite(d(T)) AND finite(q95[A(T)]) AND d(T) > q95[A(T)];
  NaN -> False. Rows with T < 2021-09-24 are never gated (frozen).
- Expected gate rate (IDEAS5 prior: S1 ~10% of bars by construction on stationary data,
  S2 ~5%; realized rates reported, not selected on).

## Engine (fixed; per-bar book-multiplier copy of vpinveto/beargate mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Gate applied AFTER the bear filter, BEFORE the shifted-clock forward fill, on the
  standard grid: `sbb_S1 = sb.where(~gate_S1_std, sb*0.5)` (gate_S1_std broadcast over
  all 5 sym columns); same for S2; `sbb_C1 = sb*m_C1[anchor_of(T)]` per-row constant
  (m from the gate's own year); same for C2. Dip `tilt(i,a)` = 1.0 for ALL five rows
  (book-side idea; dip sleeve untouched).
- Rows run through the engine (ONLY these five): REF, S1, S2, C1, C2.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the five rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4 robust pick + its
  matched control ONLY (every Y4 number labelled scored-once; REF Y4 must reproduce
  v421 G2 Y4 to the digit). No re-runs after seeing outcomes; any change becomes a
  disclosed extra row.
- Long jobs: `nohup ... > tmp/<log> 2>&1 &` + poll the log; heartbeat every 600 s.

## Metrics / gates (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + gated
  share of book bars + sized mean book multiplier (same collection as
  oc_vpinveto/run_engine.py; dip tilt mult reports 1.0).
- Robust pick on dev4 ONLY among S1/S2 (controls are diagnostics, REF is baseline):
  eligible iff DDmax <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo, then
  highest dev4 WORST-year monthly return, ties -> higher mean. (If none eligible, pick
  = "none-eligible" and the last stage runs REF only.)
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (4h closes <= T only; c/d from returns ending <= T; gate-bar's own
  future flow never used; truncation-tested in tests/test_oc_spillgate.py); label
  windows (no labels fit; thresholds are unsupervised quantiles); fit windows
  (q90/q95 from [A-372d,A-7d) per anchor, 7d embargo, frozen per year, no statistic
  from any test year feeds any choice); fill timing (win_start=5 + 1m trade-through +
  stop-first, engine). Gate costs inside the engine. No statistic from any test year
  feeds any choice.

## Compute plan (heavy_slot, resume-safe)

- `spill_rule.py`: pure helpers (`pairwise_mean_corr`, `gate_level`, `gate_change`,
  `anchor_of`, `control_mult`) — no data access; unit-tested.
- `compute_spill.py`: hourly -> 4h closes (float32) -> c(T), d(T) -> per-anchor q90/q95
  (CSV) -> gate tables `gates_std.parquet` {(T): s1, s2} + control constants
  `controls.json` {m_C1/m_C2 per anchor}. CPU-only; via heavy_slot (hourly parquet
  > 0.4 GB working set). Resume-safe per-step caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + matched control +
  REF) -> `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), spill_rule.py, compute_spill.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_spillgate.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_spillgate.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
