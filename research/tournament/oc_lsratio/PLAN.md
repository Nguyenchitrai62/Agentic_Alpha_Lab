# oc_lsratio — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_lsratio.md` (= IDEAS5 §7, rank 7) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS5_20261008.md` §7 + CLOSED rows read in full).
Write ONLY `research/tournament/oc_lsratio/` + `tests/test_oc_lsratio.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched — here only the engine touches 1m; gate math is
5-min metrics only, float32 where large). Heartbeat print every 600 s in long jobs.
Progress print every ~10 min. Scratch only under `research/tournament/oc_lsratio/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp).

## Why (IDEAS5 §7, rank 7)

2026 cascade panel: top-trader long/short ratio is the ONLY variable with the
pre-cascade signature in both Oct-2025 and Aug-2024 (16-17/39 configs);
positioning helped only 2023 as a member (DATA LEADERBOARD) — as a contrarian
GATE it was never isolated. CLOSED rows read: `oc_i2_oiguard` (OI-DROP unwind
skip, CLOSED NOT PROMISING) and IDEAS4-H6 (OI-LEVEL long throttle, never
engine-tested) are the opposite tails/legs (OI level/drop, long crowd); this is
the uncovered top-trader-ratio contrarian cell (RATIO level extremes, BOOK leg),
so kept per the IDEAS5 near-duplicate note. Prior 8%. Expected effect
+0.0-0.08 %/mo, DD -0.0-0.3 pp.

## Variants (exactly two + reference, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- L1 = per-(T,sym) book-LONG contrarian gate: if gate_long(T,sym) true at decision
  bar T for coin sym, and the bear-filtered book weight > 0 (long), weight x0.5.
  Shorts untouched. Dip untouched (tilt mult 1 everywhere).
- L2 = SYMMETRIC both sides: L1 PLUS per-(T,sym) book-SHORT contrarian gate: if
  gate_short(T,sym) true and the bear-filtered book weight < 0 (short), weight
  x0.5. Long gate identical to L1. Dip untouched (tilt mult 1 everywhere).
  (IDEAS5 says "L2 symmetric (ratio < p10 -> shorts x0.5)"; interpreted as L1 +
  short side — the only reading under which L2 is symmetric; disclosed.)
- No exposure-matched control (IDEAS5 §7 does not ask; §4-style control not
  applicable to a positioning-contrarian veto; disclosed — same disclosure as
  `oc_vpinveto` §2 / `oc_oishort` §6).
- Frozen thresholds (never fit): ratio = Binance `count_toptrader_long_short_ratio`
  (top-trader LONG/SHORT ACCOUNT ratio; `sum_` = positions, not used — disclosed),
  5-min availability lag, trailing-1y quantile window [A-372d, A-7d), 7-day
  embargo, p90 (longs) / p10 (shorts, L2 only), x0.5, rows < 2021-09-24 never
  gated. All round numbers from IDEAS5, frozen ex-ante.

## LS-ratio contrarian gate (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited):
  `data/raw/um_metrics_20260926/<COIN>_metrics.parquet` (columns create_time,
  count_toptrader_long_short_ratio; local; BTC 2020-09-01..2026-09-24,
  ETH/SOL/BNB/XRP 2021-12-01..2026-09-24 per manifest.json — span check per
  anchor below; EXCHANGE-WIDE gap: count ratio NaN for most of 2022-01..2022-12
  on all 5 coins, plus 400 NaN rows in 2021-12; if a coin/anchor norm has <1000
  finite samples the gate is never true there — disclosed skip, never imputed).
  `data/raw/metrics_ext_20260924/metrics_ext.parquet` is a redundant BTC-only
  subset and is NOT used (same as `oc_oishort`; disclosed).
- Standard grid G = 4h closes {00,04,08,12,16,20 UTC} from 2020-09-01 00:00 to
  2026-09-24 00:00 UTC (freq 4h, tz UTC).
- Ratio leg (per coin, per T in G): LS(T) = last count_toptrader_long_short_ratio
  with create_time <= T-5min (5-min lag, same as `oc_oishort`; excludes the bar
  exactly at T; uses ONLY rows available at T, no restated series). NaN if no
  such row, or value non-finite / <= 0.
