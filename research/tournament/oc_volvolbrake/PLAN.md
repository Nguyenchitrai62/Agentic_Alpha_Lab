# oc_volvolbrake — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_volvolbrake.md` (= IDEAS8 §8, rank 8) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS8_20261008.md` §8 + CLOSED rows read in full).
Write ONLY `research/tournament/oc_volvolbrake/` + `tests/test_oc_volvolbrake.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched — here only the engine touches 1m; gate math is 4h/hourly
only, float32 where large). Heartbeat print every 600 s in long jobs. Progress print
every ~10 min. Scratch only under `research/tournament/oc_volvolbrake/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp). CPU training only (no heavy local GPU).

## Why (IDEAS8 §8, rank 8)

Gates on LEVELS rarely transfer (bookfunding/fundclock, voltilt); crash legs announce
via second-moment instability (HAR-RS-DOW 2026: downside composition matters; cascade
panel: variance compression precedes). Brake on vol INSTABILITY, not level.
CLOSED rows read in full:
- `oc_bookvol` (vol-LEVEL target 60d book / risk-parity / slow120 / semivariance,
  CLOSED as NOT PROMISING: Sharpe 2-3/5, DD 5/5 for risk-parity/slow but Sharpe fail)
  — that scales on the LEVEL of realised vol; this gates on the vol-OF-vol
  (std of daily RV6), a distinct second-moment axis.
- `oc_spillgate` (24h mean-pairwise-corr LEVEL S1 + 24h CHANGE spike S2 book x0.5 gate,
  CLOSED: both trail REF on dev4 mean and trail their exposure-matched constants;
  gated spike bars are above-average bars) — that gates on cross-asset CORR level/change;
  this gates on single-asset (BTC) second-moment instability; same control lesson kept
  (spike bars must be shown not-above-average via the constant control).
- `oc_fundclock` (funding settlement-CLOCK flatten, CLOSED: W2 dev4 +0.56 but clean
  year -0.16, FAILS gate (b)) — that is a funding-clock gate; this is a vol-of-vol
  regime gate, different signal family.
So kept per the IDEAS8 near-duplicate note. Prior: ~0 return (+-0.05), DD -0-0.4pp
(tail buy). Prior 7% return / 10% DD.

## Variants (exactly two + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- V1 = vol-of-vol fragility brake p90: if gate_V1(T) true at book-bar T, whole book
  row x0.5 (longs AND shorts, after the exact v421 bear filter, before the
  shifted-clock forward fill). Dip untouched (tilt mult 1 everywhere).
- V2 = same with p85 threshold (gate_V2(T)). Dip untouched.
- C1 = exposure-matched constant control for V1 (DIAGNOSTIC, in-year, not tradable):
  per anchor year y, constant book multiplier m_C1[y] = 1 - 0.5*share_V1[y] applied to
  the whole book row every bar of that year (after bear, before ffill), where
  share_V1[y] = fraction of standard-grid 4h closes T in [A_y, A_y+365d) with
  gate_V1(T) true. Same for C2 with share_V2/m_C2. Control uses the in-year share
  (like `oc_premexpo`/`oc_spillgate` in-year average exposure) and is therefore a
  diagnostic that isolates timing from exposure; it is not a tradable rule.
- Claim rule (frozen): V1 (resp V2) "beats exposure" iff dev4 geometric mean R(V) >
  R(C) AND DDmax(V) <= DDmax(C). A gate that trails its control is an exposure story,
  not timing alpha — reported as such (oc_spillgate lesson).
- Frozen numbers (never fit): BTC 4h log returns, RV6 window 6x4h bars (24h),
  daily sampling at 00 UTC, fragility window 30 days, trailing norm window 1y (365d),
  7-day embargo, V1 threshold p90, V2 threshold p85, scale x0.5.
  All round numbers from IDEAS8, frozen ex-ante.

## Fragility gate (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited): `research/tournament/ext/hourly_ext.parquet` ONLY
  (columns t, close, sym; t = bar START UTC, bar END = t+1h; BTCUSDT only for the
  signal; gap-free over the norm windows; if BTC hourly missing the 4h close is NaN
  and the gate is False there — never imputed).
- 4h closes on the standard grid G = {00,04,08,12,16,20 UTC} from GRID_START
  2020-08-04 00:00 UTC to GRID_END 2026-09-23 20:00 UTC:
  C4(T) = hourly close of the bar starting at T-1h (the last hourly bar with
  END <= T); NaN if that hourly bar is missing. C4(T) uses ONLY hourly bars
  ending <= T.
