# oc_idea6 PLAN (pre-registered BEFORE any outcome is inspected)

Idea #6 of `research/tournament/oc_ideas/IDEAS.md`: basis-MOMENTUM dip
throttle (change in quarterly basis, not level). This file fixes the
hypothesis, exact causal definitions, the single variant, and the decision
rule. No outcome statistic (any y-column, any gain, any worst-day, any DD)
was inspected before writing it. Only counts/spans (fills row counts per
year 990/1045/1330/989/1144 from `harness5.load`, hourly/delivery file date
ranges, contract calendars) were read to write it.

## Hypothesis (fixed here)

`oc_qbasis` killed the LEVEL hypothesis (high basis -> BETTER book longs,
wrong-way sign 5/5). The economic object for crash risk is the CHANGE: a
fast basis collapse = de-leveraging impulse; dips bought into it face
follow-through. Direction pre-registered: when BTC front-quarterly
annualised basis has fallen fast over the last 24h (`mom` below its
walk-forward 20th percentile), dip bids are throttled x0.5 that bar
(market-wide, all 5 majors). Expected per IDEAS.md: return -0.2..0.0 pp/mo,
DD -0.5..-1.5 pp; a throttle, screened DD-first, but PROMISING only under
the full rule below (gain sign + LOYO + tail).

This differs from `oc_qbasis` (terciles on basis LEVEL/z90: FAIL, sign flips
or wrong way) and `v351 QB1` / `v352` (basis LEVEL as an ensemble member /
one-way control, DD 22.9/20.6, no transfer): momentum (impulse) vs level
(stock) - the level result does not pre-judge the change. Single
pre-registered cutoff (p20) and multiplier (x0.5); no threshold search, no
per-coin cut, no level interaction.

## Data (fixed here, all in repo - no fetch, LIGHT)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h boundaries,
  verified 100%). Outcome = y_dep only (exact net return at the DEPLOYED TP
  per rung from `research/parallel/rounds/parallel-20260906-r2/v376/
  tables_hidden/r2_table_s0.parquet` via `research/tournament/ext/
  harness5.py::load`; fees + adverse funding already inside; ~4-8 bps
  round-trip cost context). TP unchanged by this idea.
