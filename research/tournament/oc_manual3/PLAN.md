# oc_manual3 PLAN (pre-registered BEFORE any outcome is inspected)

Idea #15: STATIC placement-time proxy for the BOT's correlation-aware dip
sizing B1 (v399). A human places orders once per 4h bar and cannot amend
resting bid sizes minute by minute, so the dynamic rule (shrink a rung when
other majors flush in the same minute) is not MANUAL-compatible. This study
tests whether a static per-(coin, depth) haircut recovers a useful share of
the dynamic rule's drawdown reduction.

## Hypothesis (fixed here)

At the fill minute f of a rung of coin c, v399-B1 sizes x 1/(1+n) where n =
other majors already flushed. The static proxy sizes the rung of (coin c,
depth d) x m(c,d), where m(c,d) is the walk-forward mean of 1/(1+n) over
historical fills of (c,d) — a placement-time constant a human can apply when
the bid is placed. Direction pre-registered: the static proxy recovers a
material share (>= 50%) of the dynamic rule's maxDD reduction vs no sizing,
year by year. PROMISING only under the decision rule below.

This differs from oc_corrbudget (market-wide daily 1/(1+c) scaler on y1.0)
and oc_idea7 (VRP budget dial): per-(coin, depth) static haircut, outcome
y_dep, maxDD of the daily-sum path as the target.

## Data (fixed here, all in repo — no fetch)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23) loaded via `research/tournament/ext/harness5.py::load`
  (T = t_fill - f minutes, all T on 4h boundaries; k = x1; deployed
  size_dep/tp_dep from v376/r2_table_s0; outcome y_dep = exact net return at
  the DEPLOYED TP per rung; fees + adverse funding already inside).
- Universe TEST = majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2
  depths k in {2.5, 3.0, 3.5, 4.0, 5.0} with size_dep non-NaN (expected
  5498 rows; per anchor year 990/1045/1330/989/1144 as in oc_idea7).
- Training pool for m(c,d) = majors x R2 grid fills (x1 in R2, size_dep NOT
  required) — expected 6876 rows; per-anchor history with
  t_fill strictly < anchor - 7 days (expected 1345/2335/3401/4743/5704).
- 1m klines (this assignment explicitly permits 1m one coin at a time):
  BTC from `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`,
  others from `data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet`
  (columns open_time/open/close). No per-fill n is reused from v399
  (v399_runs.pkl stores only equity paths, no per-fill n) — n is recomputed
  from 1m exactly as v399 does (definitions below). No DVOL/options/premium
  data. One process, 1m read one coin-year at a time, RAM < 1 GB.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).

## Exact causal definitions (frozen)

Bar open T = t_fill - f minutes (4h boundary, UTC). Fill minute f in
16..238 in this universe; guard: f <= 0 -> n = 0.

1. `O_b(T)` = 1m open of coin b with open_time == T (exact bar-open minute;
   NaN if that minute is missing; NO ffill for minute 0, as in the engine
   cube). Known at placement time T.
2. `C_b(T,f)` = 1m close of coin b with open_time == T + (f-1) minutes; if
   that minute is missing, the last available 1m close with open_time in
   [T, T+(f-1)] (engine within-bar ffill); NaN if none. Uses fill-minute
   data (bot_only, exactly as v399).
3. `sig_b(T)` = sig4 of coin b at bar T: 4h bar-open series o_b(G) = 1m open
   at each 4h boundary G (2020-06-01 .. 2026-09-24), then
   sig = o.pct_change().rolling(360, min_periods=120).std() evaluated at G
   = T (same formula as forward_v205.build_prep / engine_user.prepare with
   60*PD = 360; uses opens up to and including T, all known at T). NaN until
   120 bar returns exist.
4. `n` per fill of coin c at (T,f), EXACTLY as v399_corr_dip_size.corr_size
   with rule "inv": n = #{other majors b != c with finite O_b, C_b, sig_b
   AND C_b <= O_b * (1 - 2.5 * sig_b)}. NaN-sig / NaN-price coins are
   skipped (never counted). `mult_dyn` = 1/(1+n) in {1, 1/2, 1/3, 1/4, 1/5}.
