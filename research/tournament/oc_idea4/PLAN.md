# oc_idea4 PLAN (pre-registered BEFORE any outcome is computed)

Idea #4 of `research/tournament/oc_ideas/IDEAS.md`: funding-surprise dip
filter (actual minus predicted, not level). This file fixes the hypothesis,
exact causal definitions, variants, and decision rule. No outcome statistic
(y-column) was inspected before writing it.

## Question

Does an unsettled-crowding SURPRISE event observed strictly before the 4h bar
open T separate bad from good dip-rung fills, so that skipping (or scaling
down) dip bids in the surprised coin improves the tail without giving up more
than 5% of the yearly sum?

## Hypothesis (fixed here)

A large positive funding surprise (settled funding above what was predicted
just before the settlement = longs more crowded than priced) marks a flush
that is more likely to extend past the resting bids. Dip fills whose coin is
flagged at T have LOWER mean y1.0 than unflagged fills. Expected sign of the
primary spread (flagged minus kept) is NEGATIVE. Consistency across anchor
years is what matters (rule below).

## Data (fixed here, read-only, LIGHT)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0} (~6876 rows; per-year T-counts ~990/1045/1330/
  989/1144 from counts only, no outcomes inspected). T = t_fill - f minutes
  (all T on 4h boundaries). Outcome = y1.0 only (exact net return at TP 1.0
  sigma, unit rung size; y0.5/y1.5 NOT scored). Reported in bps (1 bps = 1e-4);
  round-trip cost ~4-8 bps.
- Funding + premium: `data/raw/binance_premium_20260928/` (in repo):
  `{SYM}_funding.parquet` (calc_time, funding_interval_hours,
  last_funding_rate; settlements 00/08/16 UTC, 8h; spans 2020-01..2026-08-31
  16:00 UTC) and `{SYM}_premium_1m.parquet` (open_time, open/high/low/close;
  close = premium index in decimal). No other 1m data is loaded (no
  majors/btc/alts intraday klines). One process, RAM < 1 GB (premium loaded
  one coin at a time, close column only).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data, any finding
  needs prospective validation). Premium bars starting at/after 2026-09-24
  00:00 UTC are dropped; no data beyond the cutoff is read.
- Predicted-funding note (disclosed BEFORE the run): Binance public bulk data
  (`data.binance.vision` fundingRate) archives SETTLED rates only (8h rows);
  the REST API serves settled history plus the CURRENT predicted rate, but no
  free public endpoint serves a historical per-minute predicted-funding
  series. There is therefore nothing to fetch into `data/raw/newinfo_idea4/`
  (no fetch is performed). The predicted leg is operationalised from the
  archived series the idea names in the same folder: the premium index 1m is
  the per-minute published crowding input from which predicted funding is
  computed, so the last-hour premium TWAP before a settlement is the
  market-priced expectation at that point (V1, primary). A settled-innovation
  variant that needs no premium scaling is pre-registered as robustness (V2).
  Both are causal, per-coin, walk-forward, and fixed here.

## Surprise definitions (exact, causal)

Let S run over a coin's funding-file rows (settlements; S wall time =
calc_time, kept with its ms offset). S_floor = S floored to the minute
(settlements print at 00/08/16:00 + ms, so S_floor is the exact hour).

V1 (primary, settled-minus-premium): P_c(S) = mean premium-1m close over the
60 bars with open_time in [S_floor - 60m, S_floor - 1m] (bar ENDs in
(S_floor - 60m, S_floor], all <= S). Require >= 30 valid bars else NaN (no
imputation). surprise1_c(S) = settled_c(S) - P_c(S) (decimal rate points).

V2 (robustness, settled innovation): surprise2_c(S) = settled_c(S) -
settled_c(S_prev), where S_prev is the coin's previous funding-file row (any
interval; the SOL Nov-2022 4h/2h rows are used as listed, no 21-count rule).
First row per coin = NaN.

At bar open T (4h boundary), per coin c: S*(c,T) = max settlement with
calc_time < T (STRICTLY before T; never the settlement at T). surprise_c(T) =
surprise at S*(c,T); NaN if no S < T, or the surprise leg is NaN. The flag
uses only information published before T (bar-open knowledge; NOT bot_only).

## Thresholds and flags (exact, walk-forward, per-coin)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC, literal +365d per assignment).
- Per year k, per coin c, per variant: threshold p80_c,k = 80th percentile of
  surprise_c(T) over DIP ROWS of coin c with T < A_k and surprise non-NaN
  (row-weighted; strictly previous data, all history back to the coin's first
  settlement). Require >= 100 training rows per coin else p80 = NaN and the
  coin is NEVER flagged that year (fail-safe, disclosed).
