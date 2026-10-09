# oc_b7thresh — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7thresh.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_b7thresh/` + `tests/test_oc_b7thresh.py`. Scratch only under
`research/tournament/oc_b7thresh/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Heavy work (engine 1m, stop recompute if needed) via
`scripts/heavy_slot.py` (RAM tight: one heavy job at a time, one coin in RAM at a time where
applicable, float32 where the engine allows). Long jobs: nohup + log file under tmp/, poll the log.
Heartbeat print every 600 s in long jobs. Progress print every 10 minutes.

## Why — robustness surface, NOT a selection (B7 stays 4 sigma / 7 days)

B7 (`research/tournament/oc_cascadeboost`: dip budget x1.5 for 7 days after a > 4 sigma 4h move)
is the biggest gain found (dev4 mean 6.74 vs G2 5.60, 5y 6.36). A knife-edge optimum (4.0/7 an
isolated peak with cliffs on all sides) would be a red flag; a broad plateau (neighbours also
help, monotonic-ish in W, flat-ish in k) would be reassuring. This study maps the surface and
REPORTS ONLY: nothing here changes B7, no variant is adopted, no threshold/window is refit, no
selection is made on any year (dev4, 5y, pre-sample or post-release).

## Grid (fixed, exactly 12 cells + reference; nothing else)

- Trigger threshold k in {3.5, 4.0, 4.5} sigma x window W in {3, 5, 7, 10} days = 12 cells.
- Multiplier fixed 1.5 in window else 1.0 (never scanned). Book untouched (dip-only sizing overlay;
  presample replica has no book leg anyway; engine book leg byte-identical to G2).
- Cascade definition otherwise EXACTLY oc_cascadedelay (section below verbatim, only k varies).
- Cell labels: `k35_W03`, `k35_W05`, `k35_W07`, `k35_W10`, `k40_W03`, `k40_W05`, `k40_W07` (=B7),
  `k40_W10`, `k45_W03`, `k45_W05`, `k45_W07`, `k45_W10`. REF = mult 1 (reproduction row only).
- The 4.0/7 cell must reproduce oc_cascadeboost B7 replica numbers exactly (gate below); the
  4.0/3 cell must reproduce oc_cascadeboost B3 replica numbers exactly.

## Cascade trigger + boost window (frozen, causal, existing 4h closes only — VERBATIM oc_cascadedelay except k)

- Source (read-only): main period `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3, per (sym, shift) sorted by T = bar open; bar close = T+4h; only `close`
  used); pre-sample `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (4 syms
  BTC/ETH/BNB/XRP, SOL absent; union over available majors only — disclosed).
- READING OF "range > k sg" (frozen, inherited): "range" = absolute close-to-close log move |r[i]|
  with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED alternative: (H-L)-based range.
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540..i-1] (540 returns = 90d x 6 bars/day),
  min_periods 120 (else NaN). SIG[i] uses only bars with close_time <= T[i]; the tested return
  r[i] resolves at close_time[i] = T[i]+4h and is NEVER in its own sigma window — causal by
  construction, no self-inclusion.
- TRIGGER (k varies, strict): bar i of (sym, shift) fires iff SIG[i] finite > 0 AND
  |r[i]| > k * SIG[i] with k in {3.5, 4.0, 4.5}. Trigger close time tc = T[i]+4h (known at tc).
  NaN SIG or non-finite closes -> never fires (conservative; counted and disclosed).
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at holding-bar open T on shift s
  is BOOSTED iff there EXISTS a trigger (ANY major available on that period, same shift s) with
  0 < T - tc <= W days (strictly after the trigger close, up to and including +W days). Same
  boosted(T, s) for all coins. On the 4h grid T in (tc, tc+Wd] = k = 1..18/30/42/60 bars for
  W = 3/5/7/10. REJECTED alternative: per-coin triggers — disclosed (inherited).
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first computable bar) -> 1.0
  (never boosted; inert — disclosed with counts).
- Output: `boost_grid_main.parquet` (shift, T, one bool+mult column per cell; T range = union of
  main shift grids 2020-08-01..2026-09-23) and `boost_grid_pre.parquet` (same for the pre-sample
  grid 2017-08-17..2020-09-30). Triggers raise monotonically as k falls (k35 superset k40 superset
  k45); for fixed k, W10 superset W07 superset W05 superset W03 — asserted in code and tests.
- Unit-tested: hand-checked synthetic trigger/sigma/boost arithmetic (incl. k and W boundaries) +
  causality/truncation test (recompute from bars truncated at a cut date -> identical on kept
  prefix) + monotonicity test (superset relations above).
- If the data named does not cover an anchor year: disclose and skip that year for that cell
  (never impute). None expected (main 4h from 2020-08-01 give full 540-return windows for all of
  2021-09-24..; pre-sample from 2017-08-17, early NaN-SIG bars never fire — counted, not imputed).

## No fits (nothing estimated)

Trigger thresholds {3.5,4.0,4.5}, windows {3,5,7,10}, boost 1.5, sigma windows (540/120) are all
frozen ex-ante from the assignment (never scanned beyond the fixed grid). No harness join, no
quantiles, no embargo beyond strict causality (trigger at tc uses only closes with close_time <=
tc). No statistic from any test year feeds any choice. The post-release year is never used to pick
between cells (no picking at all — report only).

## Frozen inputs (read-only, never edited, never refit)

- Main closes: `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`.
- Pre closes: `research/tournament/oc_presampletilt/bars_4h_presample.parquet`.
- Main ledger (contaminated, labelled): `research/tournament/oc_k2placebo/tmp/ledger.npz` +
  `bt_all.npy` (D0+B1 replica read-only; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- Pre ledger (clean): `research/tournament/oc_presampletilt/tmp/ledger_presample.npz` +
  `bt_presample.npy` (gate n == 9731, per-leg 909/2986/3115/2721, base sums ==
  (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6).
- Pre stop kinds (read-only, boost-independent): `research/tournament/oc_cboostpre/tmp/stop_kinds.npz`
  (kind codes in ledger order; unknown = -1). Kinds depend only on fills + 1m, never on the boost,
  so joining them to new boosted sets is exact with no recompute.
- Engine baseline: `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82).
- Engine mechanism: `research/tournament/oc_chronos/run_engine.py` (= v414 pipe v321, corr-aware inv
  kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs inside
  the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m
  trade-through; nothing in first 5 min after a 4h close; stop-first in shared 1m bar).

