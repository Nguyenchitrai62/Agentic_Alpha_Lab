# oc_b1btc PLAN (pre-registered BEFORE any outcome is inspected)

Idea #20: BTC-weighted correlation count for B1 (v399 B1 variant).

## Hypothesis (fixed here)

v399-B1 sizes each dip rung at its fill minute f by 1/(1+n), where n = number
of OTHER majors jointly flushed at minute f-1. Hypothesis: a flush that
includes BTC is market-wide (leader-driven, follow-through / weak bounce)
while an alt-only flush is idiosyncratic (better bounce). Direction
pre-registered: extra shrink when BTC is among the flushing others improves
the yearly sum at no worse tail, i.e. B1-BTC beats B1. Fixed rule (no fitted
parameters): n_btc = n + 1 if BTC is among the flushing others (a != BTC),
else n; size x 1/(1+n_btc). For BTC's own rungs nothing changes
(n_btc = n). PROMISING only under the decision rule below.

This differs from oc_b1shape S3 (same n_w formula, but y1.0 flat weights) and
from oc_manual3 (static placement-time proxy): here the BOT-exact dynamic
comparison B1 vs B1-BTC on y_dep with deployed size_dep weights.

## Data (fixed here, all in repo — no fetch)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23) loaded via `research/tournament/ext/harness5.py::load`
  (T = t_fill - f minutes, all T on 4h boundaries; k = x1; deployed
  size_dep/tp_dep from v376/r2_table_s0; outcome y_dep = exact net return at
  the DEPLOYED TP per rung; fees + adverse funding already inside).
- Universe TEST = majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2
  depths k in {2.5, 3.0, 3.5, 4.0, 5.0} with size_dep non-NaN (expected 5498
  rows; per anchor year 990/1045/1330/989/1144 as in oc_idea7/oc_manual3).
- n source: REUSE per-fill n of `research/tournament/oc_manual3/
  n_per_fill.parquet` (6876 majors-R2 grid rows, recomputed exactly as v399;
  oc_manual3 REPORT documents: C[f-1] <= O[0] x (1 - 2.5 sig4), sig4 = 4h-open
  pct_change rolling(360,min120).std, O = 1m open at T no ffill, C = 1m close
  at T+f-1 with within-bar ffill). Join to TEST on
  (sym, x1, T, t_fill, f); assert full coverage and n in 0..4. No per-fill n
  is recomputed from scratch.
- btc_det source: recomputed EXACTLY as v399 for the BTC leg only (this
  assignment explicitly permits 1m one coin at a time): BTC 1m from
  `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`, one yearly file in
  RAM at a time, minutes strictly < 2026-09-24 00:00 UTC. O_BTC(T) = 1m open
  at minute T (no ffill); C_BTC(T,f) = 1m close at T+(f-1), else last
  available close in [T, T+(f-1)] (within-bar ffill); sig_BTC(T) = std of
  4h-open simple returns trailing 360 ending at T (min 120, else NaN) over
  opens at 4h boundaries 2020-06-01..2026-09-24. btc_det = 1 iff sym != BTC
  AND O/C/sig all finite AND C <= O x (1 - 2.5 x sig), else 0. BTC's own
  fills always 0. Descriptive cross-check vs oc_b1shape fills_n.parquet
  btc_det (no-ffill variant) reported as agreement rate only.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation). One process, RAM < 1 GB.

## Exact causal definitions (frozen)

Bar open T = t_fill - f minutes (4h boundary, UTC). Fill minute f in
16..238 in this universe; guard: f <= 0 -> n = stored n (no recompute),
btc_det = 0.

1. `n` per fill = stored oc_manual3 n (0..4, # other majors flushing by the
   v399 2.5-sigma rule). Own coin never counted (by construction).
2. `btc_det` per fill of coin a at (T,f): BTC-leg 2.5-sigma detection exactly
   as v399_corr_dip_size.corr_size applies to b = BTC (finite O/C/sig,
   sig > 0 required; NaN -> 0; flush at exactly 2.5 sigma counts, <=).
   For a == BTCUSDT, btc_det = 0 by definition.
3. `n_btc` = n + btc_det for a != BTC; n_btc = n for a == BTC (range 0..5).
4. Arms per TEST fill (TP held at deployed, y_dep unchanged):
   (a) B1: size_a_raw = size_dep x 1/(1+n);
   (b) B1-BTC: size_b_raw = size_dep x 1/(1+n_btc).