- 4h log return r(T) = log(C4(T)/C4(T-4h)); NaN if either close missing/non-positive.
- RV6(T) = std(ddof=1) of the 6 log returns with end in (T-24h, T] (6 values ending
  <= T; requires 6 finite else NaN). RV6(T) uses ONLY closes <= T.
  (Same RV6 construction as oc_voltilt `r.rolling(6).std()`, here unshifted because
  returns already end <= T; voltilt shifted because its r was close-to-close indexed
  differently — disclosed equivalence.)
- Daily RV series: D(d) = RV6(T = d 00:00 UTC) for each calendar day d (the 00 UTC
  4h bar). NaN if RV6 NaN there.
- Fragility f(T): for 4h bar T on calendar day d = date(T) (UTC), let
  pool(T) = {D(d-30), ..., D(d-1)} (30 daily values on days strictly before T's day).
  f(T) = std(ddof=1) of pool(T); NaN if < 30 finite values. f is constant within a
  day and uses ONLY closes <= (d-1) 00:00 UTC < T — strictly pre-day, causal.
  Warm-up: f valid from the 31st daily 00 UTC bar after hourly start; earlier T NaN.
- Norms (walk-forward, pre-anchor + 7d embargo, frozen per anchor year):
  ANCH5 = 2021-09-24 .. 2025-09-24. For anchor A: pool P(A) = {f(T): T in
  [A-372d, A-7d)} on the standard grid. Require >= 1000 finite samples else
  thresholds NaN (gate never true that year, disclosed skip, never imputed).
  q90(A) = 90th percentile of P(A); q85(A) = 85th percentile of P(A) (linear
  interpolation, numpy default). Year y = [A, A+365d) uses q90/q85 of its anchor A
  on all four phase shifts. No test-year statistic feeds any threshold.
- Gates at book-bar T (standard grid; engine forward-fills books to holding bars with
  the same causal ffill, so the gate sees exactly the state the books saw):
  gate_V1(T) = finite(f(T)) AND finite(q90[A(T)]) AND f(T) > q90[A(T)] (strict);
  gate_V2(T) = finite(f(T)) AND finite(q85[A(T)]) AND f(T) > q85[A(T)] (strict);
  NaN -> False. Rows with T < 2021-09-24 are never gated (frozen).
- Expected gate rate (IDEAS8 prior: V1 ~10% of bars by construction on stationary
  data, V2 ~15%; realized rates reported, not selected on).

## Engine (fixed; per-bar book-multiplier copy of vpinveto/spillgate/beargate mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Gate applied AFTER the bear filter, BEFORE the shifted-clock forward fill, on the
  standard grid: `sbb_V1 = sb.where(~gate_V1_std, sb*0.5)` (gate_V1_std broadcast over
  all 5 sym columns); same for V2; `sbb_C1 = sb*m_C1[anchor_of(T)]` per-row constant
  (m from the gate's own year); same for C2. Dip `tilt(i,a)` = 1.0 for ALL five rows
  (book-side idea; dip sleeve untouched).
- Rows run through the engine (ONLY these five): REF, V1, V2, C1, C2.
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
  oc_spillgate/run_engine.py; dip tilt mult reports 1.0).
- Robust pick on dev4 ONLY among V1/V2 (controls are diagnostics, REF is baseline):
  eligible iff DDmax <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo, then
  highest dev4 WORST-year monthly return, ties -> higher mean. (If none eligible, pick
  = "none-eligible" and the last stage runs REF only.)
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (BTC 4h closes <= T only; r/RV6 from closes ending <= T; f(T) from
  daily D on days strictly before T's day; gate-bar's own future flow never used;
  truncation-tested in tests/test_oc_volvolbrake.py); label windows (no labels fit;
  thresholds are unsupervised quantiles); fit windows (q90/q85 from [A-372d,A-7d)
  per anchor, 7d embargo, frozen per year, no statistic from any test year feeds any
  choice); fill timing (win_start=5 + 1m trade-through + stop-first, engine). Gate
  costs inside the engine. No statistic from any test year feeds any choice.

## Compute plan (heavy_slot, resume-safe)

- `volvol_rule.py`: pure helpers (`rv6`, `fragility`, `gate_level`, `anchor_of`,
  `control_mult`) — no data access; unit-tested.
- `compute_volvol.py`: hourly BTC -> 4h closes (float32) -> r/RV6/D/f -> per-anchor
  q90/q85 (JSON) -> gate tables `gates_std.parquet` {(T): v1, v2, f} + control
  constants `controls.json` {m_C1/m_C2 per anchor}. CPU-only; via heavy_slot (hourly
  parquet > 0.4 GB working set). Resume-safe per-step caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + matched control +
  REF) -> `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), volvol_rule.py, compute_volvol.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_volvolbrake.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_volvolbrake.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
