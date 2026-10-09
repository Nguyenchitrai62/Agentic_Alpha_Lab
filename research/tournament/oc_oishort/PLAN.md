# oc_oishort — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_oishort.md` (= IDEAS5 §6, rank 6) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS5_20261008.md` §6 + CLOSED rows read in full).
Write ONLY `research/tournament/oc_oishort/` + `tests/test_oc_oishort.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched — here only the engine touches 1m; gate math is OI-5m +
hourly only, float32 where large). Heartbeat print every 600 s in long jobs. Progress
print every ~10 min. Scratch only under `research/tournament/oc_oishort/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp).

## Why (IDEAS5 §6, rank 6)

Mirror of the unwind guard: 24h OI UP + price DOWN = crowded shorts building into a
falling tape = squeeze tail (Oct-2025: OI cleared 45-70% on Hyperliquid; CeFi/DeFi BTC
diverged 7.24% in 1 s). Program tested the long-crowd tail repeatedly, never the
short-crowd tail.
CLOSED rows read: `oc_i2_oiguard` (OI-DROP unwind skip, CLOSED NOT PROMISING: O1 dSum
-0.25, O2 -0.12 vs +0.273 gate; joint 24h OI+price <-2sigma DIP-bid skip, thin
~0.5-0.7% fires) and IDEAS4-H6 (OI-LEVEL long throttle, never engine-tested — different
tail/leg). This is the uncovered short-divergence cell (OI-RISE + price-FALL, BOOK
short leg, longs untouched), so kept per the IDEAS5 near-duplicate note.

## Variants (exactly two + reference, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- O1 = per-(T,sym) book-SHORT cover gate: if gate_O1(T,sym) true at decision bar T for
  coin sym, and the bear-filtered book weight < 0 (short), weight x0.5. Longs untouched.
  Dip untouched (tilt mult 1 everywhere).
- O2 = same with looser OI threshold: gate_O2(T,sym) with z > 1.5 (more events), shorts
  x0.5. Longs untouched. Dip untouched.
- No exposure-matched control (IDEAS5 §6 does not ask; §4-style control not applicable
  to a short-divergence veto; disclosed — same disclosure as `oc_vpinveto` §2).
- Frozen thresholds (never fit): OI lookback 24h, 5-min availability lag, z > 2.0 (O1) /
  z > 1.5 (O2), price < -2sg, trailing-1y norm window [A-372d, A-7d), 7-day embargo,
  x0.5, rows < 2021-09-24 never gated. All round numbers from IDEAS5, frozen ex-ante.

## OI-rise / price-fall gate (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited):
  `data/raw/um_metrics_20260926/<COIN>_metrics.parquet` (columns create_time,
  sum_open_interest; local; BTC 2020-09-01..2026-09-24, ETH/SOL/BNB/XRP
  2021-12-01..2026-09-24 per manifest.json — span check per anchor below; if a
  coin/anchor norm has <1000 samples the gate is never true there — disclosed skip,
  never imputed) + `research/tournament/ext/hourly_ext.parquet` (columns t, close,
  sym; t = hourly bar START UTC, bar END = t+1h; majors gap-free over the norm windows)
  for the price leg. `data/raw/metrics_ext_20260924/metrics_ext.parquet` is a redundant
  BTC-only subset (2026-03-23..2026-09-23) and is NOT used (same as `oc_i2_oiguard`;
  disclosed).
- Standard grid G = 4h closes {00,04,08,12,16,20 UTC} from 2020-09-01 00:00 to
  2026-09-24 00:00 UTC (freq 4h, tz UTC).
- OI leg (per coin, per T in G): OI_now(T) = last sum_open_interest with
  create_time <= T-5min (5-min lag per metrics_ext manifest point-in-time note);
  OI_24h(T) = same at <= T-24h-5min. dOI(T) = ln(OI_now/OI_24h); NaN if either
  missing/non-positive/non-finite. Uses ONLY OI rows available at T (no restated
  series; vintages as-of).
- Price leg (per coin, per T in G): C4(sym,T) = hourly close of the bar starting at
  T-1h (the last hourly bar with END <= T); NaN if missing. Single-step log return
  r(sym,T) = ln(C4(T)/C4(T-4h)); NaN if either close missing/non-positive. 24h return
  R24(sym,T) = ln(C4(T)/C4(T-24h)) = sum of the 6 single-step returns ending <= T
  (computed directly from closes 6 grid bars apart; NaN if either endpoint NaN).
  Trailing sigma sg(sym,T) = std(ddof=1) of the 360 single-step returns strictly before
  T (rets[t-360:t] ending at T-4h, causal shifted like the engine sig4); NaN unless
  >=120 finite values and sd > 0. Price condition P(sym,T) = finite(R24) AND
  finite(sg) AND R24 < -2*sg. All closes <= T only.
