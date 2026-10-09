# oc_b7taper — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7taper.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Implements idea #1 of `docs/opencode/IDEAS7_20261008.md` EXACTLY as written
(rule, the two pre-registered variants and frozen constants, data, leakage notes).
Write ONLY `research/tournament/oc_b7taper/` + `tests/test_oc_b7taper.py`.
Scratch only under `research/tournament/oc_b7taper/tmp/` (never the system temp
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
(gain -0.069, boosted stops +1.5pp), the same leg that breaks every tilt.
IDEAS7 #1 mech (rank 1, prior 18%): the bounce (+4-10% in 24-48h) is
front-loaded; days 4-7 keep crash-leg exposure for decayed edge. Rule: taper the
boost so late-window sizing pays less.

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
- V1 = STEP-taper (assignment V1): mult 1.6 on days 0-2 / 1.3 on days 3-5 /
  1.0 on days 6-7 after a cascade bar (frozen day-bin reading below).
- V2 = EXP-taper (assignment V2): mult 1 + 0.5 * 2^(-d/3) with d = days since
  the latest cascade bar (frozen continuous reading below), 1.0 outside the 7d
  window.
- Book untouched (dip-only sizing overlay; presample replica has no book leg;
  engine stage, if gated, keeps the book leg byte-identical to G2).
- No other variant, no ensemble, no threshold/window tuning, no refit.

## Cascade trigger + taper window (frozen, causal, VERBATIM trigger arithmetic, no new data)

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
- TAPER WINDOW (market-wide per shift, frozen): per shift, let tc[0..K) be the
  sorted union of triggers over available majors (same shift). For a dip
  decision at holding-bar open T on shift s, let tc_last = the latest union
  trigger with tc_last < T (strictly prior; searchsorted left-1). If none, or
  T - tc_last > 7 days (strictly above 7*86400s in ns), mult = 1.0
  (unboosted). Otherwise d_days = (T - tc_last) / 1 day as a float (>= 0), and:
  * V1 step: d_int = floor(d_days); mult = 1.6 if d_int in {0,1,2}, 1.3 if
    d_int in {3,4,5}, 1.0 if d_int in {6,7} (the d_int = 7 edge is T - tc == 7d
    exactly, kept in-window at 1.0 per the 0 < T-tc <= 7d convention). Frozen
    reading of "1.6 d0-2 / 1.3 d3-5 / 1.0 d6-7" (disclosed; the alternative
    3d/3d/1d continuous-bound reading coincides with this on the 4h grid up to
    sub-day edges and is NOT used).
  * V2 exp: mult = 1.0 + 0.5 * 2^(-d_days/3) (d_days float; at d->0+ ~1.5, at
    d = 3 exactly 1.25, at d = 7 ~1.099). Outside the 7d window mult = 1.0.
  Since the taper f is non-increasing in d_days, using the latest trigger is
  identical to max-over-triggers f(T-tc) (re-fires refresh the taper;
  disclosed — this is NOT first-cascade-only; stacking enters only via the
  refresh, never additively).
- BOOSTED FLAG (frozen, for reporting + stop split only): boosted_V = mult_V >
  1.0 + 1e-12 (V1 day 6-7 bars at exactly 1.0 count as unboosted; V2 every
  in-window bar counts as boosted). Same boosted(T, s) for all coins (sleeve
  budget is global). On the 4h grid T in (tc, tc+7d].
- MULT: as above, else 1.0. Missing trigger history (T before first computable
  bar) -> 1.0 (never boosted; inert — disclosed with counts).
- Outputs: `boost_mult_presample_taper.parquet` (shift, T, mult_V1, mult_V2,
  boosted_V1, boosted_V2; T range = union of pre-sample shift grids
  2017-08-17..2020-09-30) and `boost_mult_4shift_taper.parquet` (same columns;
  T range = union of 2021-2026 shift grids 2020-08-01..2026-09-23 20:00+shift).
- Unit-tested: hand-checked synthetic trigger/sigma/taper arithmetic +
  causality/truncation test (recompute from bars truncated at a cut date ->
  identical on kept prefix).
- If the data named does not cover a year: disclose and skip that year for that
  variant (never impute). None expected (closes cover all years; early bars have
  NaN SIG and never fire — counted, not imputed).

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), window length 7d, V1 levels 1.6/1.3/1.0 with
day bins {0,1,2}/{3,4,5}/{6,7}, V2 1+0.5*2^(-d/3) with half-life 3d, seeds
(20261007+y / 20261008+y), BLOCK 42 are all frozen ex-ante round numbers /
inherited conventions (levels/bins/decay from the assignment, never scanned).
No harness join, no quantiles, no embargo beyond strict causality (trigger at
tc uses only closes with close_time <= tc; taper uses only triggers with close
< T). No statistic from any test year feeds any choice. Pre-sample years were
never used for any fit anywhere in this program (the rule has no fits at all).

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
  (ffill, causal); missing -> 1.0 (counted and disclosed). Same join for V1,
  V2 and the B7 reference (B7 mults from the frozen cboostpre parquet).