5. Static proxy for test year Y with anchor A = anchor(Y):
   training = majors x R2 grid fills with t_fill strictly < A - 7 days
   (fill-time embargo; n is a fill-time quantity). m(c,d) = mean of
   mult_dyn over training fills with sym == c AND x1 == d; if fewer than 30
   such fills, pooled mean over training fills with x1 == d across the 5
   majors; if still fewer than 30, m = 1.0 (neutral). m depends only on
   pre-anchor history -> placeable at bar open T (MANUAL-compatible).
   Depth d = x1 (fill grid depth; equals k on R2 rows).
6. Arms (per TEST fill): (a) no sizing: size_a = size_dep; (b) static:
   size_b_raw = size_dep * m(c,d); (c) dynamic B1 BOT reference:
   size_c_raw = size_dep * mult_dyn. TP held at deployed (y_dep unchanged).
7. Equal total exposure per anchor year (same convention as
   harness5.score): within year Y, s_b = size_b_raw * mean(size_a)/mean
   (size_b_raw), s_c = size_c_raw * mean(size_a)/mean(size_c_raw); (a)
   unchanged. Only ALLOCATION is tested, not mean exposure.
8. Daily sums per arm per year: group by D = floor(T to calendar day UTC);
   s(D) = sum(size_renorm * y_dep) over the year's fills on day D.
   Yearly sum S = sum s(D). Worst day W = min s(D) (descriptive only).
   Cumulative path over fill-days sorted ascending: C_0 = 0,
   C_k = cumsum(s); maxDD = max(0, max_{p<q}(C_p - C_q)) in native
   size*y_dep units (0 when monotone non-decreasing). Zero-fill calendar
   days contribute 0 and cannot change peak/trough values.

Anchor years: Y_k = [A_k, A_k + 365d) by T,
A in {2021-09-24 .. 2025-09-24} (UTC).

## Evaluation (fixed here — one comparison only)

- Per year Y: DD_a, DD_b, DD_c (maxDD as above, all on renormalised sizes).
  Reduction_dyn = DD_a - DD_c; Reduction_stat = DD_a - DD_b;
  recovery(Y) = Reduction_stat / Reduction_dyn.
  PASS(Y) iff Reduction_dyn > 1e-12 (dynamic actually reduces DD) AND
  recovery(Y) >= 0.50. Denominator <= 1e-12 -> FAIL (no reduction to
  recover); NaN year -> FAIL, never imputed.
- DECISION RULE (idea-specific sentence of the assignment, which supersedes
  the generic sign/LOYO template for this task): PROMISING iff PASS(Y) in
  >= 4 of 5 anchor years. Otherwise NOT PROMISING. The generic
  same-sign-4/5 + LOYO-4/5 template is not applied here: m(c,d) is already
  strictly walk-forward sequential, and a LOYO screen would train the
  "static" constant on future years, breaking the placement-time causality
  this idea exists to test.
- Descriptive only (NOT part of the rule): per-year S and W per arm;
  distribution of n (share n = 0/1/2/3/4); m(c,d) table per year (25 cells
  + pooled fallbacks used); mean y_dep by n bucket.
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native units, also shown x1e4 as bps-sum for reference.
- Path-effects caveat: the rung-level equal-exposure screen is the cheap
  gate only — compounding/margin paths matter live and no engine run is
  claimed here.

## Causality / alignment tests (tests/test_oc_manual3.py)

- test_n_matches_v399_definition: synthetic opens/closes/sig4 frame ->
  hand-computed n and 1/(1+n) (flush at exactly 2.5 sigma counts;
  NaN sig skipped; own coin never counted).
- test_static_embargo: training pool for one anchor excludes every fill
  with t_fill >= anchor - 7d; m(c,d) cell equals the pool mean; a cell with
  < 30 fills equals the pooled depth mean.
- test_renorm_equal_exposure: per year mean(s_b) == mean(s_a) and
  mean(s_c) == mean(s_a) after renormalisation (approx).
- test_decision_counts_match: results.json PASS count recomputed from
  yearly DD values equals the stored decision string.
- test_T_and_bounds: T = t_fill - f; no fill with T >= 2026-09-24; no 1m
  bar with open_time >= 2026-09-24 00:00 UTC used; all 1m reads are
  single-coin files.
- test_universe_counts: TEST years n == [990, 1045, 1330, 989, 1144].

## Deliverables

research/tournament/oc_manual3/: PLAN.md (this file), analyze_manual3.py,
n_per_fill.parquet (n + mult per majors-R2 grid fill, 6876 rows),
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_manual3.py. No commits, no edits outside these two paths.
One process, 1m one coin(-year) at a time, RAM < 1 GB.
