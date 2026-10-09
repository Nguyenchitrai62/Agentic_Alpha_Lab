# oc_mvrvrobust PLAN (pre-registered BEFORE any new outcome, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_mvrvrobust.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Write ONLY `research/tournament/oc_mvrvrobust/` + `tests/test_oc_mvrvrobust.py`.

## Context (frozen, from oc_lit_position — no re-selection)

- M1 = ALL majors' book LONG weights x0.5 while BTC MVRV-z > 2.0, else x1.0.
  zM(D) = (MVRV(D) - mean(W)) / std(W, ddof=1), W = trailing <= 365 daily
  `CapMVRVCur` ending at D inclusive, min 180 else NaN; std==0 -> NaN.
  Day D usable from D+1 02:00 UTC; z(T) = zM(D*(T)).
- Frozen numbers (oc_lit_position engine_results.json): dev4 M1 6.192 vs G2 5.601,
  DD 16.26 vs 16.91, beats CTRL_M1 5.735; worst dev year ties 2.588; gains
  concentrate in 2023 (+1.78 pp). Most recent year was NOT a selection input.
- This task is ROBUSTNESS of frozen M1 only. No threshold/window/mult refit.
  All rows below are fixed here before any new computation.

## Base + mechanism (fixed, v426 copy)

- Base = G2 (`R2B1D17BFG2`, v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  multiplier on STANDARD book rows (T, sym) with bear-filtered weight > 0,
  AFTER the bear-book filter, BEFORE the shifted-clock forward fill.
  Shorts/flats/NaN-z unchanged. Rows before 2021-09-24 not gated.
- Harness, costs, fills, reset metric, full-path DD exactly as v426/v421
  (gate costs: maker 0.0002, taker 0.00055; longs pay 0.0001/8h at 00/08/16 UTC,
  shorts nothing; limit fills only on 1m trade-through; `win_start=5`;
  stop-first in same 1m bar).
- Reproduce G2 (5.41 / W 2.588 / DD 16.91 / full 16.82, yearly rows
  [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9]) and M1
  (dev4 6.192 / W 2.588 / DD 16.26; 5y 5.881 / full 16.22) to the digit first
  from cached `oc_lit_position/engine_runs.pkl` + `engine_results.json`,
  plus a bit-exact engine re-run of G2+M1; else STOP.
- Anchors: dev years A in {2021,2022,2023,2024}-09-24, each [A, A+365d);
  dev4 = first four. Most recent year 2025-09-24..2026-09-23 scored ONCE,
  labelled, never a selection input.

## Pre-registered rows (ONLY these reach the engine)

- FROZEN: M1 (thr 2.0, win 365, min 180, mult 0.5), G2, CTRL_M1 (per-year
  constant long multiplier = M1 realised mean over long rows that year).
- Jitters (one knob each, all else frozen):
  - J_T175: threshold 1.75 (win 365, mult 0.5).
  - J_T225: threshold 2.25 (win 365, mult 0.5).
  - J_W270: z window 270 days (thr 2.0, min 180, mult 0.5).
  - J_W450: z window 450 days (thr 2.0, min 180, mult 0.5).
- Frictions S1-S5 on M1 vs G2 (oc_amihudrobust does not exist yet, so copied
  verbatim from the v421-audit family as implemented in
  `research/diagnostics/oc_d13robust/robust_d13.py` /
  `research/diagnostics/oc_g2k20robust/robust_g2k20.py`):
  - S1 cost stress: patch `simulate.__globals__` MAKER 0.0004 / TAKER 0.0012
    (= 0.0007 + 0.0005 5-bps taker stress); win_start 5.
  - S2 latency 15: win_start 15, sleeve_start 16.
  - S3 latency 30: win_start 30, sleeve_start 31.
  - S4 stop slip 50%: win_start 5, stop_slip 0.5.
  - S5 Bybit prices: 1m cube/opens from `data/raw/bybit_linear_1m_20261004/`,
    all phases start 2021-11-15 (SOL starts 2021-10-15); compare M1 vs G2 on
    the same S5 window. If Bybit build fails, report as missing, never silently
    substitute Binance.
- Leave-one-episode-out (LOEO): episodes = merged gated episodes from the
  event table (rule below). One engine row per episode E: M1 with bars in E
  forced to mult 1.0 (everything else frozen). Report dev4 mean with each
  episode removed. If > 4 merged episodes, test only those covering >= 5% of
  total gated bars (pre-registered cap).
- Combined (labelled post-hoc, NOT a candidate): A1M1 = M1 gate THEN Amihud A1
  tilt from oc_lit_xs (weights x (1+0.25*z_illiq), clip [0.5,1.5], both legs,
  NaN->1; D*(T) = date(T)-1 day; applied to the M1-gated book AFTER the bear
  filter, before ffill). One row, dev4 + 5y. Order fixed here.

## Event table (Task 1, fixed rule)

- Gate flag per STANDARD 4h bar T: g(T) = 1 iff M1 mult(T) < 1 (finite z > 2.0
  and T >= 2021-09-24), else 0. Signal from `signals.py` copy (frozen M1 def).
- Windows = maximal contiguous g=1 runs on the STANDARD index.
- Episodes = windows merged if the gap between them is <= 14 days (pre-registered;
  avoids splitting one euphoria across a brief z dip). Each episode: start (first
  gated bar), end (last gated bar), days (end-start, calendar), plus per anchor
  year attribution by bar overlap.
- Per episode/window row: BTC buy-hold return over [start, end] from 4h closes
  (or daily if 4h missing), and TOTAL-equity window P&L for G2 vs M1 from the
  cached 4-phase-mean equity paths (labelled total-equity proxy — the full engine
  does not separate book-only P&L; the M1-G2 difference inside a gated window is
  book-gate-driven by construction). Difference = M1 - G2.
- Verdict input: count independent episodes carrying the dev4 gain (dev4 gain =
  M1 dev4 mean - G2 dev4 mean on the reset metric; window diffs are descriptive).

## Metrics + verdict (fixed)

- Per engine row: per-year 4-phase reset R (%/mo geometric), yearly DD,
  full-path DD (v388.mix), dev4 mean / worst / DD, 5y mean / DD / full DD.
- Frictions: report M1 vs G2 dev4 mean (and 5y where defined; S5 on its own
  window) per S1-S5; "positive under every friction" = M1 dev4 mean > G2 dev4
  mean in each S1-S5 row (S5: on the S5 window).
- Jitters: ">= G2" = dev4 mean >= G2 dev4 5.601.
- Robust (assignment rule) iff ALL of: gain spread over >= 2 episodes (no single
  episode explains > 80% of the dev4 gain in LOEO), all 4 jitters dev4 >= G2,
  M1 > G2 under every friction S1-S5. Else single-event luck / fragile.
- Vietnamese 3-line verdict in REPORT.md.

## Leakage checks (pre-registered)

- Feature timing: MVRV daily as-of D+1 02:00 <= T (searchsorted right-1);
  A1 daily as-of D+1 00:00 <= T; truncation test leaves mults unchanged.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; rolling norms are causal features (windows end at/before
  availability); thresholds/windows fixed here; CTRL means realised-exposure only.
- Fill timing: win_start per row + 1m trade-through + stop-first (harness,
  G2 bit-exact). Tests assert these.

## Deliverables

- `research/tournament/oc_mvrvrobust/`: PLAN.md (this file), `signals_mvrv.py`
  (frozen M1 + jitter mults, copy of oc_lit_position/signals.py H8 part),
  `compute_events.py` (event table, no engine), `compute_engine.py`
  (jitters + A1M1 + LOEO + frictions via heavy_slot, Pool(2)),
  `results.json`, `REPORT.md` (tables, what failed, 3-line Vietnamese verdict).
- `tests/test_oc_mvrvrobust.py`: >=1 causality/truncation test + >=1
  hand-checked synthetic case; run
  `.venv/Scripts/python.exe -m pytest tests/test_oc_mvrvrobust.py -q`.
  Stop when done.

## Post-hoc log

- (empty at pre-registration; any change after an outcome keeps the original
  row and adds the change as a disclosed extra row.)
- Coordination note (after outcomes, no definition change):
  `research/tournament/oc_amihudrobust/PLAN.md` appeared mid-task (parallel
  worker); its Row-1 friction defs (S1 MAKER 0.0004/TAKER 0.0012 via globals
  patch; S2 15/16; S3 30/31; S4 stop_slip 0.5; S5 Bybit from 2021-11-15) match
  the S1-S5 implementations used here verbatim. No code change needed.