- Delivery 1h (the assignment's stated basis source):
  `data/raw/qbasis_20261003/cm_BTCUSD_*_1h.parquet` (26 contracts,
  first expiry 2020-09-25) + `um_BTCUSDT_*_1h.parquet` (25 contracts, first
  expiry 2021-03-26). Columns open_time (hour START UTC)/open/high/low/
  close/volume. Close-time of an hourly bar C = open_time + 1h.
  BTC legs only (IDEAS.md: SOL leg too short, unused; ETH leg unused here -
  the signal is BTC front-quarterly, market-wide).
- Perp reference (LIGHT, no 1m): `research/tournament/ext/hourly_ext.parquet`
  BTCUSDT hourly OHLC (t = hour START UTC, 2020-08-01..2026-09-23; close of
  hour C = row with t = C - 1h). This replaces the fetch script's 1m-derived
  perp hourly with the pre-aggregated hourly panel (same object: last traded
  perp price of the hour); no intraday-1m file is loaded.
- Market data up to 2026-09-24 00:00 UTC (= CUTOFF) may be read (assignment
  override; all five years are research data; any finding needs prospective
  validation). Any hourly/delivery bar with close_time >= CUTOFF is dropped
  and never used; fills with T >= CUTOFF are excluded (asserted zero).
- One process, delivery + hourly + fills frames only, RAM < 1 GB. One coin
  (BTC) in delivery memory at a time; per-expiry frames released after the
  asof join.

## Exact causal definitions (frozen)

Contract calendar (same as `scripts/fetch_quarterly_basis.py`, pure math,
no network): expiry E of a `_YYMMDD` suffix = 08:00 UTC on 20YY-MM-DD.
At each hourly close C, FRONT(C) = nearest expiry with E > C + 7 days
(roll 7 days before expiry). F(C) = close of the FRONT contract's 1h bar
with close_time <= C (merge_asof backward, strictly causal; both venues
pooled per expiry: UM preferred where its qb is available, else CM - see
annualisation step). P(C) = hourly_ext BTCUSDT close at C (NaN if missing).
`qb(C) = ln(F(C)/P(C)) * 365 / DTE`, DTE = (E - C) in days; NaN if
F/P non-positive/missing or DTE <= 0. Venue used at C is recorded
(`um` if the UM leg yields a finite qb, else `cm`, else `none`).

4h series: 4h closes at 00/04/08/12/16/20 UTC (date_range from midnight,
same phase as the fills T grid). `QB4(c4) = qb(C)` at the hourly C == c4
(NaN if that hourly row is missing). No interpolation, no fill-forward.

Per-bar signal (market-wide, one value per 4h bar open T):
`basis(T)` = QB4 at max 4h close c4 with c4 < T (STRICTLY before T; the
hourly bar ending exactly at T is never used). `mom(T)` = basis(T) -
basis(T - 24h), where basis(S) is the same strict rule at S; NaN if either
leg is NaN/missing. NaN mom -> multiplier 1.0 (neutral, never throttled).
Rolls: no roll adjustment - a mom window spanning a front roll keeps the
raw annualised difference (rolls ~quarterly, disclosed; sensitivity without
roll-spanning bars is descriptive only and NOT part of the rule).

Anchor years (5, assignment-literal): `Y_k = [A_k, A_k + 365d)` by T,
`A_k` in {2021-09-24 .. 2025-09-24} (UTC, literal +365 d).

Sequential cut-off per year k: `p20_seq(k)` = 20th percentile of `mom` over
the 4h GRID bars (all 4h opens from 2020-08-01 00:00 UTC, step 4h, anchored
00 UTC) with bar time < A_k and mom non-NaN (strictly previous data, full
history; bar-pool, each bar once - same pool convention as `oc_idea8`).
Require >= 100 training bars else p20 = NaN and the year is never
throttled (fail-safe; expected ~7k+ bars, never binds).

Flag (actionable at the bar open T, bot-executable): `THROTTLE(T) = 1`
iff mom(T) non-NaN and mom(T) < p20_seq(k) for the year k containing T
(strictly below; boundary ties stay unthrottled).

Multiplier (single pre-registered pair, exactly as IDEAS.md): per MAIN-R2
fill with bar open T: `m = 0.5` if THROTTLE(T) == 1 (ALL 5 majors,
market-wide, BTC included), else `1.0`. NaN mom -> 1.0.
`size_new = size_dep * m` (TP held at deployed). Scoring uses
`harness5.score` equal-exposure renormalisation per year
(`sn *= mean(sd)/mean(sn)`), so only TIMING is tested, not mean exposure.

LOYO cut-offs: for held-out year h, `p20_loyo(h)` = 20th percentile of mom
over grid bars inside the OTHER 4 anchor-year windows (union of Y_k,
k != h; mom non-NaN; >= 100 bars required). THROTTLE_loyo for rows in year
h uses p20_loyo(h); gain_h is computed with equal-exposure renormalisation
INSIDE the held-out year (same formula as harness5.score).

One variant only (p20 / x0.5 market-wide). No threshold search, no
venue/contract tweak, no ETH leg, no level interaction.

## Evaluation (fixed here - one variant only)

- Per anchor year (sequential cut-offs, renormalised sizes):
  `S_dep = sum(size_dep * y_dep)`, `S_new = sum(size_new_renorm * y_dep)`;
  `gain = S_new - S_dep`. PASS_gain(Y): gain > 0 (strict; NaN = FAIL).
- Worst day per year: daily sums of (size * y_dep) grouped by floor(T)
  calendar day UTC on the RENORMALISED sizes (same convention as
  harness5.score); W_dep = min, W_new = min. PASS_wd(Y): W_new >= W_dep
  (strictly not worse; NaN = FAIL).
- Yearly maxDD of the daily-sum path: within-year cumulative daily sums
  from 0; maxDD = min(cum - running max). D_dep, D_new per year.
  PASS_dd(Y): D_new >= D_dep (not deeper; NaN = FAIL). Tail PASS_tail(Y)
  = PASS_wd(Y) AND PASS_dd(Y) (the assignment's "worst-day / yearly maxDD"
  both guard; NaN = FAIL).
- LOYO per held-out year h: same gain construction with LOYO cut-offs;
  PASS_loyo(h): gain_h > 0 (NaN = FAIL).
- DECISION RULE (assignment default + throttle tail clause): PROMISING iff
  (a) PASS_gain in >= 4 of 5 sequential years, AND (b) PASS_loyo in >= 4 of
  5 held-out years, AND (c) PASS_tail in >= 4 of 5 sequential years.
  Otherwise NOT PROMISING. NaN/FAIL counts as a miss, never imputed.
- Reported per year (descriptive, NOT part of the rule): throttle share
  (fraction of fills with m = 0.5; overall), coverage (fraction of fills
  with non-NaN mom), per-coin gain split (same renormalised sizes),
  Spearman rho(mom, y_dep), raw (non-renormalised) sums + retention
  S_raw_new / S_raw_dep, full-path worst-day and maxDD of the cumulative
  daily sum (5 years concatenated chronologically), cut-off values +
  training-bar counts, venue (um/cm) share + roll dates spanned.
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native size*y_dep units.
- Path-effects caveat (from IDEAS.md): sleeve/budget path matters live;
  the rung-level equal-exposure screen is the cheap gate only - no engine
  run is claimed here.

## Causality / correctness tests (tests/test_oc_idea6.py)

- test_universe_counts: majors-R2 scored rows total 5498 with per-year T
  counts 990/1045/1330/989/1144; T = t_fill - f; T on 4h boundaries; no T
  at/after CUTOFF.
- test_basis_causal_truncate: 4 sampled T; mom recomputed from delivery +
  hourly truncated to close_time < T equals the stored value; no used bar
  has close_time >= T; no bar with close_time >= CUTOFF used; doubling any
  input close after T leaves mom(T) unchanged.
- test_mom_lag_synthetic: hand-built QB4 series -> mom(T) equals
  basis(T) - basis(T-24h) with strict-< sampling; NaN iff either leg NaN.
- test_cutoffs_causal: year-k p20 equals the < A_k grid-bar-pool 20th pct;
  LOYO p20 for one held-out year equals the other-4-windows pool 20th pct
  (held-out bars excluded); training pools use no bar at/after the anchor
  (sequential) resp. no bar of the held-out year (LOYO).
- test_multiplier_mapping: synthetic mom values map to {0.5, 1.0} at the
  exact boundary (< p20 -> 0.5 on every coin incl. BTC, == p20 -> 1.0;
  NaN -> 1.0).
- test_decision_counts_match: results.json pass counts recomputed from
  yearly passes equal the stored decision strings.
- test_gain_signs_match_harness: stored per-year gains/worst-days equal an
  independent harness5.score recomputation from stored features.
- test_no_1m_and_cutoff: the analysis script never references
  btc/majors/alts intraday 1m paths; max used delivery/hourly close_time
  < CUTOFF.

## Deliverables

`research/tournament/oc_idea6/`: PLAN.md (this file), `analyze_idea6.py`,
`features_idea6.parquet`, `results.json`, REPORT.md (tables + one-line
verdict). `tests/test_oc_idea6.py`. No commits, no edits outside these two
paths. One process, delivery-hourly + fills only, RAM < 1 GB. No tuning on
results; any post-hoc change logged in REPORT.md.

VF_COMMON note: `src/agentic_alpha_lab/patterns/common.py` was read. Its
compute/events/event_study contract targets BTC-bar feature studies; this
tournament screen follows the W assignment's rung-level screen instead
(fills_U_ext exact outcomes, 5 anchor years to 2026-09-24, harness5), while
honouring the shared causality principles: as-of availability (closes
strictly < T, windows ending before T), pre-anchor fits only, and no reads
beyond the 2026-09-24 cutoff.
