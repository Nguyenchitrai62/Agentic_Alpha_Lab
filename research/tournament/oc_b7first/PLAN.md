# oc_b7first — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7first.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Implements idea #3 of `docs/opencode/IDEAS7_20261008.md` EXACTLY as written
(rule, the two pre-registered variants and frozen constants, data, leakage notes).
Write ONLY `research/tournament/oc_b7first/` + `tests/test_oc_b7first.py`.
Scratch only under `research/tournament/oc_b7first/tmp/` (never the system temp
folder; never inspect /proc or folders outside the workspace). GIT IS READ-ONLY:
never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Progress print every 10 minutes (heartbeat every 600 s in long loops).
Engine / 1m work (if gated) via `scripts/heavy_slot.py` (RAM tight: one job at a
time, one coin at a time, float32). Long jobs: nohup + log under tmp/.

## Why and the contamination protocol

Base = B7 of `research/tournament/oc_cascadeboost` (dip budget x1.5 for 7 days
after a cascade bar, oc_cascadedelay definition: |close-to-close log move| >
4 x trailing-90d sigma, market-wide per shift). oc_cascadeboost B7 is the dev4
robust pick (dev4 mean 6.74 vs G2 5.60) but CONTAMINATED (idea formed after the
delay replica covered all five years incl. the post-release year); pre-sample
(`oc_cboostpre`) shows B7 helps 3/4 unseen years but fails the COVID leg Y2020p
(gain -0.07, boosted stops +1.5pp), the same leg that breaks every tilt.
IDEAS7 #3 mech (rank 3, prior 14%): first cascade = flush + bounce setup;
re-fires inside the window = crash leg (COVID pattern: repeated cascades lever
up). Rule: boost fires only for the FIRST cascade (no cascade in the prior N
days); re-fires inside the window neither stack nor extend.

CONTAMINATION PROTOCOL (from the assignment, repeated here BEFORE any outcome):
anything derived from the cascade results is contaminated for 2021-2026. The
PRIMARY, clean test is the pre-sample replica 2017 .. 2020-09-23
(`oc_presampletilt` + `oc_cboostpre` machinery: cascade flags on pre-sample 4h
closes, D0+B1 ledger): per-year normalised gain vs B7 AND vs no boost, timing
placebo pct, boosted-fill stop rate, and the COVID leg (2020p) separately.
SECONDARY: the 2021-2026 replica gate (contaminated, info only) and, for
variants that beat B7 on the pre-sample test, the 4-phase engine vs REF and B7
(dev4 robust pick, 5y, full-path DD; post-release year labelled diagnostic).
No selection is made on 2021-2026 or on the post-release year in this study;
the pre-sample beater definition below is the only gate to the engine.

## Variants (exactly two + two references; nothing else)

- REF = base dip replica unchanged (mult 1), reproduction row only.
- B7 = plain dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window
  else 1.0), VERBATIM oc_cascadeboost/oc_cboostpre (reference for head-to-head).
- F14 = FIRST-cascade-only B7 with N = 14 (V1): boost window 7d at 1.5 fires only
  from a trigger with NO cascade in the prior 14 days; re-fires inside the
  window neither stack nor extend.
- F7 = FIRST-cascade-only B7 with N = 7 (V2): same with prior-7-day exclusion.
- Book untouched (dip-only sizing overlay; presample replica has no book leg;
  engine stage, if gated, keeps the book leg byte-identical to G2).
- No other variant, no ensemble, no threshold/window tuning, no refit.

## Cascade trigger + first-cascade filter + boost window (frozen, causal, VERBATIM arithmetic, no new data)

- Source pre-sample (read-only): `research/tournament/oc_presampletilt/bars_4h_presample.parquet`
  (4 syms BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT x shifts 0..3, ORIGIN 2020-01-01 + s h
  grid; per (sym, shift) series sorted by T = bar open). Only the `close` column
  is used. SOL absent pre-sample (union over available majors only — disclosed).
