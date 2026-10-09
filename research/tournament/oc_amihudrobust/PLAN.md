# oc_amihudrobust PLAN (pre-registered BEFORE any engine run, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_amihudrobust.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Frozen A1 from `research/tournament/oc_lit_xs` (copied, not edited):
A1 = book weights x (1 + 0.25 z), z = cross-sectional z-score (across the 5 coins
at the same bar) of each coin's trailing-30-day Amihud illiquidity
(|daily return| / daily quote volume), applied to both long and short weights
on standard book rows (v426 mechanism: multiplier on STANDARD rows after the
bear filter, before the shifted-clock forward fill; rows before 2021-09-24
untilted; clip [0.5,1.5]; NaN->1).
oc_lit_xs gave (given, not computed here): dev4 5.844 / worst 2.798 / DD 16.81
vs G2 5.601 / 2.588 / 16.91; most recent year 4.750 / 11.14 vs 4.648 / 12.90.
A1 was 1 of ~20 variants screened today -> multiple-testing risk.
All rows below are ROBUSTNESS of the frozen A1 (no re-selection);
report dev4 (anchors 2021-09-24..2024-09-24, each [A,A+365d)) and the 5-year path.
Write ONLY `research/tournament/oc_amihudrobust/` + `tests/test_oc_amihudrobust.py`.

## Base (reproduction gate, stop if failed)