- Norms (walk-forward, pre-anchor + 7d embargo, frozen per anchor year):
  ANCH5 = 2021-09-24 .. 2025-09-24. For anchor A and coin sym: pool P(A,sym) =
  {dOI(T,sym): T in [A-372d, A-7d)} on G. Require >=1000 finite samples else mu/sd NaN
  (gate never true that year for that coin, disclosed). Else mu[A,sym], sd[A,sym] =
  mean/std(ddof=1) of P. Year y=[A, A+365d) uses mu/sd of its anchor A on all four
  phase shifts. No test-year data feeds any norm.
- z(T,sym) = (dOI(T,sym)-mu[A,sym])/sd[A,sym] (sd<=1e-12 or NaN -> never gate).
  gate_O1(T,sym) = finite(z) AND z > 2.0 (strictly greater) AND P(sym,T) true.
  gate_O2(T,sym) = finite(z) AND z > 1.5 (strictly greater) AND P(sym,T) true.
  NaN -> False. Rows with T < 2021-09-24 are never gated (frozen).
- Expected gate rate (IDEAS5: ~10-20 gate-bars/yr per coin so wide CI): reported, not
  selected on. Early-2021 non-BTC bars are gate-ineligible by construction (OI starts
  2021-12-01; 2021 anchor norms have 0 samples -> never gate; 2022 anchor norms are
  partial ~9.5mo -> disclosed, still >=1000 4h samples so gated).

## Engine (fixed; per-(T,sym) book-multiplier copy of vpinveto/beargate mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Book cover-gate applied AFTER the bear filter, BEFORE the shifted-clock forward fill:
  `sbb_O1 = sb.where(~(gate_O1 & (sb < 0)), sb*0.5)` where gate_O1 is the O1 gate
  DataFrame on the standard grid (T,sym); same for O2 with gate_O2. Longs (sb>0)
  untouched. Dip `tilt(i,a)` = 1.0 for ALL rows (book-side idea; dip sleeve untouched).
- Rows run through the engine (ONLY these three): REF, O1, O2.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the three rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) for the dev4 robust pick + REF ONLY, ONCE
  (every Y4 number labelled scored-once; REF Y4 must reproduce v421 G2 Y4 to digit).
  No re-runs after seeing outcomes; any change becomes a disclosed extra row.
- Long jobs: `nohup ... > tmp/<log> 2>&1 &` + poll the log (never inspect /proc);
  heartbeat every 600 s. Heavy via heavy_slot, one job, float32, one coin at a time
  inside compute.

## Metrics / gates (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + gated
  share of (T,sym) bars + sized mean book multiplier (same collection as
  oc_vpinveto/run_engine.py; dip tilt mult reports 1.0).
- Robust pick on dev4 ONLY among REF/O1/O2: DD <= 20 and no losing dev year; prefer
  dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return, ties -> higher mean.
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (OI rows with create_time <= T-5min only; hourly closes with END <= T
  only; gate-bar's own future flow never used; truncation-tested in
  tests/test_oc_oishort.py); label windows (no labels fit; norms/thresholds are
  unsupervised moments/quantiles, windows [A-372d,A-7d] only); fit windows (mu/sd
  frozen per anchor year, 7d embargo, no statistic from any test year feeds any choice);
  fill timing (win_start=5 + 1m trade-through + stop-first, engine). Gate costs inside
  the engine. No statistic from any test year feeds any choice.

## Compute plan (heavy_slot, resume-safe, one coin at a time, float32)

- `oishort_rule.py`: pure helpers (`log_change`, `trailing_sg`, `gate_short`,
  `anchor_of`) — no data access; unit-tested.
- `compute_oishort.py`: hourly -> 4h closes (float32) + OI as-of (5-min lag) -> dOI,
  R24, sg per (T,sym) -> per-anchor mu/sd (CSV/JSON) -> gate tables
  `gates_std.parquet` {(T): o1_BTC..o1_XRP, o2_BTC..} + `oishort_panel.parquet`
  (dOI/R24/sg/z per coin for audit). CPU-only except via heavy_slot (hourly+OI working
  set > 0.4 GB). Resume-safe per-step caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + REF) ->
  `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), oishort_rule.py, compute_oishort.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_oishort.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_oishort.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