- Per pre-sample year y (Y2017/Y2018/Y2019/Y2020p; 4-phase means, same
  `phase_mean_sums` with n_years=4): base(y), boosted_V(y), realised_mean_V(y)
  (mean mult over fills in y), norm_V(y) = boosted_V(y)/realised_mean_V(y),
  gain_vs_base_V(y) = norm_V(y) - base(y), gain_vs_B7_V(y) = norm_V(y) -
  norm_B7(y) (norm_B7 from the same-ledger B7 join). "Helps vs base" in a year
  iff gain_vs_base > 0; "beats B7" in a year iff gain_vs_B7 > 0. Report n fills
  + boosted fill share + realised mean too. The COVID leg Y2020p is reported
  separately in its own row (it is the stress case: B7 gain -0.069 there).
- Timing placebo per year (primary, inherited verbatim from oc_cboostpre):
  bar universe per (year y, shift s) = time-bars (s, T) on that shift's
  pre-sample grid with T in the year's [S_y, E_y) interval; mult series per
  (y, s) permuted uniformly WITHIN (y, s) (1000 perms, seed 20261007+y with
  y = 0..3; preserves per-shift mult marginals and cross-sym sharing); fills
  map to their (y, s) time-bar. Percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95; perm norms use the ACTUAL realised-mean denominator.
  Block placebo per year: 42-bar chronological blocks per (y, s), permuted
  within (y, s) (seed 20261008+y). Same normalisation/percentile/significance.
  (For continuous V2 mults the same null applies: permutation of the realised
  mult values within (year, shift).)
- Boosted-fill stop rate (no new 1m; reuse read-only `stop_kinds.npz` kinds in
  ledger order): "hit the stop" = kind in {stop, backstop} (verbatim mu=1.0
  branch, codes backstop=0/stop=2, unknown=-1); base rate = stop-hit share over
  known-kind fills in the year; boosted rate = stop-hit share over boosted
  fills in the year (boosted = mult > 1+1e-12, per variant V1/V2, plus B7
  reference row); report delta (boosted - base) per year + pooled. Rates over
  known kinds only; unknown count disclosed (15 inherited).
- PRIMARY BEATER DEFINITION (frozen; the only gate to the engine): variant V
  beats plain B7 on the clean pre-sample years iff
  sum_{4y} norm_V(y) > sum_{4y} norm_B7(y) (strictly; normalised sums, like for
  like on the same 9731 fills). Supporting rows (helps-count vs base,
  timing-significant count, COVID-leg gain_vs_B7, pooled stop delta) are
  reported but do NOT change eligibility. If neither variant beats B7, STOP with
  no engine (negative result, valid).

## SECONDARY — 2021-2026 replica gate (contaminated, info only) + conditional engine

- Secondary replica (CPU-only): same join/method on the k2placebo ledger
  (5 years 2021-2026, anchors 2021-09-24..2025-09-24) for V1/V2 with the B7
  reference from the frozen cascadeboost parquet; per-year base/boosted/norm/
  gain_vs_base/gain_vs_B7 + 1000-perm timing/block placebos (seeds
  20261007+y / 20261008+y, y = 0..4; null = time-bar permutation WITHIN
  (year, shift)). Report dSum5y vs base and vs B7 + sum-half counts, plus the
  assignment's replica gate rows (dSum5y >= +0.273, timing >= 95) labelled
  CONTAMINATED/INFO-ONLY. "Without losing the 2021-2024 gains" is judged here
  as: dev4 (2021-2024) replica sum_V vs sum_B7 reported side by side (plus
  engine below if run).