5. Equal total exposure per anchor year (same convention as harness5.score
   and oc_manual3): within year Y, s_a = size_a_raw x mean(size_dep) /
   mean(size_a_raw), s_b = size_b_raw x mean(size_dep) / mean(size_b_raw).
   Only ALLOCATION is tested, not mean exposure.
6. Daily sums per arm per year: group by D = floor(T to calendar day UTC);
   s(D) = sum(size_renorm x y_dep) over the year's fills on day D. Yearly
   sum S = sum s(D). Worst day W = min s(D) (reported; NOT part of the
   rule except descriptively). Cumulative path over fill-days sorted
   ascending: C_0 = 0, C_k = cumsum(s); maxDD = max(0, max_{p<q}(C_p - C_q))
   in native size*y_dep units (0 when monotone non-decreasing). Zero-fill
   calendar days contribute 0 and cannot change peak/trough values.
7. Win-rate split (descriptive, NOT part of the rule): per year over TEST
   fills, fraction with y_dep > 0 (strict) and mean y_dep (bps) for:
   BTC-flush = non-BTC fills with btc_det == 1; alt-only = non-BTC fills
   with n >= 1 AND btc_det == 0; isolated = non-BTC fills with n == 0;
   BTC-own = BTC fills (n_btc == n). Hypothesis support expects
   BTC-flush <= alt-only (worse outcomes where the extra shrink lands).

Anchor years: Y_k = [A_k, A_k + 365d) by T,
A in {2021-09-24 .. 2025-09-24} (UTC).

## Evaluation (fixed here — one comparison only)

- Per year Y: S_a, S_b (renormalised), gain(Y) = S_b - S_a.
  PASS_gain(Y) iff gain(Y) > 0 (strict). NaN -> FAIL.
- LOYO stability (no parameters are fitted, so LOYO is a robustness check,
  not a refit): for held-out year h, LOYO_gain(h) = mean gain(Y) over the
  other 4 years. PASS_loyo(h) iff LOYO_gain(h) > 0 (strict).
- Tail: DD_a, DD_b per year (maxDD as above, renormalised sizes).
  PASS_dd(Y) iff DD_b <= DD_a (strictly not worse; equal passes since extra
  shrink doing nothing is not harm). NaN -> FAIL.
- DECISION RULE (assignment default + maxDD clause): PROMISING iff
  (a) PASS_gain in >= 4 of 5 anchor years, AND
  (b) PASS_loyo in >= 4 of 5 held-out years, AND
  (c) PASS_dd in >= 4 of 5 anchor years. Otherwise NOT PROMISING.
- Descriptive only (NOT part of the rule): per-year W_a/W_b; n histogram;
  btc_det share per year (non-BTC fills); agreement rate of exact btc_det
  vs oc_b1shape btc_det; per-bucket win rate + mean y_dep (bps);
  full-path maxDD of concatenated daily sums (reference only).
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native units, also shown x1e4 as bps-sum for reference.
- Path-effects caveat: the rung-level equal-exposure screen is the cheap
  gate only — compounding/margin paths matter live and no engine run is
  claimed here.

## Causality / alignment tests (tests/test_oc_b1btc.py)

- test_btc_det_matches_v399_definition: synthetic O/C/sig frame ->
  hand-computed btc_det (flush at exactly 2.5 sigma counts; NaN sig -> 0;
  sig <= 0 -> 0; BTC own fills always 0; n_btc = n + btc_det).
- test_n_reuse_join: every TEST row joins exactly one stored n row;
  n in 0..4; n_btc in 0..5; btc_det == 0 for all BTC fills;
  btc_det <= n for non-BTC fills is NOT asserted (different legs), but
  violation count is reported (must be 0 for exact consistency).
- test_renorm_equal_exposure: per year mean(s_a) == mean(size_dep) and
  mean(s_b) == mean(size_dep) after renormalisation (approx).
- test_decision_counts_match: results.json pass counts recomputed from
  yearly gain/DD values equal the stored decision strings.
- test_T_and_bounds: T = t_fill - f; no fill with T >= 2026-09-24; no 1m bar
  with open_time >= 2026-09-24 00:00 UTC read; only BTC 1m files read.
- test_universe_counts: TEST years n == [990, 1045, 1330, 989, 1144].

## Deliverables

research/tournament/oc_b1btc/: PLAN.md (this file), analyze_b1btc.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_b1btc.py. No commits, no edits outside these two paths. One
process, BTC 1m one yearly file at a time, RAM < 1 GB.