- Source 2021-2026 secondary (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3). Only `close` is used.
- "range > 4sg" reading (frozen, inherited): "range" = absolute close-to-close
  log move |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED
  alternative: (H-L)-based range.
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6
  bars/day), min_periods 120 (else NaN). SIG[i] uses only bars with close_time
  <= T[i]; the tested return r[i] resolves at close_time[i] = T[i]+4h and is
  NEVER in its own sigma window — causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 *
  SIG[i] (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h
  (known at tc). NaN SIG or non-finite closes -> never fires (conservative;
  counted and disclosed).
- FIRST-CASCADE FILTER (frozen, this study's only new logic): per shift, let
  tc[0..K) be the sorted union of triggers over available majors (same shift).
  A trigger tc[j] QUALIFIES iff there is NO other trigger tc[k] with
  0 < tc[j] - tc[k] <= N days (strictly prior within N days; prior = ANY cascade,
  qualifying or not — frozen reading of "NO cascade in prior N days"). N = 14
  for F14, N = 7 for F7. Non-qualifying re-fires are dropped entirely: they
  neither start a window nor extend/stack an open one (frozen reading of
  "re-fires inside window neither stack nor extend"). With N >= 7 = window
  length, qualifying triggers are > N days apart so 7d windows never overlap
  (up to the inclusive boundary); no stacking arithmetic is needed.
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at holding-bar
  open T on shift s is BOOSTED_F iff there EXISTS a qualifying trigger (same
  shift s) with 0 < T - tc <= 7 days (strictly after the trigger close, up to
  and including +7 days). Same boosted(T, s) for all coins (sleeve budget is
  global). On the 4h grid T in (tc, tc+7d].
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first
  computable bar) -> 1.0 (never boosted; inert — disclosed with counts).
- Outputs: `boost_mult_presample_first.parquet` (shift, T, boosted_F14,
  boosted_F7, mult_F14, mult_F7; T range = union of pre-sample shift grids
  2017-08-17..2020-09-30) and `boost_mult_4shift_first.parquet` (same columns;
  T range = union of 2021-2026 shift grids 2020-08-01..2026-09-23 20:00+shift).
  F mults are subsets of B7 (dropping re-fires can only un-boost bars).
- Unit-tested: hand-checked synthetic trigger/sigma/first-filter/boost
  arithmetic + causality/truncation test (recompute from bars truncated at a
  cut date -> identical on kept prefix).
- If the data named does not cover a year: disclose and skip that year for that
  variant (never impute). None expected (closes cover all years; early bars have
  NaN SIG and never fire — counted, not imputed).

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), boost 1.5, boost length 7d, N = 14/7, seeds
(20261007+y / 20261008+y), BLOCK 42 are all frozen ex-ante round numbers /
inherited conventions (N from the assignment, never scanned). No harness join,
no quantiles, no embargo beyond strict causality (trigger at tc uses only
closes with close_time <= tc; filter uses only triggers with close <= tc).
No statistic from any test year feeds any choice. Pre-sample years were never
used for any fit anywhere in this program (the rule has no fits at all).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (triggers).
- `research/tournament/oc_presampletilt/tmp/ledger_presample.npz` +
  `tmp/bt_presample.npy` (D0+B1 replica; reproduction gate n == 9731, per-leg
  909/2986/3115/2721, base 4-phase-mean sums == (2.313362, 2.678870, 0.577643,
  0.297538) +- 1e-6 — variant-independent).
- `research/tournament/oc_cboostpre/boost_mult_presample.parquet` (B7 reference
  mults on the same grid; read-only head-to-head) + `tmp/stop_kinds.npz`
  (per-fill exit kinds in ledger order; read-only stop split — NO new 1m work).
- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (secondary).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `tmp/bt_all.npy`
  (secondary D0+B1 ledger; reproduction gate n == 22312, base sum5y ==
  7.718304 +- 0.002) + `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet`
  (secondary B7 reference; read-only).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline — engine stage only, if gated)
  + `research/tournament/oc_chronos/run_engine.py` mechanism (copied verbatim;
  only the dip mult lookup changes — engine stage only, if gated).

