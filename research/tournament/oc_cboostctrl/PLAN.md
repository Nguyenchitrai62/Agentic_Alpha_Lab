# oc_cboostctrl — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_cboostctrl.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_cboostctrl/` + `tests/test_oc_cboostctrl.py`. Scratch only under
`research/tournament/oc_cboostctrl/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: one engine
job at a time). Long jobs: nohup + log file under tmp/, poll the log. Heartbeat print every 600 s in
long jobs. Progress print every 10 minutes (engine stages print per shift-variant; each phase-variant
is ~0.1-0.3 min per oc_cascadeboost logs).

## Question

oc_cascadeboost B7 (dip budget x1.5 for 7 days after a cascade bar, > 4 sigma 4h close-to-close move)
is the dev4 robust pick (dev4 mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36).
Is B7 timing or just more exposure? Two exposure-matched controls, run IN THE ENGINE:
CTRL_C (constant multiplier, same average exposure, no timing) and CTRL_R (random 7-day windows,
same count, 20 seeds). CONTAMINATION (inherited, labelled): the boost idea was formed after
oc_cascadedelay's replica had covered all five years incl. the post-release year, so post-release
numbers are labelled diagnostics; new evidence in this study comes from the controls (this study
copies B7 verbatim and freezes both controls below before any control outcome; B7/REF numbers here
are reproductions, nothing is tuned).

## Rows (pre-registered, ONLY these)

- REF = G2 unchanged (dip mult 1.0 everywhere), reproduction row (v421 R2B1D17BFG2) — engine first.
- B7 = copy of oc_cascadeboost B7 verbatim (read-only `research/tournament/oc_cascadeboost/
  boost_mult_4shift.parquet` mult_B7: 1.5 in the 7d window after any > 4sg 4h bar else 1.0,
  market-wide per shift, same for all 5 coins at (shift, T)). No recomputation of triggers for B7.
- CTRL_C = constant dip-budget multiplier per anchor year, equal to B7's realised mean dip-budget
  multiplier in that year from B7's own engine run in THIS study (same average exposure, no timing).
- CTRL_R = random 7-day x1.5 windows with the same count per year as B7's cascade windows,
  20 random seeds (R00..R19); report mean, p5, p95 of each metric.
- Book untouched (all rows). G2 dip gross cap 2.0 and every other G2 limit bind (enforced inside
  the engine). No other variant, no ensemble, no tuning.

## Frozen cascade definition (verbatim oc_cascadedelay / oc_cascadeboost, for counts only)

- Source (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3 4h OHLCV; per (sym, shift) series sorted by T = bar open;
  bar close time = T + 4h). Only the `close` column is used.
- "range" = absolute close-to-close log move |r[i]|, r[i] = ln(C[i]/C[i-1]) (r[0] = NaN).
  REJECTED alternative: (H-L) range (not closes) — disclosed, inherited.
- SIG[i] = std(ddof=1) of r[i-540..i-1] (540 returns = 90d x 6 bars/day), min_periods 120
  (else NaN). Tested bar NEVER in its own sigma window — causal by construction.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 * SIG[i]
  (strict; 4.0 frozen). Trigger close tc = T[i] + 4h (known at tc). NaN SIG / non-finite
  closes -> never fires (conservative; counted and disclosed).
- B7 BOOST WINDOW (market-wide per shift, for reference): dip decision at holding-bar open T on
  shift s is boosted iff EXISTS a trigger (ANY of 5 majors, same shift s) with
  0 < T - tc <= 7 days. Mult 1.5 else 1.0. Missing history -> 1.0 (never boosted).
- This definition is used in THIS study only to derive the per-(year, shift) trigger counts
  k_{y,s} for CTRL_R (recomputed with copied verbatim arithmetic in build_ctrl.py) and,
  via the read-only B7 parquet, for the B7 engine leg. Threshold/windows (4.0/540/120),
  boost 1.5, N = 7 are frozen ex-ante round numbers, never scanned.

## CTRL_C (exposure control, frozen PROCEDURE; values filled mechanically after B7 runs)

- Realised mean per year from B7's own engine run: for year y (holding-bar-open year, per-shift
  intervals below), c_y = sum_s (sized_mean_{s,y} * n_sized_{s,y}) / sum_s n_sized_{s,y},
  where sized_mean_{s,y} / n_sized_{s,y} are the run_engine mult bookkeeping for B7
  (mean mult over dip sizings in year y on shift s). Dev constants c_0..c_3 come from the
  dev-stage B7 runs; c_4 comes from the last-stage B7 run (ordering below). Written to
  `tmp/ctrlC_dev.json` / `tmp/ctrlC_last.json` by compute_ctrlC.py (pure averaging, no choice).
- CTRL_C engine leg: every dip sizing with holding-bar open T in year y uses constant mult c_y
  (same for all syms/shifts at that T within the year). Year of T on shift s:
  [A_y+s, min(A_y+s+365d, live1)) with A = (2021-09-24, ..., 2025-09-24), s = shift hours,
  live1 = DEV1+s (dev) or Y1+s (last) — same `anchor_of` convention as boost_rule.
- Degenerate (no sizings in year, non-finite c_y): fallback 1.0, counted and disclosed.
- LABEL: CTRL_C is a NON-TRADABLE decomposition control by construction (c_y peeks at year y's
  own realised boosted share to equalise exposure); it never feeds any tradable choice and no
  selection is made on it. Its purpose is only the share split (B7-CTRL_C) vs (CTRL_C-REF).

## CTRL_R (random-timing control, fully frozen incl. seeds)

- Counts: k_{y,s} = number of union trigger closes tc (ANY major, shift s) with tc in the
  year-y interval [A_y+s, min(A_y+s+365d, live1_full)) where live1_full = Y1+s
  (2026-09-23+s; stage-independent full-history counts; dev years 0-3 reuse these k).
  Trigger tc list recomputed verbatim (build_ctrl.py) and stored in `tmp/ctrl_counts.json`
  with per-(y,s) grid sizes. Late-year trigger tails spilling into y+1 behave exactly as B7
  (windows are konkatenated on the grid; no truncation).
- Windows per (y, s, seed j), j = 0..19 (rows R00..R19): draw k_{y,s} DISTINCT grid-T starts
  uniformly without replacement from shift-s grid T values in the year-y interval
  [A_y+s, min(A_y+s+365d, live1_full)) (rng.choice replace=False; k=0 -> no windows;
  k>=N -> all boosted; counted). Seed frozen: seed(y,s,j) = 6100000 + j*100 + y*10 + s
  (all distinct; base never used before; rng = np.random.default_rng(seed)).
- Boosted mask: same helper as B7 (`boosted_mask`: T boosted iff EXISTS start ts with
  0 < T - ts <= 7 days; strictly-after, 42-bar geometry identical to B7; overlapping random
  windows merge). Mult 1.5 in window else 1.0, market-wide per shift, book untouched.
- Starts stored in `tmp/ctrlR_starts.pkl` ({(y,s,j): sorted start-ns list}, built CPU-only
  before any engine run, deterministic from frozen seeds). Engine loads it read-only.
- Null rationale (disclosed): per-(year,shift) count matching preserves per-shift boosted
  budgets and the market-wide sharing; random positions break timing only.

## Engine (mechanism = exact copy of oc_cascadeboost/run_engine.py = oc_chronos/run_engine.py)

- = v414 pipe v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Dip leg: rung size x mult_row(T, shift); book leg byte-identical to G2. Rows:
  REF (1.0), B7 (mult_B7 parquet, exact match + causal ffill fallback, missing -> 1.0),
  CTRL_C (c_y of T's year), Rjj (random-window mult from frozen starts, same fallback).
- Mult bookkeeping per (shift, year): sized-mean + n_sized (same msum/mcnt as cascadeboost).
- Stages: dev [DEV0=2021-09-24, DEV1=2025-09-24), last [DEV0, Y1=2026-09-23).
  Order (one heavy job at a time, resume-safe caches tmp/runs_dev.pkl tmp/runs_last.pkl):
  (1) REF dev -> verify vs v421 G2 years 0..3 R/DD to the digit AND 5y path numbers later,
  else STOP; (2) B7 dev -> compute c_0..3; (3) CTRL_C dev + R00..R19 dev; (4) analyze dev;
  (5) last REF+B7 ONCE -> determinism check (dev segments equal stage-dev) + REF Y4/5y/full-path
  to the digit, else STOP -> compute c_4 (+re-verify c_0..3); (6) last CTRL_C + R00..R19 ONCE;
  (7) analyze last. No re-runs after outcomes; any change = disclosed extra row.
- DISCLOSED DEVIATION from the common header ("last year ONCE only for pick+ref"): the
  assignment requires 5y / full-path DD / per-year p95 for the controls, so last stage runs
  ALL rows once. Last-year control numbers are scored-once DIAGNOSTICS, never used for any
  selection (there is NO selection in this study — B7 is the frozen copy).

## Metrics / verdict (fixed)

- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean, WORST-year R,
  DDmax = max(max yearly DD, dev full-path DD), losing count; 5y geo mean; full-path DD via
  `v388.mix` equal-1/4 mix from 2021-09-24 (max of marked/close DD); worst 1m-marked DD episode
  per row (same dd(t) = 1 - ms(t)/peak(es)(t) helper); pooled book/rung/all win rates +
  fills/year + sized mean multiplier + boosted share of sizings and of (shift, T) time-bars.
- CTRL_R: full per-seed metrics + distribution mean / p5 / p95 of EACH metric (per-year R and
  DD, dev4 mean / WORST / DDmax, 5y R, full-path DD). Per-year question: is B7's year-R above
  the 20-seed p95 (each dev year + Y4 diagnostic)?
- Share split (primary on dev4 mean; per-year too): exposure = (CTRL-REF)/(B7-REF),
  timing = (B7-CTRL)/(B7-REF) when B7 > REF (else disclosed as undefined/degenerate).
  Primary CTRL = CTRL_C (exact mean-exposure); secondary = CTRL_R mean (random-timing).
- Verdict: 3-line Vietnamese conclusion — timing vs exposure shares + B7-vs-p95 per year.

## Leakage / checks (stated in REPORT)

- Feature timing: triggers use closes with close_time <= tc only; SIG excludes tested bar;
  windows strictly after tc; truncation-tested (tests/test_oc_cboostctrl.py).
- CTRL_C peeks at its year's realised mean BY DESIGN (non-tradable control, labelled).
- CTRL_R windows are random (no data use); seeds frozen ex-ante.
- Fit windows: no fits anywhere (threshold/windows/boost/N/seeds frozen; c_y is a mechanical
  exposure equaliser, not a fitted parameter; k_{y,s} are counts from causal triggers).
- Fill timing: engine win_start=5 + 1m trade-through + stop-first (inherited).
- Gate costs inside the engine. Coverage: 4h closes cover all anchors; missing mult -> 1.0,
  counted.

## Compute plan

- `ctrl_rule.py`: pure helpers (`boosted_mask` copy, `constant_for`, `random_starts_for`,
  `seed_of`, `anchor_of`) — no data access; unit-tested.
- `build_ctrl.py`: CPU-only 4h closes -> `tmp/ctrl_counts.json` (k_{y,s} + grid sizes +
  trigger totals) + `tmp/ctrlR_starts.pkl` (frozen 20-seed starts); prints progress.
- `compute_ctrlC.py`: B7 runs -> `tmp/ctrlC_dev.json` / `tmp/ctrlC_last.json` (c_y + n).
- `run_engine.py` + `analyze.py`: as above (REF gate first; determinism check; ctrlR
  distributions + share split; worst 1m-marked episode per row).
- Deliverables: PLAN.md (this file), ctrl_rule.py, build_ctrl.py, compute_ctrlC.py,
  run_engine.py, analyze.py, tmp/ctrl_counts.json, tmp/ctrlR_starts.pkl,
  tmp/ctrlC_*.json, results.json, REPORT.md, tests/test_oc_cboostctrl.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_cboostctrl.py -q`).

## Post-hoc log

- 2026-10-08, before any outcome: `run_engine.py` used `variant.startswith("R")`
  which also matched "REF" (crashed with ValueError, produced no outcome) — narrowed
  to the frozen R00..R19 set. No scored number affected.
- 2026-10-08, after a partial non-scored outcome (CTRL_C dev shift-0 eq_end only):
  dev-stage CTRL_C lookup for out-of-window year-4 sizings (past live1, unscored in
  dev) falls back to mult 1.0 instead of KeyError. Scored dev years 0..3 use the
  filed constants; no scored number affected. (Original rows kept; no extra variant.)