## Part 1 — replica surface on both ledgers (CPU-only, no engine; REPORT ONLY, no gate)

- Per fill join (phase=shift, T=bar open): exact match on the shift grid, fallback to latest grid
  time <= T (ffill, causal); missing -> 1.0 (counted and disclosed). Same for all syms at (shift,T).
- Per year y (4-phase means from ledger w*y, same phase_mean_sums as k2placebo/voltilt/cascadedelay/
  cascadeboost/cboostpre): base(y), boosted(y), realised_mean(y) = mean mult over fills in y,
  norm(y) = boosted(y)/realised_mean(y), gain(y) = norm(y) - base(y). "Helps" in a year iff
  gain(y) > 0. Report n fills + boosted fill share per cell-year. Main years: 2021..2024 + 2025
  screen (labelled CONTAMINATED — idea formed after seeing the delay replica incl. post-release;
  the 2025 column is a labelled diagnostic, never a selection input). Pre years: Y2017/Y2018/Y2019/
  Y2020p (clean, never seen when B7 was formed).
- Timing placebo per cell-year (supporting, pre-registered market-wide null, inherited verbatim):
  bar universe per (year y, shift s) = time-bars (s,T) on that shift's grid in the year's interval;
  mult series per (y,s) permuted uniformly WITHIN (y,s) (1000 perms, seed 20261007+y with y=0..4
  main / 0..3 pre; preserves per-shift boosted counts and cross-sym sharing); fills map to their
  (y,s) time-bar. Block placebo: 42-bar chronological blocks per (y,s), permuted within (y,s)
  (seed 20261008+y). Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95; perm norms
  use the ACTUAL realised-mean denominator.
- Boosted stop rate (crash-risk leg): PRE-SAMPLE all 12 cells — join each cell's boosted fill set
  to the reused read-only `stop_kinds.npz` (verbatim mu=1.0 kinds; "hit the stop" = {stop,backstop});
  report per cell-year base stop% vs boosted stop% (delta) over known kinds only + pooled. MAIN
  replica ledger carries no exit-date/daily path (same pre-registered limitation as
  oc_cascadedelay/oc_cascadeboost: replica DD-half cannot be scored from this ledger), so no
  replica stop rate is computable on main without a new 1m kind recompute (out of scope for a
  report-only surface); main crash-risk is instead the engine DD leg below (yearly DD + full-path
  DD for the 4 corners) plus boosted fill shares. DISCLOSED here before any outcome.
- Reproduction gates (must pass before any surface row is trusted): k40_W07 == B7 and k40_W03 == B3
  replica rows must equal oc_cascadeboost tmp/replica_cascadeboost.json (gains/dSum) and pre
  k40_W07/W03 must equal oc_cboostpre tmp/boost_presample.json, up to 1e-6 rounding; ledger base
  gates above must pass; else STOP and report.