## PRIMARY — pre-sample replica + placebo + stop split (clean; CPU-only, no engine)

- Per fill join (phase=shift, T=bar open; coin mapping BTC/ETH/BNB/XRP = 0/1/2/3
  inherited): exact match on the shift grid, fallback to latest grid time <= T
  (ffill, causal); missing -> 1.0 (counted and disclosed). Same join for F14,
  F7 and the B7 reference (B7 mults from the frozen cboostpre parquet).
- Per pre-sample year y (Y2017/Y2018/Y2019/Y2020p; 4-phase means, same
  `phase_mean_sums` with n_years=4): base(y), boosted_F(y), realised_mean_F(y)
  (mean mult over fills in y), norm_F(y) = boosted_F(y)/realised_mean_F(y),
  gain_vs_base_F(y) = norm_F(y) - base(y), gain_vs_B7_F(y) = norm_F(y) -
  norm_B7(y) (norm_B7 from the same-ledger B7 join). "Helps vs base" in a year
  iff gain_vs_base > 0; "beats B7" in a year iff gain_vs_B7 > 0. Report n fills
  + boosted fill share too. The COVID leg Y2020p is reported separately in its
  own row (it is the stress case: B7 gain -0.069 there).
- Timing placebo per year (primary, inherited verbatim from oc_cboostpre):
  bar universe per (year y, shift s) = time-bars (s, T) on that shift's
  pre-sample grid with T in the year's [S_y, E_y) interval; mult series per
  (y, s) permuted uniformly WITHIN (y, s) (1000 perms, seed 20261007+y with
  y = 0..3; preserves per-shift boosted counts and cross-sym sharing); fills
  map to their (y, s) time-bar. Percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95; perm norms use the ACTUAL realised-mean denominator.
  Block placebo per year: 42-bar chronological blocks per (y, s), permuted
  within (y, s) (seed 20261008+y). Same normalisation/percentile/significance.
- Boosted-fill stop rate (no new 1m; reuse read-only `stop_kinds.npz` kinds in
  ledger order): "hit the stop" = kind in {stop, backstop} (verbatim mu=1.0
  branch); base rate = stop-hit share over known-kind fills in the year;
  boosted rate = stop-hit share over boosted fills in the year (per variant
  F14/F7, plus B7 reference row); report delta (boosted - base) per year +
  pooled. Rates over known kinds only; unknown count disclosed (15 inherited).
- PRIMARY BEATER DEFINITION (frozen; the only gate to the engine): variant F
  beats plain B7 on the clean pre-sample years iff
  sum_{4y} norm_F(y) > sum_{4y} norm_B7(y) (strictly; normalised sums, like for
  like on the same 9731 fills). Supporting rows (helps-count vs base,
  timing-significant count, COVID-leg gain_vs_B7, pooled stop delta) are
  reported but do NOT change eligibility. If neither variant beats B7, STOP with
  no engine (negative result, valid).

## SECONDARY — 2021-2026 replica gate (contaminated, info only) + conditional engine

- Secondary replica (CPU-only): same join/method on the k2placebo ledger
  (5 years 2021-2026, anchors 2021-09-24..2025-09-24) for F14/F7 with the B7
  reference from the frozen cascadeboost parquet; per-year base/boosted/norm/
  gain_vs_base/gain_vs_B7 + 1000-perm timing/block placebos (seeds
  20261007+y / 20261008+y, y = 0..4; null = time-bar permutation WITHIN
  (year, shift)). Report dSum5y vs base and vs B7 + sum-half counts. This leg
  is CONTAMINATED (idea derived from cascade results covering these years):
  info only, never a selection basis. "Without losing the 2021-2024 gains" is
  judged here as: dev4 (2021-2024) replica sum_F vs sum_B7 reported side by
  side (plus engine below if run).