- Flag: SKIP_c(T) = 1 iff surprise non-NaN and surprise_c(T) > p80_c,k
  (strictly greater); NaN surprise or NaN threshold -> 0. A fill row is
  flagged iff its own coin is flagged at its T. Single pre-registered cutoff
  (80th pct); no tuning.
- Variants (2, fixed): V1_SKIP = skip rows flagged by V1 surprise (PRIMARY);
  V2_SKIP = skip rows flagged by V2 surprise (robustness, same rule). A x0.5
  scale-down (kept + 0.5 * flagged) is reported as descriptive accounting for
  V1 only, not a scored variant.

## Evaluation (fixed here)

Per anchor year, per variant: n, n_flag, n_kept; retention = n_kept / n;
mean y1.0 flagged/kept (bps) + win rates (y1.0 > 0) + min y1.0 (bps);
spread = mean_flagged - mean_kept (bps; NEGATIVE expected = flagged worse).
Minimum-n: a year's spread is valid only if n_flag >= 10 AND n_kept >= 10,
else NaN = FAIL for the sign count (oc_macro precedent; never imputed).
Skip simulation per year (unit rung size): S_full = sum y1.0; S_skip = sum
kept; S_half = S_kept + 0.5 * S_flagged; cut = (S_full - S_skip) / S_full
(NaN if S_full <= 0); daily sums grouped by T floor('D'): worst_day_full,
worst_day_skip; tail_improves = worst_day_skip > worst_day_full.
LOYO: for held-out year h, per-coin p80 fit on rows of the OTHER 4 anchor
years (surprise non-NaN; no row of year h); spread_h in the held-out year;
pooled_other4 = flagged-minus-kept mean over the other 4 years pooled (NaN
if either side < 10 rows); agree_h = sign(spread_h) == sign(pooled_other4),
both nonzero (NaN = fail).
DECISION RULE (assignment default + filter bar, per variant, on spread):
PROMISING iff (a) spread has the expected NEGATIVE sign in >= 4 of 5 anchor
years (NaN = fail), AND (b) LOYO spread is negative in >= 4 of 5 held-out
years (NaN = fail), AND (c) worst_day_skip >= worst_day_full in >= 4 of 5
years. The idea's retention screen (retention >= 95% per year) is REPORTED per
year for both variants but is not part of the PROMISING rule (note: a p80
cutoff flags ~20% of coin-time by construction, so retention near ~80% is
the expected null, not a failure of the sign rule; the tail bar (c) governs).
OVERALL verdict follows the PRIMARY variant V1; V2 is robustness context.

## Causality / correctness tests (tests/test_oc_idea4.py)

- test_universe_counts: majors-R2 join yields 6876 rows, T on 4h boundaries,
  per-year T counts 990/1045/1330/989/1144; no T at/after 2026-09-24.
- test_surprise_strictly_before_T: on sampled T, S*(c,T) < T for every coin;
  every premium bar used ends <= S* < T; truncating all funding+premium data
  at T leaves surprise_c(T) unchanged (recompute on sampled T).
- test_cutoffs_causal: year-k p80 uses no row with T >= A_k; LOYO p80 for
  held-out h uses no row of year h (per-coin).
- test_no_intraday_1m: the analysis script never references
  majors/btc/alts intraday kline paths (premium_1m from the stated folder is
  the only 1m data loaded) or premium bars starting at/after 2026-09-24
  (source scan + premium span assertion).
- test_skip_recompute_no_outcome: flags recomputed from T + surprise table
  after dropping all y-columns are identical (flags carry no outcome info).

## Deliverables

research/tournament/oc_idea4/: PLAN.md (this file), analyze_idea4.py,
results.json, REPORT.md (tables + one-line verdict). tests/test_oc_idea4.py.
One process, RAM < 1 GB. No tuning on results; any post-hoc change logged in
REPORT.md. No commits, no edits outside the two allowed paths.

VF_COMMON note: `src/agentic_alpha_lab/patterns/common.py` was read. Its
compute/events/event_study contract targets BTC-bar feature studies; this
tournament screen follows the W assignment's rung-level screen instead
(fills_U_ext exact outcomes, 5 anchor years to 2026-09-24), while honouring
the shared causality principles: as-of availability (strict < T joins),
pre-anchor fits only, and no reads beyond the 2026-09-24 cutoff.
