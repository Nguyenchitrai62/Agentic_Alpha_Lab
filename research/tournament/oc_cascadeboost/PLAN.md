# oc_cascadeboost — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_cascadeboost.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_cascadeboost/` + `tests/test_oc_cascadeboost.py`. Scratch only under
`research/tournament/oc_cascadeboost/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: one engine
job at a time, load one coin at a time where applicable, float32 where the engine allows). Long jobs:
nohup + log file under tmp/, poll the log. Heartbeat print every 600 s in long jobs.
Progress print every 10 minutes (this study is CPU-light until the engine stage; prints at each stage).

## Why and the contamination label

`research/tournament/oc_cascadedelay`: halving the dip budget for 3-7 days after a > 4 sigma 4h move
lost decisively (dSum5y -2.0 / -2.9, timing 0.1 in 2024): post-cascade dips carry the sleeve's profit.
The opposite rule is the natural hypothesis: INCREASE the dip budget after a cascade bar. BUT
oc_cascadedelay's replica covered all five years incl. the post-release year, so this idea was formed
after seeing those years: select on dev4 ONLY (anchors 2021-2024); the post-release year
(2025-09-24 .. 2026-09-23) number is a LABELLED DIAGNOSTIC (not clean evidence); only prospective
paper could confirm. This label is stated here BEFORE any outcome and repeated in REPORT.md /
results.json.

## Variants (exactly two + reference; everything else EXACTLY as oc_cascadedelay's PLAN, multiplier inverted)

- REF = G2 unchanged (dip mult 1), reproduction row (v421 R2B1D17BFG2) — engine stage only.
- B3 = dip budget x1.5 for 3 days after a cascade bar (mult 1.5 in window else 1.0).
- B7 = dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window else 1.0).
- Cascade bar definition and everything else EXACTLY as oc_cascadedelay's PLAN (section below);
  only the multiplier is inverted (0.5 -> 1.5) and the N labels renamed (V2/V1 -> B3/B7).
- Book untouched (both variants). The G2 dip gross cap (2.0) and every other G2 limit still bind
  (enforced inside the engine; replica is a linear w*mult overlay like oc_cascadedelay).
- No other variant, no ensemble, no threshold tuning.

## Cascade trigger + boost window (frozen, causal, existing 4h closes only — no new data; VERBATIM from oc_cascadedelay)

- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open;
  bar close time = T + 4h). Only the `close` column is used.
- READING OF "range > 4sg" (frozen, disclosed, inherited): "range" = absolute close-to-close log
  move |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED alternative: (H-L)-based range —
  highs/lows are not closes, contradicting the twice-stated "from closes only".
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6 bars/day),
  min_periods 120 (else NaN). SIG[i] uses only bars with close_time <= T[i] (r[i-1] resolves
  at close_time[i-1] = T[i]); the tested return r[i] resolves at close_time[i] = T[i]+4h and
  is NEVER in its own sigma window — causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 * SIG[i]
  (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h (known at tc).
  NaN SIG or non-finite closes -> never fires (conservative; counted and disclosed).
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at holding-bar open T on shift s
  is BOOSTED iff there EXISTS a trigger (ANY of the 5 majors, same shift s) with
  0 < T - tc <= N days (strictly after the trigger close, up to and including +N days).
  Same boosted(T, s) for all 5 coins (the sleeve budget is global; post-cascade flow is
  market-wide). REJECTED alternative: per-coin triggers — disclosed (inherited).
  On the 4h grid this is T in (tc, tc+Nd] = k = 1..42 bars (B7) / 1..18 bars (B3).
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first computable bar) ->
  1.0 (never boosted; inert — history from 2020-08-01 gives full 540-return windows for all
  of 2021-09-24.., disclosed with counts).
- Output: `boost_mult_4shift.parquet` (shift, T, boosted_B7, boosted_B3, mult_B7, mult_B3;
  T range = union of shift grids 2020-08-01..2026-09-23 20:00+shift).
- Unit-tested: hand-checked synthetic trigger/sigma/boost arithmetic + causality/
  truncation test (recompute from bars truncated at a cut date -> identical on kept prefix).
- If the data named does not cover an anchor year: disclose and skip that year for that
  variant (never impute). None expected (4h closes from 2020-08-01 cover all anchors with
  full 540-return windows; missing -> mult 1, counted and disclosed).

## No fits (nothing estimated)

There are no fitted parameters here: trigger threshold 4.0, windows (540/120/min),
boost 1.5, N = 7/3 are all frozen ex-ante round numbers (1.5 = inverted 0.5; N from the
assignment, never scanned). No harness join, no quantiles, no embargo beyond strict causality
(trigger at tc uses only closes with close_time <= tc). No statistic from any test year feeds
any choice.

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (closes for triggers).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy` (D0+B1 replica ledger
  read-only; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json`
  row R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82)
  — engine stage only.
- `research/tournament/oc_chronos/run_engine.py` (mechanism copied verbatim; only the dip
  mult lookup changes to the frozen boost mult) — engine stage only.

## Part 1 — replica + placebo gate (CPU-only, no engine yet; BINDING)

- For B3, B7: per fill in the reused ledger, key (shift, T=bar open): mult = 1.5 if
  boosted(T, shift) else 1.0 (same for all syms at that (shift, T); exact match on the
  shift grid, fallback to latest grid time <= T (ffill, causal); missing -> 1, counted).
- Per year y (4-phase means from ledger w*y, same phase_mean_sums as k2placebo/voltilt/
  crashgate/downshare/cascadedelay): base(y), boosted(y), realised_mean(y),
  norm(y) = boosted(y)/realised_mean(y). dSum5y = sum_y boosted(y) - sum_y base(y)
  (4-phase-mean sums, w*y units).
- Timing placebo per year (supporting, pre-registered adaptation for a MARKET-WIDE rule,
  inherited verbatim): bar universe per (year y, shift s) = time-bars (s, T) on that shift's
  grid with T in [A_y+s, min(A_y+s+365d, live1)); mult series per (y, s) permuted uniformly
  WITHIN (y, s) (1000 perms, seed 20261007+y; preserves per-shift boosted counts and the
  cross-sym sharing); fills map to their (y, s) time-bar. Block placebo: 42-bar
  chronological blocks per (y, s), permuted within (y, s) (seed 20261008+y).
  Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95; perm norms use the
  ACTUAL realised-mean denominator. Rationale (disclosed, inherited): permuting over
  (sym,shift,T) triples would break the pre-registered market-wide sharing (all syms share
  one mult per time-bar); time-bar permutation within (year, shift) is the correct null.
- Gate (as oc_cascadedelay): sum-half (boosted sum >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). DISCLOSED LIMITATION
  (pre-registered, same as oc_crashgate/oc_downshare/oc_cascadedelay): the k2placebo ledger
  carries no exit-date/daily path, so the replica DD-half cannot be scored at the replica
  stage; the binding DD check is the 4-phase engine (yearly DD + full-path DD <= 20).
  Timing percentiles are supporting evidence, not binding. Engine runs ONLY for variants
  passing the sum-half + dSum5y gate. If neither passes, STOP with no engine (negative
  result, valid).
- Arithmetic expectation (NOT a gate change, disclosed): boosted dSum5y = -delayed dSum5y
  up to ledger rounding (mult 1.5 = 1+0.5 vs 0.5 = 1-0.5 on the same cooled sets), so both
  B3/B7 are expected to pass (+2.0/+2.9 vs gate +0.273, 5/5 years); the gate is still
  applied mechanically and the engine still required.
- No statistic from any test year feeds any choice (triggers use closes <= tc only;
  thresholds/windows frozen; no fits).

## Part 2 — 4-phase engine (ONLY for gate-passing variants)

- Mechanism = exact copy of oc_chronos/run_engine.py (= v414 pipe v321, corr-aware inv
  sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first
  in shared 1m bar — engine handles). Dip leg: rung size x mult_B(T, shift) (1.5 in
  boost window else 1.0, market-wide per shift, same for all 5 coins at (shift, T));
  book leg byte-identical to G2. G2 dip gross cap 2.0 and every other G2 limit bind
  (kw["sleeve_gross_cap"] = 2.0, unchanged).
- Rows run through the engine (ONLY): REF + each gate-passing variant (B3 and/or B7).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit AND 5y/full-path 5.41/16.91/16.82 on the full
  window, else STOP). Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4
  robust pick only (every Y4 number labelled scored-once DIAGNOSTIC — contaminated, see
  top; REF Y4 must reproduce v421 G2 Y4 to the digit). No re-runs after outcomes; any
  change becomes a disclosed extra row. Via heavy_slot, one job at a time; resume-safe
  caches tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.
- Metrics / selection (fixed): per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`;
  dev4 geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of marked/close); worst 1m-marked DD episode
  for each row (peak/trough/depth on dd(t) = 1 - ms(t)/peak(es)(t); crash legs matter);
  pooled book/rung/all win rates + fills/year + sized mean multiplier + boosted share of
  fills and of (shift, T) time-bars. Robust pick on dev4 ONLY among REF + engine-run
  variants: DD <= 20, no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean. Post-release year scored ONCE, only for
  the pick (+ REF), LABELLED DIAGNOSTIC (contaminated, not clean evidence).

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window excludes the
  tested bar; boost window strictly after tc; truncation-tested in
  tests/test_oc_cascadeboost.py), label windows (no labels fit anywhere in this study),
  fit windows (no fits; frozen threshold/windows/N/boost, no statistic from any test year
  feeds any choice), fill timing (replica live 16..238 strict trade-through + stop-first
  inherited; engine win_start=5 + trade-through + stop-first if reached; perms reassign
  mults within (year, shift) only, seeds 20261007+y / 20261008+y). Gate costs inside
  replica outcomes / engine. Coverage: disclose any skipped anchor year (none expected;
  missing trigger history -> mult 1, counted).