- Norms (walk-forward, pre-anchor + 7d embargo, frozen per anchor year):
  ANCH5 = 2021-09-24 .. 2025-09-24. For anchor A and coin sym: pool P(A,sym) =
  {LS(T,sym): T in [A-372d, A-7d)} on G. Require >=1000 finite samples else
  p90/p10 NaN (gate never true that year for that coin, disclosed per-coin/year,
  never imputed). Else p90[A,sym], p10[A,sym] = 90th/10th percentiles of P
  (numpy linear interpolation). Year y=[A, A+365d) uses p90/p10 of its anchor A
  on all four phase shifts. No test-year data feeds any norm. Thresholds p90/p10
  frozen from literature (IDEAS5), never fit.
- gate_long(T,sym) = finite(LS) AND finite(p90[A,sym]) AND LS > p90 (strictly
  greater). gate_short(T,sym) = finite(LS) AND finite(p10[A,sym]) AND LS < p10
  (strictly less). NaN -> False. Rows with T < 2021-09-24 are never gated (frozen).
- Coverage disclosure (pre-registered expectation, exact n reported by compute):
  y0 (A=2021-09-24): BTC norm full (~2190 4h samples); non-BTC 0 samples ->
  never gate non-BTC in y0. y1 (A=2022-09-24): norm window covers the 2022 gap ->
  partial/thin (likely <1000 for all coins -> mostly gate-off; disclosed). y2-y4
  anchors: full/near-full windows. Test-year NaNs (2022 calendar gap) -> never
  gate there (no imputation). Per assignment, coin-years without norm coverage are
  disclosed-skipped for that coin-year (gate-off); the engine still scores REF
  every year.
- Expected gate rate: ~10% of bars per side by construction where norms exist
  (p90/p10); reported, not selected on.

## Engine (fixed; per-(T,sym) book-multiplier copy of oishort/vpinveto mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Book gates applied AFTER the bear filter, BEFORE the shifted-clock forward fill:
  `sbb_L1 = sb.where(~(gate_long & (sb > 0)), sb*0.5)`;
  `sbb_L2 = sb.where(~(gate_long & (sb > 0)), sb*0.5).where(~(gate_short & (sb < 0)), sb*0.5)`
  where gate_long/gate_short are the LS gates on the standard grid (T,sym).
  Longs (sb>0) untouched by the short gate and vice versa. Dip `tilt(i,a)` = 1.0
  for ALL rows (book-side idea; dip sleeve untouched).
- Rows run through the engine (ONLY these three): REF, L1, L2.
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
  oc_oishort/run_engine.py; dip tilt mult reports 1.0).
- Robust pick on dev4 ONLY among REF/L1/L2: DD <= 20 and no losing dev year; prefer
  dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return, ties -> higher mean.
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (LS rows with create_time <= T-5min only; never the gate bar's
  own contemporaneous/future print; truncation-tested in
  tests/test_oc_lsratio.py); label windows (no labels fit; norms/thresholds are
  unsupervised quantiles, windows [A-372d,A-7d] only); fit windows (p90/p10
  frozen per anchor year, 7d embargo, no statistic from any test year feeds any
  choice); fill timing (win_start=5 + 1m trade-through + stop-first, engine).
  Gate costs inside the engine. No statistic from any test year feeds any choice.

## Compute plan (heavy_slot, resume-safe, one coin at a time, float32)

- `lsratio_rule.py`: pure helpers (`asof_ratio`, `gate_long`, `gate_short`,
  `anchor_of`) — no data access; unit-tested.
- `compute_lsratio.py`: per-coin as-of LS(T) on G (float32, one coin at a time)
  -> per-anchor p90/p10 (JSON) -> gate tables `gates_std.parquet`
  {(T): long_BTC..long_XRP, short_BTC..short_XRP} + `lsratio_panel.parquet`
  (LS/p90/p10 per coin for audit). CPU-only except via heavy_slot (metrics
  working set > 0.4 GB). Resume-safe per-step caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + REF) ->
  `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), lsratio_rule.py, compute_lsratio.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_lsratio.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_lsratio.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
