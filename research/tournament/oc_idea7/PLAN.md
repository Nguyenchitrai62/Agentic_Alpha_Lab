# oc_idea7 PLAN (pre-registered BEFORE any outcome is inspected)

Idea #7 of research/tournament/oc_ideas/IDEAS.md: VRP-regime dip BUDGET dial
(not per-rung sizing). Written before any outcome statistic is computed.

## Hypothesis (fixed here)

oc_dvol found VRP (DVOL minus 30d realised) IC positive 5/5 — fear
compensation predicts better dip-fill outcomes — but v414 tilted per-RUNG
size by DVOL and bought return with more DD (rejected). The clean use is the
opposite layer: the market-wide SLEEVE BUDGET, raised when compensation is
high and cut when it is not. Direction pre-registered: high VRP_z -> MORE
budget (x1.25), low VRP_z -> LESS budget (x0.75). PROMISING only under the
decision rule below (gain sign + worst-day, sequential and LOYO).

This differs from v414 (per-RUNG size tilt by DVOL level, varies by coin)
and from oc_corrbudget (uniform 1/(1+c) daily scaler): one market-wide
bar-level multiplier from VRP compensation (z-scored premium), renormalised
to equal exposure so only TIMING is scored.

## Data (fixed here, all in repo — no fetch, no newinfo_idea7)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries).
  Outcome = y_dep only (exact net return at the DEPLOYED TP per rung from
  `research/parallel/rounds/parallel-20260906-r2/v376/tables_hidden/
  r2_table_s0.parquet` via `research/tournament/ext/harness5.py::load`;
  fees + adverse funding already inside). TP unchanged by this idea.
- DVOL input: `research/tournament/oc_dvol/dvol_hourly.parquet`
  (t = bar START UTC, bar END = t + 1h; BTCDVOL/ETHDVOL 1h,
  2021-04-01 .. 2026-09-23 23:00 UTC; parsed from
  `data/raw/deribit_dvol_20261005/` + manifest, gap-free). BTC leg only.
- Realised input: `research/tournament/ext/hourly_ext.parquet` hourly closes
  (t = bar START UTC) for BTCUSDT only. No 1m data is loaded: the 30d
  realised window makes 1m vs 1h aggregation immaterial, and the assignment
  caps this LIGHT job at RAM < 1 GB / one process. (IDEAS.md says "+ 1m
  realised"; hourly aggregation is the pre-registered LIGHT equivalent, same
  definition as the validated oc_dvol vrp.)
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).

## Exact causal definitions (frozen)

As-of rule: an hourly bar (DVOL or price) with START t is usable at time U
iff its bar END (t + 1h) is strictly before U (`end < U`).

1. `dvol_asof(U)` = close of the last BTCDVOL hourly bar with END < U
   (NaN if none).
2. `rv30(U)` = 100 * std(30 daily log returns; ddof=1) * sqrt(365) (vol
   points, 365-day crypto annualisation). Daily close C(D) of BTCUSDT =
   close of the hourly bar starting D-1 23:00 UTC (bar END = D 00:00);
   usable iff C's bar END is strictly before U; take the last 31 usable
   closes -> 30 log returns; fewer than 31 -> NaN.
3. `prem(U)` = `dvol_asof(U)` - `rv30(U)` (NaN if either leg NaN).
4. `VRP_z(T)` = (`prem(T)` - mean(W)) / std(W, ddof=1), where W = up to 2160
   hourly asof samples `prem_asof(T - k*1h)`, k = 1..2160 (each with the
   same strictly-before rule at the lagged time); require >= 1728 non-NaN
   else NaN; std == 0 -> NaN. Unit: standard deviations. Market-wide: one
   value per bar T, applied to all 5 coins' rungs (sleeve BUDGET layer).
5. `FEAT_START` = 2021-06-30 UTC (~90d prem warm-up after DVOL start
   2021-04-01; same as oc_dvol). Rows with T < FEAT_START or NaN VRP_z get
   multiplier 1.0 (neutral); coverage reported per year (expected 100% in
   all 5 anchor years, which start 2021-09-24).