- G2 = `R2B1D17BFG2` in v421 (rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- Validate cached `v421/v421_runs.pkl` via `reset_metric.year_reset` + `v388.mix`:
  5.41 %/mo, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly
  (2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9).
- Engine must re-run G2 AND A1 to the same triple (dev4 G2 5.601/W 2.588/DD 16.91;
  A1 5.844/W 2.798/DD 16.81) before any other comparison is valid.
- Gate costs (all engine rows): maker 0.0002, taker 0.00055 (stops/market taker),
  longs pay 0.0001 per 8h settlement held (00/08/16 UTC), shorts nothing;
  limit fills only on 1m trade-through, no fill first 5 min (`win_start=5`
  base), stop-first in same 1m bar.

## Row 1 — Frictions on A1 and G2 (4-phase engine, 12 rows)

Copy the five friction rows of the v421 audit EXACTLY
(`research/parallel/rounds/parallel-20260906-r2/v421_audit/ROBUST.md` +
`robust_v421.py`; same defs as `oc_carryfric`):
- S1 cost stress: MAKER 0.0004 / TAKER 0.0012 (patched via
  `eu.simulate.__globals__`, restored after; robust_v421.py line 284).
- S2 latency 15/16: `win_start=15, sleeve_start=16`.
- S3 latency 30/31: `win_start=30, sleeve_start=31`.
- S4 stop slip 50%: `win_start=5, stop_slip=0.5`.
- S5 Bybit prices from 2021-11-15: `bybit_minutes()` from
  `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` instead of
  `pod.minutes()`; `live0 = 2021-11-15 + shift`; standard index filtered to
  `>= 2021-11-15` before shift; year-2021 is a short window (labelled).
  If Bybit files are missing/unreadable, report S5 as not reproducible.
Rows: G2_base, A1_base (=repro), G2_S1..S5, A1_S1..S5 (12 engine rows).
Metric per row: dev4 mean/W/DD + 5y mean/W/DD + full-path DD + yearly R/DD.
Robust sub-verdict: A1-G2 gap > 0 under base AND under every friction S1..S5
(dev4 mean; also report 5y gap).

## Row 2 — Jitter on A1 only (4-phase engine, 4 rows, one knob each)

Frozen mechanism, one knob changed at a time (clip [0.5,1.5] unchanged,
both-legs, same v426 slot):
- J_K015: K=0.15, Amihud window 30d (min 20).
- J_K035: K=0.35, Amihud window 30d (min 20).
- J_W20: K=0.25, Amihud window 20d (min 13 = round(20*2/3)).
- J_W45: K=0.25, Amihud window 45d (min 30 = round(45*2/3)).
(Min-period scaling pre-registered here: min = round(W*2/3); base 30->20.)
Robust sub-verdict: all 4 jitters have dev4 mean > G2 dev4 mean (5.601).

## Row 3 — Timing placebo (VECTORISED proxy, 500 draws, no engine)

50 full-engine runs x 4 phases (=200 phase runs on top of the ~68 already
planned) exceed the compute budget, so per the assignment fallback we run the
vectorised book-timing proxy of `research/tournament/oc_bookattrib`
(`analyze_bookattrib.py`) for 500 placebos instead (stated here, pre-registered).
Proxy (read-only replica): w = bear-filtered standard books ffill to shifted
clocks; r = next-bar open-to-open on that shift's 1m-open series; B = sum(w*r)
per bar; cumprod per [A,A+365d) wall-clock year; monthly geometric; 4-phase mean.
Placebo construction (fixed here): per anchor year independently, per coin
independently, circular-shift the RAW Amihud30 daily series by a random offset
that is a multiple of 30 days (180 4h bars on the standard-book index), drawn
uniformly from {0,30,...,330} days (seed 12345; offset 0 allowed = unshifted by
chance, kept to keep the null honest); then recompute the cross-sectional z at
each T (same ddof=1 rule, <2 finite or std 0 -> 0) and the A1 multiplier
(1+0.25*z, clip [0.5,1.5]); evaluate the proxy dev4 mean. Report the distribution
(dev4 mean histogram: mean/sd/min/max), A1 proxy dev4 mean, and A1's percentile
(frac(placebo <= A1)). Robust sub-verdict: percentile >= 90.
Also report G2 proxy dev4 mean as a sanity anchor (proxy is gross timing, not
the gated engine: levels need not match the engine, only the ordering matters).

## Row 4 — Static coin-tilt control (4-phase engine, 1 row)

Per (anchor year Y, coin c) a CONSTANT multiplier = that coin's mean realised
A1 multiplier over the TRAINING window (the year before the anchor):
TRAIN(Y) = [Y-365d, Y-7d) on the standard-book index (7-day embargo per
W_COMMON; no return information, realised-exposure only). Applied as a constant
per-(year,coin) multiplier to every non-zero bear-filtered book cell of year Y
before the shifted-clock ffill (both legs, same slot as A1). Rows before
2021-09-24 untilted. Row name: C_STATIC. Robust sub-verdict: A1 dev4 mean >
C_STATIC dev4 mean (timing beats slow overweight; also report per-coin TRAIN
means to expose e.g. XRP overweight).

## Row 5 — Per-coin decomposition of A1's gain vs G2 (vectorised proxy, no engine)

Same proxy as Row 3 (open-to-open, 4 clocks), per coin c:
bc(G2) = w_c(G2)*r_c, bc(A1) = w_c(A1)*r_c; per-coin yearly R via cumprod;
A1-G2 gain per coin per year and dev4 total; timing-split (beta vs timing)
per coin as in `oc_coinattrib/analyze_coinattrib.py` (wbar per coin-year).
Report per-coin dev4 gain, share of total A1-G2 proxy gain, and whether one
coin (e.g. XRP) dominates. No engine, no selection claim.

## Leakage checks (pre-registered)

- Feature timing: daily `D*(T)=date(T)-1day` (day D usable iff D+1 00:00<=T);
  sampled-T truncation test must leave multipliers unchanged; +-1s boundary test
  exposes exactly the prior day.
- Label windows: none fitted (engine uses realised 1m path; proxy uses realised
  next-bar opens).
- Fit windows: no fits; XS mean/std at same T only; K/windows/clip/placebo
  offsets/static TRAIN rule fixed here.
- Fill timing: engine `win_start` per friction + 1m trade-through + stop-first
  (v426 harness, G2 bit-exact). Tests assert these constants in the engine script.

## Deliverables

- `research/tournament/oc_amihudrobust/`: PLAN.md (this file), `amihud_signal.py`
  (parameterised Amihud XS signal, copied logic from oc_lit_xs, no edits there),
  `compute_robust_engine.py` (repro + frictions + jitters + static; heavy_slot),
  `analyze_placebo_coin.py` (500 placebos + per-coin decomp, vectorised proxy),
  `results.json`, `REPORT.md` (per-year tables, what failed, 3-line Vietnamese
  verdict: robust iff gain>0 under every friction AND all 4 jitters>G2 AND
  placebo pct>=90 AND beats static control, else not robust).
- `tests/test_oc_amihudrobust.py`: >=1 causality/truncation test + >=1
  hand-checked synthetic case; run `.venv/Scripts/python.exe -m pytest
  tests/test_oc_amihudrobust.py -q`. Stop when done.

## Post-hoc log

- (Filled after outcomes; no definition changes permitted without a disclosed
  extra row.)
