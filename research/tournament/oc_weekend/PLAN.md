# oc_weekend PLAN (pre-registered BEFORE any outcome is inspected)

Idea #18: weekend dip tilt. Written before any outcome statistic is computed.

## Hypothesis (fixed here)

Weekend flushes happen on thin books without macro news (liquidity-driven,
should mean-revert better); weekday flushes coincide with news / US hours.
Pre-registered direction: weekend dip fills have HIGHER mean net outcome than
weekday dip fills (weekend-minus-weekday spread > 0). The tradable use is a
fixed bar-level size tilt: weekend bars x1.25, weekday bars x0.90, renormalised
to equal total exposure per year so only TIMING is scored (same convention as
harness5.score). PROMISING only under the decision rule below.

This is a pure calendar-timing layer: no fitted parameter, no market-data
input beyond the bar-open timestamp T itself.

## Data (fixed here, all in repo)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23) loaded EXACTLY as `research/tournament/oc_idea7`
  does: `harness5.load()` (T = t_fill - f minutes, all T on 4h boundaries;
  majors-R2 rows joined to the deployed R2 table for size_dep / tp_dep;
  outcome = y_dep only = exact net return at the DEPLOYED TP per rung,
  fees + adverse funding already inside). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 (=k) in
  {2.5, 3.0, 3.5, 4.0, 5.0} with size_dep non-NaN (harness test rows).
- No other market data is loaded: no hourly, no 1m, no options/premium/DVOL,
  no bar_open_ext. The weekend flag needs only T. One process, RAM < 1 GB.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).

## Exact causal definitions (frozen)

As-of rule: the weekend flag of a fill is a pure function of its holding-bar
open T, known when the bid is placed. No future information enters.

1. `is_weekend(T)` = 1 iff Saturday 00:00 UTC <= T < Monday 00:00 UTC, i.e.
   `T.dayofweek in {5, 6}` (Monday=0, UTC). Boundaries: T exactly Saturday
   00:00 -> weekend; T exactly Monday 00:00 -> weekday. All T are 4h-aligned
   (00/04/08/12/16/20 UTC) so no ambiguous intra-day cut.
2. `m(T)` = 1.25 if is_weekend(T) else 0.90. Single fixed pair from the
   assignment (IDEAS.md #18). No fitting, no cut-offs, no NaN case (every T
   has a weekday).
3. `size_new` = `size_dep` x m(T) per MAIN-R2 fill (TP held at deployed).
   Scoring uses `harness5.score` equal-exposure renormalisation per anchor
   year (sn *= mean(sd)/mean(sn)), so only TIMING is tested, not mean
   exposure. Weekend share of fills is ~2/7 so raw exposure is slightly
   below base; the renorm removes that level effect.
4. Anchor years: Y_k = [A_k, A_k + 365d) by T, A in
   {2021-09-24 .. 2025-09-24} (UTC). Test rows = MAIN-R2 with size_dep
   non-NaN (same mask as harness.folds test mask).
5. Per-fill outcome for the spread: y_dep (native units per unit rung size).
   Per-year weekend stats (unweighted over fills, descriptive + rule input):
   n_wknd, n_wkday, mean_wknd = mean(y_dep | weekend), mean_wkday =
   mean(y_dep | weekday), spread = mean_wknd - mean_wkday (native units;
   also shown in bps x1e4), win_wknd = P(y_dep > 0 | weekend),
   win_wkday = P(y_dep > 0 | weekday).
6. Tilted vs base sums per year (renormalised, harness5 convention):
   S_dep = sum(size_dep * y_dep), S_new = sum(size_new_renorm * y_dep);
   gain = S_new - S_dep. PASS_gain is DESCRIPTIVE ONLY (not part of the
   rule; reported for context since the rule is written on the spread).
7. Worst day per year: daily sums of (size * y_dep) grouped by floor(T to
   calendar day UTC) on the RENORMALISED sizes (same convention as
   harness5.score); W_dep = min, W_new = min. PASS_tail(Y): W_new >= W_dep
   (strictly not worse; both usually negative so "not worse" = less
   negative).
8. MaxDD of daily-sum path per year (descriptive): sort fill-days D in Y
   ascending; daily sums d(D) (renormalised sizes); cumulative path
   P_t = cumsum(d); running peak M_t = max_{s<=t} P_s (with P_0 = 0
   included); DD_t = M_t - P_t; maxDD = max_t DD_t (>= 0, native units).
   Reported for dep and new (renormalised). Path-effects caveat: the tilt
   changes compounding/margin live; this rung-level screen is the cheap
   gate only.
9. LOYO (no fitted parameter, so stability form, frozen): for held-out year
   h, pooled spread over the OTHER 4 anchor years =
   mean(y_dep | weekend, Y_k k!=h) - mean(y_dep | weekday, Y_k k!=h)
   (unweighted fills). PASS_loyo(h): pooled spread > 0 (strict). Tests
   whether the sign survives dropping any single year.

Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse funding;
sums in native units, also shown in bps x1e4 for the spread.

## Evaluation (fixed here — one variant only)

- PASS_spread(Y_k): spread(Y_k) > 0 (strict). NaN (empty bucket, never
  expected: each year has ~2/7 weekend fills) = FAIL.
- PASS_loyo(h): pooled spread of the other 4 years > 0 (strict).
- PASS_tail(Y_k): W_new >= W_dep (strictly not worse).
- DECISION RULE (assignment default + tail clause): PROMISING iff
  (a) PASS_spread in >= 4 of 5 sequential anchor years, AND
  (b) PASS_loyo in >= 4 of 5 held-out pools, AND
  (c) PASS_tail in >= 4 of 5 sequential years. Otherwise NOT PROMISING.
  NaN/FAIL counts as a miss, never imputed.
- Descriptive only (NOT part of the rule): per-year gain (tilted vs base),
  raw (non-renormalised) sums and retention S_raw_new / S_raw_dep,
  weekend fill share, maxDD dep vs new, per-coin spread split.

## Causality / alignment tests (tests/test_oc_weekend.py)

- test_weekend_flag_boundaries: synthetic T at Sat 00:00 -> weekend, Mon
  00:00 -> weekday, Fri 20:00 -> weekday, Sun 12:00 -> weekend, Tue 04:00
  -> weekday; vectorised helper matches row-wise weekday computation.
- test_T_and_bounds: T = t_fill - f minutes; no fill with T >= 2026-09-24
  00:00 UTC; analysis uses only MAIN-R2 rows with size_dep non-NaN.
- test_decision_counts_match: results.json (a)/(b)/(c) counts recomputed
  from yearly passes equal the stored decision strings; promising flag
  matches the AND rule.
- test_gain_signs_match_harness: stored per-year gains and worst days equal
  an independent harness5.score recomputation from size_dep * m(T).
- test_spread_recompute: stored per-year spread/mean/win/n equal an
  independent recomputation from fills (weekend mask from T.dayofweek).
- test_loyo_recompute: stored LOYO pooled spreads equal recomputation from
  the other-4-years pool; pass flags match sign.

## Deliverables

research/tournament/oc_weekend/: PLAN.md (this file), analyze_weekend.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_weekend.py. No commits, no edits outside these two paths. One
process, no hourly/1m loaded, RAM < 1 GB.