## Compute plan (heavy_slot only for engine, resume-safe)

- `boost_rule.py`: pure helpers (`close_returns`, `trailing_sigma`, `triggers_of`,
  `boosted_mask`, `anchor_of`) — no data access; unit-tested. (Same arithmetic as
  oc_cascadedelay `delay_rule.py`; constant BOOST = 1.5, B3_DAYS = 3, B7_DAYS = 7.)
- `build_boost.py`: CPU-only 4h closes -> `boost_mult_4shift.parquet` + trigger counts
  per (year, shift) (fast, < 5 min; prints progress).
- `compute_replica_gate.py`: CPU-only boosted replica sums + dSum5y + 1000-perm
  timing/block placebo (time-bar within-(year,shift) permutation) for B3 + B7 on the
  reused ledger -> `tmp/replica_cascadeboost.json` (heartbeat every 600 s).
- `run_engine.py` + `analyze.py`: ONLY for gate-passing variants (same shape as
  oc_voltilt/run_engine.py + analyze.py, mult lookup = frozen boost parquet,
  market-wide per (shift, T); REF reproduction gate first; worst 1m-marked DD episode
  per row in analyze).
- Deliverables: PLAN.md (this file), boost_rule.py, build_boost.py,
  compute_replica_gate.py, (run_engine.py + analyze.py only if gated),
  boost_mult_4shift.parquet, results.json, REPORT.md, tests/test_oc_cascadeboost.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_cascadeboost.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
