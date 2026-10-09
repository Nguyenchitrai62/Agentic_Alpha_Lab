# oc_cascadedelay — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_cascadedelay.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS5_20261008.md idea #10 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_cascadedelay/` + `tests/test_oc_cascadedelay.py`. Scratch only under
`research/tournament/oc_cascadedelay/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one engine job at a
time, load one coin at a time, float32). Long jobs: nohup + log file under tmp/, poll the log; never
inspect /proc or folders outside the workspace. Heartbeat print every 600 s in long jobs.
Progress print every 10 minutes (this study is CPU-light; prints at each stage).

## Why (IDEAS5_20261008.md idea #10, rank 10 — quoted, not refit)

Nguyen 2025 (Hyperliquid L2 after Oct-2025: spreads back to 1.06-1.19x in ~23d, but depth stuck at
66-79 % and still contracting week 3) = two-regime recovery: makers quote but don't commit size.
The dip edge IS liquidity provision — stand down until depth rebuilds. Needs no liq history
(sidesteps the 2027 data wall). Expected effect (frozen): ~0 return (+-0.04), DD -0.0-0.4 pp
(tail insurance). Prior 8 % for DD, 3 % for return. Round-trip ~4-8 bps bounds every effect below.
NEAR-DUPLICATE NOTE (inherited): `oc_cooldown` (24h post-STOP skip, essentially 2022-FTX-only;
REPORT.md read: PROMISING 4/5 DD + 5/5 sums but DD cut is the 2022 FTX cascade plus dust, removed
win 78 % > kept 69 %) triggers on STOPS over HOURS — this triggers on RANGE over DAYS with
budget-halving; kept per IDEAS5. CLOSED rows read first: `oc_cooldown` (PLAN/REPORT: per-coin
stop-triggered skip, (s,s+24h] timing convention copied), `oc_crashgate` (replica+gate template
for a dip rule that FAILED the gate with no engine run — the valid negative-outcome path followed
here), `oc_k2placebo`/`oc_placebo_dip` (D0+B1 replica ledger reused read-only; pooled placebo p95
+0.273 gate), `oc_voltilt`/`oc_downshare` (replica+placebo code shape copied).

## Variants (exactly two + reference, thresholds frozen ex-ante, never fit)

- REF = G2 unchanged (dip mult 1), reproduction row (v421 R2B1D17BFG2) — engine stage only.
- V1 = dip budget 0.26 -> 0.13 (rung mult x0.5) while in post-cascade cooldown, N = 7 days.
- V2 = same with N = 3 days.
- N values frozen ex-ante (7/3 from the assignment, never scanned); x0.5 frozen (0.13/0.26).
- Book untouched (both variants). No other variant, no ensemble, no threshold tuning.

## Cascade trigger + cooldown (frozen, causal, existing 4h closes only — no new data)

- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open;
  bar close time = T + 4h). Only the `close` column is used (IDEAS5: "cascade proxy from
  closes only", "budget path reproducible from closes only").
- READING OF "range > 4sg" (frozen, disclosed): "range" = absolute close-to-close log move
  |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED alternative: (H-L)-based range —
  highs/lows are not closes, contradicting the assignment's twice-stated "from closes only".
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6 bars/day),
  min_periods 120 (else NaN). SIG[i] uses only bars with close_time <= T[i] (r[i-1] resolves
  at close_time[i-1] = T[i]); the tested return r[i] resolves at close_time[i] = T[i]+4h and
  is NEVER in its own sigma window — causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 * SIG[i]
  (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h (known at tc).
  NaN SIG or non-finite closes -> never fires (conservative; counted and disclosed).
- COOLDOWN (market-wide per shift, frozen): a dip decision at holding-bar open T on shift s
  is COOLED iff there EXISTS a trigger (ANY of the 5 majors, same shift s) with
  0 < T - tc <= N days (strictly after the trigger close, up to and including +N days).
  Same cooled(T, s) for all 5 coins (the sleeve budget 0.26 is global; Nguyen depth
  withdrawal is market-wide). REJECTED alternative: per-coin triggers — disclosed.
  On the 4h grid this is T in (tc, tc+Nd] = k = 1..42 bars (V1 7d) / 1..18 bars (V2 3d).
- MULT: cooled -> 0.5, else 1.0. Missing trigger history (T before first computable bar) ->
  1.0 (never cooled; inert — history from 2020-08-01 gives full 540-return windows for all
  of 2021-09-24.., disclosed with counts).
- Output: `delay_mult_4shift.parquet` (shift, T, cooled_V1, cooled_V2, mult_V1, mult_V2;
  T range = union of shift grids 2020-08-01..2026-09-23 20:00+shift).
- Unit-tested: hand-checked synthetic trigger/sigma/cooldown arithmetic + causality/
  truncation test (recompute from bars truncated at a cut date -> identical on kept prefix).
- If the data named does not cover an anchor year: disclose and skip that year for that
  variant (never impute). None expected (4h closes from 2020-08-01 cover all anchors with
  full 540-return windows; missing -> mult 1, counted and disclosed).

## No fits (nothing estimated)

There are no fitted parameters here: trigger threshold 4.0, windows (540/120/min),
halving 0.5, N = 7/3 are all frozen ex-ante round numbers from the assignment text.
No harness join, no quantiles, no embargo beyond strict causality (trigger at tc uses only
closes with close_time <= tc). No statistic from any test year feeds any choice.

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (closes for triggers).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica ledger
  read-only; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json`
  row R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82) — engine stage only.