- Conditional 4-phase engine (ONLY for variants beating B7 on the PRIMARY
  pre-sample test, via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp
  log): mechanism = exact copy of oc_cascadeboost/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs maker 0.0002/taker 0.00055,
  longs 0.0001/8h, trade-through, minute-5 ban, stop-first). Rows: REF + B7 +
  each eligible V variant (dev stage [2021-09-24, 2025-09-24); REF must
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
  excludes the tested bar; taper uses only triggers with close < T;
  truncation-tested in tests/test_oc_b7taper.py), label windows (no labels fit
  anywhere), fit windows (no fits; frozen threshold/windows/levels/decay/seeds,
  no statistic from any test year feeds any choice), fill timing (replica live
  16..238 strict trade-through + stop-first inherited; engine win_start=5 +
  trade-through + stop-first if run; perms reassign mults within (year, shift)
  only, seeds above). Gate costs inside the reused replica outcomes / engine.
  Coverage: disclose any skipped year / missing-mult count / unknown-kind count
  (none expected beyond the inherited 15 unknowns). Spot-vs-perp caveat on every
  pre-sample number (SPOT fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `taper_rule.py`: pure helpers (`close_returns`, `trailing_sigma`,
  `triggers_of`, `taper_mult` (V1 step / V2 exp from d_days), `mults_on_grid`)
  — no data access; unit-tested. (Trigger arithmetic VERBATIM oc_cascadedelay
  `delay_rule.py` / oc_cascadeboost `boost_rule.py` / oc_cboostpre
  `cboostpre_rule.py` with WINDOW = 540, MIN_PERIODS = 120, THRESH = 4.0;
  window 7d; V1_STEP = (1.6, 1.3, 1.0), V1_BINS = ({0,1,2},{3,4,5},{6,7}),
  V2 = 1+0.5*2^(-d/3).)
- `build_taper_presample.py`: CPU-only pre-sample 4h closes ->
  `boost_mult_presample_taper.parquet` + trigger counts per (year, shift) +
  boosted shares (fast; prints progress every 10 min).
- `compute_taper_presample.py`: CPU-only join to the reused ledger +
  per-year sums/gains vs base AND vs B7 + 1000-perm timing/block placebos
  (time-bar within-(year,shift)) for V1 + V2 -> `tmp/taper_presample.json`
  (heartbeat every 600 s); stop split from read-only `stop_kinds.npz` ->
  same JSON (no 1m work).
- `build_taper_4shift.py` + `compute_replica_taper.py`: secondary 2021-2026
  grids + replica/placebo (same shapes as above, 5 years) ->
  `boost_mult_4shift_taper.parquet` + `tmp/replica_taper.json` (CPU-only).
- `run_engine_taper.py` + `analyze_taper.py`: ONLY for PRIMARY-beating
  variants (same shape as oc_cascadeboost/run_engine.py + analyze.py, mult
  lookup = frozen taper parquet, market-wide per (shift, T); REF + B7
  reproduction gates first; worst 1m-marked DD episode per row in analyze).
- Deliverables: PLAN.md (this file), taper_rule.py,
  build_taper_presample.py, compute_taper_presample.py,
  build_taper_4shift.py, compute_replica_taper.py,
  (run_engine_taper.py + analyze_taper.py only if gated),
  boost_mult_*_taper.parquet, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_b7taper.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7taper.py -q`).

## Post-hoc log

- 2026-10-08 (before any engine outcome; no result row changed): added the
  shared `ANCH5` anchor tuple to `taper_rule.py` (same convention as
  oc_cascadeboost `boost_rule.py`) so `run_engine_taper.py` can index engine
  years; taper arithmetic untouched, all replica outputs already written are
  unaffected (rule module pure functions unchanged).