- Heat tables (the report): per evaluation set, per cell: yearly gains, helps-count, timing-significant
  count, pooled/mean gain, boosted fill share; pre set additionally boosted stop deltas. Plateau test
  (pre-registered, descriptive only): (i) is k40_W07 the argmax on each set? (ii) do all 4-neighbours
  (k±0.5, W±one step) also help (gain>0)? (iii) does the gain rise then flatten/fall with W at k=4.0
  (diminishing returns vs cliff)? (iv) does the ordering survive on the clean pre-sample set? No
  threshold is tuned from the answers.

## Part 2 — 4-phase engine (ONLY the 4 corner cells + REF; REPORT ONLY, no selection)

- Corners (fixed by assignment): C1 = 3.5/3 (k35_W03), C2 = 3.5/10 (k35_W10), C3 = 4.5/3 (k45_W03),
  C4 = 4.5/10 (k45_W10). REF = G2 unchanged (mult 1). No other engine row (in particular the centre
  B7 engine numbers are cited read-only from oc_cascadeboost, never re-run).
- Mechanism = exact copy of oc_cascadeboost/run_engine.py (= oc_chronos/run_engine.py, see frozen
  inputs): dip rung size x mult_cell(T, shift) (1.5 in window else 1.0, market-wide per shift, same
  for all 5 coins at (shift,T)); book leg byte-identical to G2; G2 dip gross cap 2.0 and every other
  G2 limit bind (kw["sleeve_gross_cap"] = 2.0, unchanged).
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) (REF first; must reproduce v421 G2 years
  0..3 R/DD to the digit AND 5y/full-path 5.41/16.91/16.82 on the full window at the last stage,
  else STOP). Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the 4 corners (every Y4 number
  labelled scored-once DIAGNOSTIC — contaminated, see top; REF Y4 must reproduce v421 G2 Y4 to the
  digit). No re-runs after outcomes; any change becomes a disclosed extra row. Via heavy_slot, one
  job at a time; resume-safe caches tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s;
  nohup + tmp log.
- Metrics (fixed): per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean, W
  (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via `v388.mix` equal-1/4 mix
  from 2021-09-24 (max of marked/close); worst 1m-marked DD episode per row; pooled book/rung/all win
  rates + fills/year + sized mean multiplier + boosted share of fills and of (shift,T) time-bars.
  Engine table is descriptive (are corners within ~1pp of B7? does DD stay <= 20?); NO robust pick is
  made here (B7 stays the candidate regardless).

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window excludes the tested bar;
  boost window strictly after tc; truncation-tested in tests/test_oc_b7thresh.py), label windows (no
  labels fit anywhere in this study), fit windows (no fits; grid frozen ex-ante, no statistic from any
  test year feeds any choice; pre-sample years never used for any fit), fill timing (replica live
  16..238 strict trade-through + stop-first inherited; engine win_start=5 + trade-through + stop-first;
  perms reassign mults within (year, shift) only, seeds 20261007+y / 20261008+y). Gate costs inside
  replica outcomes / engine. Coverage: disclose any skipped anchor year (none expected; missing
  trigger history -> mult 1, counted). Contamination labels repeated on every main-period number.

## Compute plan (heavy_slot only for engine, resume-safe)

- `thresh_rule.py`: pure helpers (`close_returns`, `trailing_sigma`, `triggers_of` with k param,
  `boosted_mask` with W param, `anchor_of`) — no data access; unit-tested. (Arithmetic VERBATIM
  oc_cascadedelay delay_rule.py / oc_cascadeboost boost_rule.py; constant BOOST = 1.5.)
- `build_grids.py`: CPU-only 4h closes -> `boost_grid_main.parquet` + `boost_grid_pre.parquet` (one
  bool+mult column per cell) + trigger counts per (k, year, shift) + boosted shares (prints progress;
  heartbeat every 600 s).
- `compute_replica_main.py`: CPU-only 12-cell boosted replica sums + gains + 1000-perm
  timing/block placebo on the reused main ledger -> `tmp/replica_main.json` (heartbeat every 600 s).
- `compute_replica_pre.py`: CPU-only 12-cell boosted replica sums + gains + 1000-perm
  timing/block placebo on the reused pre ledger + boosted stop rates via reused stop_kinds.npz ->
  `tmp/replica_pre.json` (heartbeat every 600 s).
- `run_engine.py` + `analyze.py`: ONLY REF + 4 corners (same shape as oc_cascadeboost/run_engine.py
  + analyze.py, mult lookup = frozen corner grids, market-wide per (shift,T); REF reproduction gate
  first; worst 1m-marked DD episode per row in analyze).
- Deliverables: PLAN.md (this file), thresh_rule.py, build_grids.py, compute_replica_main.py,
  compute_replica_pre.py, (run_engine.py + analyze.py), boost_grid_*.parquet, tmp/*.json,
  results.json, REPORT.md, tests/test_oc_b7thresh.py (>=1 causality/truncation test + >=1
  hand-checked synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7thresh.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays and
  the change is a disclosed extra row).