- Conditional 4-phase engine (ONLY for variants beating B7 on the PRIMARY
  pre-sample test, via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp
  log): mechanism = exact copy of oc_cascadeboost/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs maker 0.0002/taker 0.00055,
  longs 0.0001/8h, trade-through, minute-5 ban, stop-first). Rows: REF + B7 +
  each eligible F variant (dev stage [2021-09-24, 2025-09-24); REF must
  reproduce v421 G2 dev years 0..3 R/DD to the digit, else STOP); last stage
  [DEV0, 2026-09-23) ONCE for REF + the dev4 robust pick only (robust pick on
  dev4 ONLY among DD <= 20 / no-losing-dev-year rows: prefer dev4 mean >= 5,
  then highest dev4 WORST-year, ties -> higher mean; post-release Y4 labelled
  scored-once DIAGNOSTIC). Metrics: per-year 4-phase reset %/mo + DD, dev4 geo
  mean, W, max yearly DD, losing count, 5y geo mean, full-path DD via v388.mix
  (max of marked/close), worst 1m-marked DD episode, win rates + fills/year +
  sized mean multiplier + boosted share. If no variant is eligible, no engine
  rows are run at all.

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window
  excludes the tested bar; first-filter uses only triggers with close <= tc;
  boost window strictly after tc; truncation-tested in
  tests/test_oc_b7first.py), label windows (no labels fit anywhere), fit
  windows (no fits; frozen threshold/windows/boost/N/seeds, no statistic from
  any test year feeds any choice), fill timing (replica live 16..238 strict
  trade-through + stop-first inherited; engine win_start=5 + trade-through +
  stop-first if run; perms reassign mults within (year, shift) only, seeds
  above). Gate costs inside the reused replica outcomes / engine. Coverage:
  disclose any skipped year / missing-mult count / unknown-kind count (none
  expected beyond the inherited 15 unknowns). Spot-vs-perp caveat on every
  pre-sample number (SPOT fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `b7first_rule.py`: pure helpers (`close_returns`, `trailing_sigma`,
  `triggers_of`, `qualifying_triggers`, `boosted_mask`, `anchor_of`) — no data
  access; unit-tested. (Trigger arithmetic VERBATIM oc_cascadedelay
  `delay_rule.py` / oc_cascadeboost `boost_rule.py` / oc_cboostpre
  `cboostpre_rule.py` with BOOST = 1.5, BOOST_DAYS = 7, N14 = 14, N7 = 7.)
- `build_boost_presample_first.py`: CPU-only pre-sample 4h closes ->
  `boost_mult_presample_first.parquet` + trigger/qualifying counts per
  (year, shift) + boosted shares (fast; prints progress every 10 min).
- `compute_boost_presample_first.py`: CPU-only join to the reused ledger +
  per-year sums/gains vs base AND vs B7 + 1000-perm timing/block placebos
  (time-bar within-(year,shift)) for F14 + F7 -> `tmp/boost_presample_first.json`
  (heartbeat every 600 s); stop split from read-only `stop_kinds.npz` ->
  same JSON (no 1m work).
- `build_boost_4shift_first.py` + `compute_replica_gate_first.py`: secondary
  2021-2026 grids + replica/placebo (same shapes as above, 5 years) ->
  `boost_mult_4shift_first.parquet` + `tmp/replica_first.json` (CPU-only).
- `run_engine_first.py` + `analyze_first.py`: ONLY for PRIMARY-beating
  variants (same shape as oc_cascadeboost/run_engine.py + analyze.py, mult
  lookup = frozen first-cascade parquet, market-wide per (shift, T); REF + B7
  reproduction gates first; worst 1m-marked DD episode per row in analyze).
- Deliverables: PLAN.md (this file), b7first_rule.py,
  build_boost_presample_first.py, compute_boost_presample_first.py,
  build_boost_4shift_first.py, compute_replica_gate_first.py,
  (run_engine_first.py + analyze_first.py only if gated),
  boost_mult_*_first.parquet, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_b7first.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7first.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