- `research/tournament/oc_chronos/run_engine.py` (mechanism copied verbatim; only the dip
  tilt lookup changes to the frozen delay mult) — engine stage only.

## Part 1 — replica + placebo gate (CPU-only, no engine yet; BINDING)

- For V1, V2: per fill in the reused ledger, key (shift, T=bar open): mult = 0.5 if
  cooled_V(T, shift) else 1.0 (same for all syms at that (shift, T); exact match on the
  shift grid, fallback to latest grid time <= T (ffill, causal); missing -> 1, counted).
- Per year y (4-phase means from ledger w*y, same phase_mean_sums as k2placebo/voltilt/
  crashgate/downshare): base(y), delay(y), realised_mean(y), norm(y) = delay(y)/
  realised_mean(y). dSum5y = sum_y delay(y) - sum_y base(y) (4-phase-mean sums, w*y units).
- Timing placebo per year (supporting, pre-registered adaptation for a MARKET-WIDE rule):
  bar universe per (year y, shift s) = time-bars (s, T) on that shift's grid with
  T in [A_y+s, min(A_y+s+365d, live1)); mult series per (y, s) permuted uniformly
  WITHIN (y, s) (1000 perms, seed 20261007+y; preserves per-shift cooled counts and the
  cross-sym sharing); fills map to their (y, s) time-bar. Block placebo: 42-bar
  chronological blocks per (y, s), permuted within (y, s) (seed 20261008+y).
  Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95; perm norms use the
  ACTUAL realised-mean denominator. Rationale for the adaptation (disclosed): permuting
  over (sym,shift,T) triples like the tilt studies would break the pre-registered
  market-wide sharing (all syms share one mult per time-bar); time-bar permutation within
  (year, shift) is the correct null for a time-based rule.
- Gate (IDEAS5 header): sum-half (delay sum >= base in >= 4/5 years) PLUS dSum5y >= +0.273
  (pooled placebo p95, oc_placebo_dip). DISCLOSED LIMITATION (pre-registered, same as
  oc_crashgate/oc_downshare): the k2placebo ledger carries no exit-date/daily path, so the
  replica DD-half cannot be scored at the replica stage; the binding DD check is the 4-phase
  engine (yearly DD + full-path DD <= 20). Timing percentiles are supporting evidence, not
  binding. Engine runs ONLY for variants passing the sum-half + dSum5y gate. If neither
  passes, STOP with no engine (negative result, valid per IDEAS5).
- No statistic from any test year feeds any choice (triggers use closes <= tc only;
  thresholds/windows frozen; no fits).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware inv
  sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first
  in shared 1m bar — engine handles). Dip leg: rung size x mult_V(T, shift) (0.5 in
  cooldown else 1.0); book leg byte-identical to G2.
- Rows run through the engine (ONLY): REF + each gate-passing variant (V1 and/or V2).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit, else STOP). Stage last runs [DEV0, Y1=2026-09-23)
  ONCE for REF + the dev4 robust pick only (every Y4 number labelled scored-once; REF Y4
  must reproduce v421 G2 Y4 to the digit). No re-runs after outcomes; any change becomes
  a disclosed extra row. Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`;
  dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24; pooled book/rung/all win rates + fills/year +
  sized mean multiplier + cooled share of fills and of (shift, T) time-bars (same collection
  as oc_voltilt/oc_crashgate). Robust pick on dev4 ONLY among REF + engine-run variants:
  DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year
  monthly return, ties -> higher mean.

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window excludes the
  tested bar; cooldown strictly after tc; truncation-tested in tests/test_oc_cascadedelay.py),
  label windows (no labels fit anywhere in this study), fit windows (no fits; frozen
  threshold/windows/N/half, no statistic from any test year feeds any choice), fill timing
  (replica live 16..238 strict trade-through + stop-first inherited; engine win_start=5 +
  trade-through + stop-first if reached). Gate costs inside replica outcomes / engine.
  Coverage: disclose any skipped anchor year (none expected; missing trigger history ->
  mult 1, counted).

## Compute plan (heavy_slot only for engine, resume-safe)

- `delay_rule.py`: pure helpers (`close_returns`, `trailing_sigma`, `triggers_of`,
  `cooled_at`, `anchor_of`) — no data access; unit-tested.
- `build_delay.py`: CPU-only 4h closes -> `delay_mult_4shift.parquet` + trigger counts
  per (year, shift) (fast, < 5 min; prints progress).
- `compute_replica_gate.py`: CPU-only delayed replica sums + dSum5y + 1000-perm
  timing/block placebo (time-bar within-(year,shift) permutation) for V1 + V2 on the
  reused ledger -> `tmp/replica_cascadedelay.json` (heartbeat every 600 s).
- `run_engine.py` + `analyze.py`: ONLY if a variant passes the gate (same shape as
  oc_voltilt/run_engine.py + analyze.py; REF reproduction gate first).
- Deliverables: PLAN.md (this file), delay_rule.py, build_delay.py,
  compute_replica_gate.py, (run_engine.py + analyze.py only if gated),
  delay_mult_4shift.parquet, results.json, REPORT.md, tests/test_oc_cascadedelay.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_cascadedelay.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
