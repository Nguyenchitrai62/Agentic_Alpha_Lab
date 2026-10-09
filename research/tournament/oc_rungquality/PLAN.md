# oc_rungquality — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_rungquality.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS5_20261008.md idea #9 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_rungquality/` + `tests/test_oc_rungquality.py`. Scratch only under
`research/tournament/oc_rungquality/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. No engine / heavy 1m work in Part 1 (CPU-only reuse of stored ledgers,
pandas+numpy, RAM < 1 GB); any Part 2 engine run would go via `scripts/heavy_slot.py` (one job at a time,
one coin at a time, float32, nohup + tmp log, heartbeat every 600 s). Never inspect /proc or folders
outside the workspace. Progress print at each stage (CPU-light study).

## Why (IDEAS5_20261008.md idea #9, rank 9 — quoted, not refit)

`oc_ladderfill` (n=21389 paired rungs, win 0.687, +17.76 bps mean) + `oc_filltime` (late fills trail
10-39 bps 4/5y) describe rung heterogeneity but no rule ever selected rungs by quality; `oc_rungcap`
(count cap, CLOSED NOT PROMISING: 0/5 sum-half, removed 4th/5th rungs win 72-83% @ +15..+83 bps) and
`oc_rungspace` (spacing, CLOSED NOT PROMISING: 1/5 sum-half) are quantity, not quality.
Rule (causal, frozen): from trailing-90d pre-anchor replica ledgers per (coin, rung depth): skip rungs
with stop-given-fill rate > p80 (F1); F2 = F1 + skip rungs with fill rate < p20 (chronic non-fillers).
Depths/stops/TP unchanged. Veto is skip-only (never re-peg). Expected effect (frozen): +0.0-0.08 %/mo,
DD -0.0-0.3 pp. Prior 8 %. Round-trip ~4-8 bps bounds every effect below.
CLOSED rows read first: `oc_ladderfill` (PLAN/REPORT/analyze — pairing + fill-minute + exit-mix method
copied), `oc_filltime` (PLAN/REPORT — LATE-relative-drag result, truncation-test convention copied),
`oc_rungcap` (PLAN/REPORT — per-(coin,bar) skip executability + raw-exposure scoring discussion),
`oc_rungspace` (REPORT — wider-spacing DD-cut-vs-sum-loss lesson), `oc_k2placebo` (PLAN — reused-ledger
+ reproduction-gate + placebo-seed convention), `oc_placebo_dip` (REPORT — PROMISING legs + pooled
p95 +0.273 gate), `oc_downshare` (PLAN/REPORT/compute_replica_gate — replica+gate template for a dip
idea where one variant passed and one failed; gate rule + disclosed replica-DD limitation followed).

## Variants (exactly two + base, thresholds frozen ex-ante, never fit)

- BASE = unfiltered replica (skip set empty every year).
- F1 = skip cells (coin, depth) with trailing stop-given-fill rate > p80 (strictly greater; == keeps).
- F2 = F1 union skip cells with trailing fill rate < p20 (strictly less; == keeps).
- Cells: 25 = 5 majors (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT) x 5 R2 depths (2.5/3.0/3.5/4.0/5.0).
  Rung index 0..4 maps to depths (2.5, 3.0, 3.5, 4.0, 5.0) = `compute_placebo_dip.RUNGS` order.
- p80/p20 = numpy linear quantiles across cells per anchor (stop-rate quantile over cells with
  n_fill >= 10 only; fill-rate quantile over all 25 cells). p80/p20 are round free quantiles, never
  scanned, never refit. min_n = 10 frozen (cells with fewer trailing fills get stop_rate NaN and are
  never F1-skipped; they remain eligible for the F2 fill-rate skip — that is the point of F2).
- No other variant, no ensemble, no threshold tuning, no re-pegging, no depth/stop/TP change.

## Quality-stat definitions (frozen, causal, no new data pull)

- Stats ledger (read-only): `research/tournament/oc_kpi/events_s{0..3}.parquet` (R2B1D17BF replica,
  shifts 0..3, majors, live 2021-09-24..2026-09-23). Pairing FIFO per (shift, symbol) in time order —
  exact copy of `oc_ladderfill/analyze_ladderfill.py::pair_shift` (labelled copy in `quality.py`).
  Depth/weight/fill_t from the `rung_fill` row; exit kind/exit_t/ret from the matched exit row.
  STOP = matched exit kind == `rung_sl` (the replica's stop leg; backstop touches resolve through the
  same engine exit and appear here as `rung_sl`; TP = `rung_tp`, flat = `rung_timeout`; disclosed).
- Holding-bar open T per fill: T = fill_t minus `fill_minute(fill_t, shift)` (exact copy of the
  ladderfill per-shift-grid formula: bars open at hours = shift mod 4; f in 16..238). Unit-tested.
- Window per anchor A: W(A) = paired rungs with T in [A - 97d, A - 7d) AND exit_t < A - 7d
  (belt-and-braces; dt <= 240 min so the T bound already implies the exit bound; both checked).
  90-day length. Uses only fills with t_exit < anchor - 7d (IDEAS5 leakage note).
- Per cell c in W(A): n_fill(c), n_stop(c), stop_rate(c) = n_stop/n_fill (NaN if n_fill < 10),
  fill_rate(c) = n_fill(c) / N_bar(A) where N_bar(A) = calendar number of 4h bars with open in
  [A - 97d, A - 7d) pooled over the 4 shifts (same denominator for every cell, so the p20 ranking
  equals the n_fill ranking; rates reported for readability, counts used in tests).
- Depths come from sigma360 <= signal close by construction (replica levels lv = O(T)*(1-k*sg(T))
  with sg known at the bar open; stats join is (coin, depth) only — no price read at test time).
- PRE-REGISTERED 2021 LIMITATION: W(2021-09-24) = [2021-06-19, 2021-09-17) predates the stats ledger
  (first paired fill 2021-10-15) so it is EMPTY: 2021 gets an empty skip set (no skip, filt == base),
  disclosed and kept in the 5-year gate as a tie (never imputed, no statistic from any test year used).
  Anchors 2022-2025 have full in-live trailing windows. No anchor year is dropped from scoring.

## Frozen eval inputs (read-only, never edited, never refit)

- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `tmp/bt_all.npy` (D0+B1 replica ledger,
  read-only; reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002 —
  same gate as oc_voltilt/oc_downshare/oc_crashgate; if the gate fails: STOP).
- Eval outcome per fill: w (B1 size 1/(1+n_fill)) x y10 (D0 net at TP 1.0sg, fees/funding inside).
  Skip = weight 0 for fills whose (coin_ix, rung_ix) cell is in the anchor year's skip set
  (coin_ix per MAJORS order BTC/ETH/SOL/BNB/XRP = 0..4; rung_ix 0..4 per RUNGS order).
- DISCLOSED LEDGER MISMATCH (pre-registered): quality stats come from the oc_kpi engine-fill ledger
  (has exact exit kinds) while eval sums come from the k2placebo D0+B1 ledger (same D0 rung family,
  same majors/depths/grids/costs, no exit-kind column stored). Cell aggregates are robust to the
  small ledger differences (n 21389 paired vs 22312; filter differences); the mismatch is disclosed
  and the direction of any bias is conservative (stats noise can only dilute a real cell effect).

## Part 1 — replica + placebo gate (CPU-only, no engine yet; BINDING)

- Per year y in 0..4 (anchors 2021..2025-09-24; year y = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), filt_F1(y), filt_F2(y) = 4-phase means of w*y over ledger fills in year y with skip applied
  (same `phase_mean_sums` as k2placebo/voltilt/downshare). dSum5y(v) = sum_y filt_v(y) - sum_y base(y)
  (4-phase-mean w*y units). sum_half(v) = #{y: filt_v(y) >= base(y) - 1e-12}.
- Gate (IDEAS5 header, same as oc_downshare): sum-half (filt >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). BOTH legs required.
  DISCLOSED LIMITATION (pre-registered, same as oc_downshare/oc_crashgate): the k2placebo ledger
  carries no exit-date/daily path, so the replica DD-half (DD not worse by > 1 pp) cannot be scored
  at the replica stage; the binding DD check is the Part 2 4-phase engine (yearly DD + full-path
  DD <= 20). Timing/cell percentiles below are supporting evidence, not binding.
  Engine runs ONLY for variants passing sum-half + dSum5y. If neither passes, STOP with no engine
  (negative result, valid per IDEAS5 — the oc_crashgate path).
- Supporting placebo per variant (fill-level, 1000 perms; CPU numpy; preserves the actual skipped-fill
  count per year, tests cell selection vs random skipping of the same size):
  (i) uniform: random k_y fills skipped uniformly (seed 20261007+y);
  (ii) block: fills ordered by (sym, shift, bar_time), chunked into consecutive blocks of 42 fills per
  (sym, shift), blocks permuted within (sym, shift, year) (seed 20261008+y), first k_y fills skipped.
  Percentile = 100*(1+#{perm_sum >= actual_sum})/1001 on RAW yearly sums (exposure loss is part of the
  effect; no realised-mean normalisation); significant iff >= 95. Reported per year + pooled 5y.
  Rationale for fill-level (not bar-level) perms, pre-registered: the skip is cell-static per anchor
  year, not bar-varying, so permuting bar mults (downshare method) does not fit; permuting which fills
  are skipped at fixed count is the exact finite-sample null for a skip rule (shape-B spirit).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of `oc_downshare/run_engine.py` (= oc_chronos/run_engine.py = v414 pipe v321,
  kd=1.7 corr-aware inv sizes, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0; limit
  fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first in shared 1m bar;
  skip applied as a pre-placement veto: rungs whose (coin, depth) cell is skipped for the anchor year
  are never placed (bot-executable: static per-year blocklist, no intrabar read)).
- Rows run through the engine (ONLY): REF (= G2 unchanged) first + each gate-passing variant (F1/F2).
  No exposure-matched control (IDEAS5 asks it only for idea #4, not #9).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce v421 G2 years
  0..3 R/DD to the digit — dev [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] — else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4 robust pick only (every Y4 number
  labelled scored-once; REF Y4 must reproduce v421 G2 Y4 (4.648/12.90) to the digit; 5y 5.410,
  full-path DD 16.82). No re-runs after outcomes; any change becomes a disclosed extra row.
  Via heavy_slot, one job at a time; resume-safe caches tmp/runs_dev.pkl / tmp/runs_last.pkl.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4
  geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via `v388.mix`
  equal-1/4 mix from 2021-09-24; pooled book/rung/all win rates + fills/year (same collection as
  oc_downshare/oc_voltilt). Robust pick on dev4 ONLY among REF + engine-run variants: DD <= 20, no
  losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return, ties ->
  higher mean.

## Leakage / checks (stated in REPORT)

- Feature timing (T from fill_t minus shift-grid f; trailing windows use T/exit_t < A - 7d;
  truncation-tested in tests/test_oc_rungquality.py), label windows (no labels fit anywhere; replica
  exits mechanical), fit windows (quantiles p80/p20 computed inside W(A) only — strictly pre-anchor;
  no test-year statistic feeds any choice), fill timing (replica live 16..238 strict trade-through +
  stop-first inherited; engine win_start=5 + trade-through + stop-first if reached). No statistic from
  any test year feeds any choice. Gate costs inside replica outcomes and (if run) the engine.
- Coverage: 2021 empty-trailing no-skip disclosed above; 2022-2025 full windows; nothing imputed.

## Compute plan (all Part 1 CPU-light; Part 2 only if gated)

- `quality.py`: `fill_minute` + `pair_shift` copies (labelled) + `trailing_stats` + `skip_sets`
  pure helpers (unit-tested) + `build_stats` (oc_kpi events -> `tmp/quality_stats.json`).
- `compute_replica_gate.py`: CPU-only filtered replica sums + dSum5y + sum-half + 1000-perm
  uniform/block fill-level placebos per variant -> `tmp/replica_rungquality.json`.
- `run_engine.py` + `analyze.py`: ONLY if a variant passes the gate (same shape as
  oc_downshare/run_engine.py + analyze.py; REF reproduction gate first).
- Deliverables: PLAN.md (this file), quality.py, compute_replica_gate.py,
  (run_engine.py + analyze.py only if gated), tmp/quality_stats.json,
  tmp/replica_rungquality.json, results.json, REPORT.md,
  tests/test_oc_rungquality.py (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_rungquality.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays and
  the change is a disclosed extra row.)
