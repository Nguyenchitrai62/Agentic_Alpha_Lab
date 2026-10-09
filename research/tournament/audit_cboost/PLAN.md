# audit_cboost — PLAN (pre-registered BEFORE any outcome, 2026-10-08 — FROZEN)

Blind replication of the oc_cascadeboost B7 dip-budget boost on G2 (engine part; triggers rebuilt).
Reads ONLY: docs/opencode/OPENCODE_W_audit_cboost.md,
docs/opencode/OPENCODE_W_COMMON_20261007.md, AGENTS.md,
docs/opencode/OPENCODE_VF_COMMON.md,
research/tournament/oc_cascadeboost/PLAN.md + research/tournament/oc_cascadedelay/PLAN.md
(frozen specs) plus INPUT files below.
Do NOT read oc_cascadeboost REPORT.md, results.json or its scripts
(boost_rule.py, build_boost.py, compute_replica_gate.py, run_engine.py, analyze.py)
until replication.json is saved. Do NOT read oc_cascadedelay REPORT.md / results.json /
scripts either (rebuild is from the frozen PLAN spec only).
Format modelled on research/tournament/audit_c2 (its PLAN.md / COMPARISON.md / REPORT.md only).
Write ONLY research/tournament/audit_cboost/ + tests/test_audit_cboost.py.
Scratch only under research/tournament/audit_cboost/tmp/.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine / heavy 1m work via scripts/heavy_slot.py (RAM tight: one engine job at a time,
load one coin at a time where applicable; never --leader). Long jobs: nohup + log file
under tmp/, poll the log. Heartbeat print every 600 s in long jobs.
Progress print every 10 minutes.

## Contamination label (pre-registered, inherited from oc_cascadeboost PLAN.md)

B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move).
The idea was formed AFTER oc_cascadedelay's replica had covered all five years incl. the
post-release year, so every post-release-year (2025-09-24 .. 2026-09-23) number in this
audit is a LABELLED DIAGNOSTIC (not clean evidence). Selection is on dev4 ONLY
(anchors 2021-2024). New evidence must come from controls, unseen years, frictions and
prospective paper. Stated here BEFORE any outcome and repeated in replication.json /
REPORT.md / COMPARISON.md.

## Variants (ONLY these two, fixed)

- REF = G2 unchanged (dip mult 1), reproduction row (v421 R2B1D17BFG2) — engine stage only.
- B7 = dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window else 1.0).
- B3 (x1.5 for 3 days) is NOT re-run in this audit (assignment names REF + B7 only).
- Cascade bar definition and everything else EXACTLY as the frozen spec below
  (verbatim from oc_cascadedelay PLAN via oc_cascadeboost PLAN); only the multiplier
  is 1.5 (inverted 0.5). Book untouched. The G2 dip gross cap (2.0) and every other
  G2 limit still bind (enforced inside the engine; audit overlay is a linear w*mult
  like oc_cascadeboost). No other variant, no ensemble, no threshold tuning.

## Cascade trigger + boost window (frozen, causal, existing 4h closes only — no new data)

- Source (read-only): research/tournament/oc_kronoshidden/bars_4h_4shift.parquet
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open;
  bar close time = T + 4h). Only the `close` column is used.
- READING OF "range > 4sg" (frozen, disclosed, inherited): "range" = absolute
  close-to-close log move |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN).
  REJECTED alternative: (H-L)-based range — highs/lows are not closes,
  contradicting the twice-stated "from closes only".
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6 bars/day),
  min_periods 120 (else NaN). SIG[i] uses only bars with close_time <= T[i] (r[i-1]
  resolves at close_time[i-1] = T[i]); the tested return r[i] resolves at
  close_time[i] = T[i]+4h and is NEVER in its own sigma window — causal by
  construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 * SIG[i]
  (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h (known at tc).
  NaN SIG or non-finite closes -> never fires (conservative; counted and disclosed).
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at holding-bar open T
  on shift s is BOOSTED iff there EXISTS a trigger (ANY of the 5 majors, same shift s)
  with 0 < T - tc <= 7 days (strictly after the trigger close, up to and including +7d).
  Same boosted(T, s) for all 5 coins (the sleeve budget is global; post-cascade flow is
  market-wide). REJECTED alternative: per-coin triggers — disclosed (inherited).
  On the 4h grid this is T in (tc, tc+7d] = k = 1..42 bars.
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first computable
  bar) -> 1.0 (never boosted; inert — history from 2020-08-01 gives full 540-return
  windows for all of 2021-09-24.., disclosed with counts).
- Output: research/tournament/audit_cboost/boost_mult_4shift.parquet
  (shift, T, boosted_B7, mult_B7; T range = union of shift grids 2020-08-01..2026-09-23
  20:00+shift). Independent implementation (audit_cboost/boost_rule.py); byte-format
  need not match theirs, semantics must.
- Unit-tested: hand-checked synthetic trigger/sigma/boost arithmetic + causality /
  truncation test (recompute from bars truncated at a cut date -> identical on kept prefix).
- If the data named does not cover an anchor year: disclose and skip that year for that
  variant (never impute). None expected (4h closes from 2020-08-01 cover all anchors with
  full 540-return windows; missing -> mult 1, counted and disclosed).

## No fits (nothing estimated)

There are no fitted parameters here: trigger threshold 4.0, windows (540/120/min),
boost 1.5, N = 7 are all frozen ex-ante round numbers (1.5 = inverted 0.5; N from the
assignment, never scanned). No harness join, no quantiles, no embargo beyond strict
causality (trigger at tc uses only closes with close_time <= tc). No statistic from any
test year feeds any choice.