6. Budget multiplier (single pre-registered triple, exactly as IDEAS.md):
   m(T) = 1.25 if VRP_z(T) > q67, 0.75 if VRP_z(T) <= q33, else 1.0,
   where q33/q67 are walk-forward cut-offs (below). NaN VRP_z -> 1.0.
7. `size_new` = `size_dep` x m(T) per MAIN-R2 fill (TP held at deployed).
   Scoring uses `harness5.score` equal-exposure renormalisation per year
   (sn *= mean(sd)/mean(sn)), so only TIMING is tested, not mean exposure.

Cut-offs (walk-forward, causal):
- Sequential year k (anchor A_k in {2021-09-24 .. 2025-09-24}):
  training pool = MAIN-R2 fills with T < A_k AND T >= FEAT_START AND VRP_z
  non-NaN (strictly previous data only). Require >= 100 training rows else
  the year is NaN (FAIL). q33/q67 = 33rd/67th percentiles of training VRP_z.
- LOYO held-out year h: training = MAIN-R2 fills of the other 4 anchor
  years with VRP_z non-NaN (>= 100 required); cut-offs from that training;
  applied to the held-out year; gain_h computed with equal-exposure
  renormalisation INSIDE the held-out year.

Anchor years: Y_k = [A_k, A_k + 365d) by T, A in
{2021-09-24 .. 2025-09-24} (UTC).

## Evaluation (fixed here — one variant only)

- Per anchor year (sequential cut-offs): harness5-style S_dep =
  sum(size_dep * y_dep), S_new = sum(size_new_renorm * y_dep);
  gain = S_new - S_dep. PASS_gain(Y): gain > 0 (strict).
- Worst day per year: daily sums of (size * y_dep) grouped by floor(T to
  calendar day UTC) on the RENORMALISED sizes (same convention as
  harness5.score); W_dep = min, W_new = min. PASS_tail(Y): W_new >= W_dep
  (strictly not worse; both usually negative so "not worse" = less
  negative). NaN year = FAIL.
- LOYO per held-out year h: same gain construction with LOYO cut-offs;
  PASS_loyo(h): gain_h > 0.
- DECISION RULE (assignment default + sizing/filter tail clause):
  PROMISING iff (a) PASS_gain in >= 4 of 5 sequential years, AND
  (b) PASS_loyo in >= 4 of 5 held-out years, AND (c) PASS_tail in >= 4 of
  5 sequential years. Otherwise NOT PROMISING. NaN/FAIL counts as a miss,
  never imputed.
- Descriptive only (NOT part of the rule): raw (non-renormalised) sums and
  retention S_raw_new / S_raw_dep; multiplier shares (hi/mid/lo fractions)
  per year; Spearman rho(VRP_z, y_dep) per year; per-coin gain split.
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native units, also shown in bps x1e4.
- Path-effects caveat (from IDEAS.md): the budget path matters in a live
  engine (compounding, margin); the rung-level equal-exposure screen is the
  cheap gate only — no engine run is claimed here.

## Causality / alignment tests (tests/test_oc_idea7.py)

- test_vrpz_causal_truncate: 5 sampled T; VRP_z recomputed from panels
  truncated to bar END < T equals the stored value; no retained bar has
  END >= T.
- test_cutoffs_causal: year-1 cut-offs equal the previous-data-only pool
  quantiles; LOYO cut-offs for one held-out year equal the other-4-years
  pool quantiles (held-out rows excluded).
- test_multiplier_mapping: synthetic VRP_z values map to {0.75, 1.0, 1.25}
  at exact boundaries (<= q33 -> 0.75, > q67 -> 1.25, else 1.0; NaN -> 1.0).
- test_decision_counts_match: results.json counts recomputed from yearly
  passes equal the stored decision strings.
- test_T_and_bounds: T = t_fill - f; no fill with T >= 2026-09-24; no DVOL /
  hourly bar with START >= 2026-09-24 00:00 UTC used.
- test_universe_counts: majors-R2 join yields 6876 rows with
  ~990/1045/1330/989/1144 rows per anchor year.

## Deliverables

research/tournament/oc_idea7/: PLAN.md (this file), analyze_idea7.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_idea7.py. No commits, no edits outside these two paths. One
process, hourly data only, RAM < 1 GB.