## Frozen inputs (read-only, never edited, never refit)

- research/tournament/oc_kronoshidden/bars_4h_4shift.parquet (closes for triggers).
- research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl + v421_result.json
  row R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82)
  — engine stage only.
- research/tournament/oc_chronos/run_engine.py + research/tournament/oc_kronoshidden/run_engine.py
  (mechanism templates copied verbatim; only the dip mult lookup changes to the frozen
  boost mult) — engine stage only.
- research/diagnostics/r2_decompose5/reset_metric.py (year_reset) +
  research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py
  (hourly / mix for full-path DD) for scoring only.

## Engine (fixed, 4-phase, heavy_slot)

- Mechanism = exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware inv
  sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first
  in shared 1m bar — engine handles). Dip leg: rung size x mult_B7(T, shift) (1.5 in
  boost window else 1.0, market-wide per shift, same for all 5 coins at (shift, T));
  book leg byte-identical to G2. G2 dip gross cap 2.0 and every other G2 limit bind
  (kw["sleeve_gross_cap"] = 2.0, unchanged).
- Rows run through the engine (ONLY): REF + B7.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit AND 5y/full-path 5.41/16.91/16.82 on the full
  window, else STOP). Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + B7 (every Y4
  number labelled scored-once DIAGNOSTIC — contaminated, see top; REF Y4 must reproduce
  v421 G2 Y4 to the digit). No re-runs after outcomes; any change becomes a disclosed
  extra row. Via heavy_slot, one job at a time; resume-safe caches tmp/runs_dev.pkl /
  tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Holding-bar open H = idx[i]+4h; boost lookup (shift=s, T=H): exact match on the shift
  grid, fallback to latest grid time <= T (ffill, causal); missing -> 1, counted.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via reset_metric.year_reset;
  dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD
  via v388.mix equal-1/4 mix from 2021-09-24 (max of marked/close); worst 1m-marked DD
  episode for each row (peak/trough/depth); pooled book/rung/all win rates + fills/year +
  sized mean multiplier + boosted share of fills and of (shift, T) time-bars; cap-bind
  frequency: share of (shift, T) time-bars where the sleeve gross cap binds under REF vs
  B7 (boosted vs normal windows for B7), from engine sleeve diagnostics where available,
  else counted from rung sizes pre-cap vs cap (method stated in REPORT).
- replication.json (Part A, saved BEFORE opening any oc_cascadeboost output):
  trigger counts per (year, shift), boosted (shift, T) time-bar counts + shares,
  per-year {R, DD} for REF and B7, dev4 {R,W,DD,losing}, Y4 {R,DD} (labelled diagnostic),
  5y {R,W,DD,losing}, full_path_dd, cap-bind stats, code/mapping notes, run hashes.
- Comparison (Part B, only after replication.json is saved): thresholds
  R diff > 0.10 pp, DD diff > 0.5 pp, trigger counts exact, boosted time-bar counts exact
  (tolerance: exact integer match; mult agreement 100% on sampled (shift, T) keys).
  Code audit for look-ahead: (1) feature timing per (sym, shift) (closes <= tc only,
  sigma excludes tested bar; 200-row truncation recompute must match), (2) window timing
  (0 < T-tc <= 7d strict; holding-bar key T=H), (3) fit windows (no fits; frozen only),
  (4) multiplier application point (sleeve_fill_size, holding-bar key, cap still binds).
  Each with a test. COMPARISON.md: PASS / PASS-WITH-NOTES / FAIL + 3-line Vietnamese verdict.

## Leakage checks (to state in REPORT)

- Feature timing: triggers use closes with close_time <= tc only; sigma window excludes
  the tested bar; boost window strictly after tc; truncation recompute on 200 rows.
- Label windows: no labels fit anywhere in this study.
- Fit windows: no fits; frozen threshold/windows/N/boost, no statistic from any test year
  feeds any choice.
- Fill timing: engine win_start=5 + 1m trade-through + stop-first if reached (inherited).
- Costs: gate maker 0.0002 / taker 0.00055, longs 0.0001/8h, shorts 0.
- Coverage: disclose any skipped anchor year (none expected; missing trigger history ->
  mult 1, counted).

## Compute plan (heavy_slot only for engine, resume-safe)

- boost_rule.py: pure helpers (close_returns, trailing_sigma, triggers_of,
  boosted_mask, anchor_of) — no data access; unit-tested. (Independent re-implementation
  of the frozen arithmetic; constant BOOST = 1.5, B7_DAYS = 7.)
- build_boost.py: CPU-only 4h closes -> boost_mult_4shift.parquet + trigger counts
  per (year, shift) (fast, < 5 min; prints progress).
- run_engine.py + analyze.py: REF + B7 (same shape as oc_chronos/run_engine.py +
  oc_kronoshidden/run_engine.py multilookup = frozen boost parquet, market-wide per
  (shift, T); REF reproduction gate first; worst 1m-marked DD episode per row in analyze).
- Deliverables: PLAN.md (this file), boost_rule.py, build_boost.py,
  run_engine.py + analyze.py, boost_mult_4shift.parquet, replication.json (Part A),
  COMPARISON.md (Part B, after unblind), REPORT.md, tests/test_audit_cboost.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  .venv/Scripts/python.exe -m pytest tests/test_audit_cboost.py -q).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
