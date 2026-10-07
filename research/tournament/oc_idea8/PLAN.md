# oc_idea8 PLAN (pre-registered BEFORE any outcome is inspected)

Idea #8 of `research/tournament/oc_ideas/IDEAS.md`: dominance-momentum dip
throttle (alt-capitulation flow, not level). This file fixes the hypothesis,
exact causal definitions, the single variant, and the decision rule. No
outcome statistic (any y-column, any gain, any worst-day) was inspected
before writing it.

## Hypothesis (fixed here)

When BTC dominance is SURGING (alts in capitulation), alt-dip bids catch
falling knives; when dominance is stable, the ladder is safe. The tradable
object is FLOW (`ddom`), not level (`dom30`): `oc_dombook` scaled the book by
`dom30` LEVEL terciles and added return every year but deepened DD in
2021/2024 (extra size met the worst slides); `oc_ethbtc` sorted outcomes by
`dom30` LEVEL and is fragile (rests on +0.02 bps/bar 2021). Momentum (flow)
applied to ALT DIPS (not the book) is the untested cell.

Direction pre-registered: high `ddom` -> LESS alt-dip exposure (x0.5 on
ETH/SOL/BNB/XRP rungs that bar, BTC unchanged). Expected per IDEAS.md:
return -0.1..+0.2 pp/mo, DD -0.3..-1.0 pp (FTX-type alt cascades throttled);
a throttle, screened DD-first but PROMISING only under the full rule below
(gain sign + LOYO + tail).

This differs from `oc_dombook` (book weights x LEVEL terciles),
`oc_ethbtc` (outcomes sorted by LEVEL), `v351/v352` (basis members), and
`v414` (per-rung size tilt by DVOL): market-wide FLOW gate on ALT DIP bids
only, single pre-registered cutoff, no per-coin distance/size change.

## Data (fixed here, all in repo - no fetch, LIGHT)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (35 coins,
  2020-08..2026-09-23). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (all T on 4h
  boundaries). Outcome = y_dep only (exact net return at the DEPLOYED TP per
  rung from `research/parallel/rounds/parallel-20260906-r2/v376/
  tables_hidden/r2_table_s0.parquet` via `research/tournament/ext/
  harness5.py::load`; fees + adverse funding already inside; ~4-8 bps
  round-trip cost context). TP unchanged by this idea.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  BNB/BTC/ETH/SOL/XRP, 2017-08..2026-09-24; the canonical full-history opens
  used by the `oc_dombook` fix; `data/raw/spot_majors_20260925` is the same
  opens family and is NOT loaded separately). Opens ONLY - no 1m, no hourly,
  no funding, no options, no premium data is loaded.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation). Opens bars at/after 2026-09-24 00:00 UTC are dropped and never
  used; fills with T >= 2026-09-24 are excluded (asserted zero).
- One process, two small frames (opens + fills), RAM < 1 GB.

## Exact causal definitions (frozen)

Grid: full opens history sorted ascending (tz-aware UTC), restricted to bars
with time < CUTOFF = 2026-09-24 00:00 UTC. All formulas use rows with index
<= T only (causal).

1. `dom30[t] = log(O_BTC[t]/O_BTC[t-180]) - mean_s log(O_s[t]/O_s[t-180])`
   over the 5 majors (180 bars = 30 d at 6 bars/day), computed on the FULL
   opens history with index <= t only (NaN until the 180-bar lag is
   available). Identical math to `oc_dombook::compute_dom30` (pandas
   `log(o / o.shift(180))`, equal-weight mean skips NaN for early-alts bars;
   no change).
2. `ddom[T] = dom30[T] - dom30[T-42bars]`, where `T-42bars` is the full-grid
   position 42 bars before T (42 x 4h = 168 h = 7 d, the idea-literal
   `dom30(T-7d)` on the 4h grid). NaN if either leg is NaN or fewer than 42
   prior grid bars exist. Market-wide: one value per bar T (same for all 5
   coins). NaN `ddom` -> multiplier 1.0 (neutral, never throttled).
3. Anchor years (5, assignment-literal): `Y_k = [A_k, A_k + 365d)` by T,
   `A_k` in {2021-09-24 .. 2025-09-24} (UTC, literal +365 d).
4. Sequential cut-off per year k: `q67_seq(k)` = 67th percentile of `ddom`
   over full-opens-history grid bars with time < A_k and `ddom` non-NaN
   (strictly previous data, all history back to 2017; bars, not fills -
   same pool convention as `oc_dombook` hist). Require >= 100 training bars
   else `q67 = NaN` and the year is never throttled (fail-safe; expected
   ~8k+ bars, never binds).
5. Flag (actionable at the bar open T, bot-executable): `THROTTLE(T) = 1`
   iff `ddom(T)` non-NaN and `ddom(T) > q67_seq(k)` for the year k
   containing T (strictly greater; boundary ties stay unthrottled).
6. Multiplier (single pre-registered pair, exactly as IDEAS.md): per fill
   row with bar open T and symbol s: `m = 0.5` if `THROTTLE(T) == 1` AND
   `s != BTCUSDT` (ETH/SOL/BNB/XRP only), else `1.0`. BTC dip bids are
   NEVER throttled. NaN `ddom` -> 1.0.
7. `size_new = size_dep * m` per MAIN-R2 fill with `size_dep` non-NaN (TP
   held at deployed). Scoring uses `harness5.score` equal-exposure
   renormalisation per year (`sn *= mean(sd)/mean(sn)`), so only TIMING is
   tested, not mean exposure.
8. LOYO cut-offs: for held-out year h, `q67_loyo(h)` = 67th percentile of
   `ddom` over grid bars inside the OTHER 4 anchor-year windows (union of
   `Y_k`, k != h; `ddom` non-NaN; >= 100 bars required). `THROTTLE_loyo`
   for rows in year h uses `q67_loyo(h)`; `gain_h` is computed with
   equal-exposure renormalisation INSIDE the held-out year (same formula as
   `harness5.score`). The vol/return/turnover path is untouched (rung-level
   screen only).

One variant only (q67 / x0.5 on alts). No threshold search, no BTC leg, no
level interaction, no per-coin cut.

## Evaluation (fixed here - one variant only)

- Per anchor year (sequential cut-offs, renormalised sizes):
  `S_dep = sum(size_dep * y_dep)`, `S_new = sum(size_new_renorm * y_dep)`;
  `gain = S_new - S_dep`. `PASS_gain(Y)`: gain > 0 (strict; NaN = FAIL).
- Worst day per year: daily sums of `(size * y_dep)` grouped by
  `floor(T)` calendar day UTC on the RENORMALISED sizes (same convention as
  `harness5.score`); `W_dep = min`, `W_new = min`. `PASS_tail(Y)`:
  `W_new >= W_dep` (strictly not worse; NaN = FAIL).
- LOYO per held-out year h: same gain construction with LOYO cut-offs;
  `PASS_loyo(h)`: `gain_h > 0` (NaN = FAIL).
- DECISION RULE (assignment default + sizing/filter tail clause):
  PROMISING iff (a) `PASS_gain` in >= 4 of 5 sequential years, AND
  (b) `PASS_loyo` in >= 4 of 5 held-out years, AND (c) `PASS_tail` in >= 4
  of 5 sequential years. Otherwise NOT PROMISING. NaN/FAIL counts as a
  miss, never imputed.
- Reported per year (descriptive, NOT part of the rule): throttle share
  (fraction of fills with m = 0.5; overall + per-coin), per-coin gain split
  (BTC vs each alt, sums under the same renormalised sizes), Spearman
  rho(ddom, y_dep) on alt rows, raw (non-renormalised) sums + retention
  `S_raw_new / S_raw_dep`, full-path worst-day and maxDD of the cumulative
  daily sum (5 years concatenated chronologically, descriptive only),
  cut-off values + training-bar counts, coverage (fraction of fills with
  non-NaN ddom; expected 100% in all 5 years).
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native size*y_dep units.
- Path-effects caveat (from IDEAS.md): sleeve/budget path matters live;
  the rung-level equal-exposure screen is the cheap gate only - no engine
  run is claimed here.

## Causality / correctness tests (tests/test_oc_idea8.py)

- test_universe_counts: majors-R2 scored rows total 5498 with per-year
  T counts 990/1045/1330/989/1144; T = t_fill - f; T on 4h boundaries;
  no T at/after 2026-09-24.
- test_dom_ddom_causal_truncate: 4 sampled T; dom30/ddom recomputed from
  opens truncated to index <= T equals the stored value; doubling opens
  after T leaves dom30/ddom at T unchanged; ddom(T) is NaN iff dom30(T)
  or dom30 42 bars earlier is NaN.
- test_cutoffs_causal: year-1 q67 equals the < A_1 bar-pool 67th pct;
  LOYO q67 for one held-out year equals the other-4-years bar-pool 67th
  pct (held-out bars excluded); training pools use no bar at/after the
  anchor (sequential) resp. no bar of the held-out year (LOYO).
- test_multiplier_mapping: synthetic ddom values map to {0.5, 1.0} at the
  exact boundary (> q67 -> 0.5 on alts, == q67 -> 1.0; NaN -> 1.0; BTC
  always 1.0 even when flagged).
- test_decision_counts_match: results.json counts recomputed from yearly
  passes equal the stored decision strings.
- test_gain_signs_match_harness: stored per-year gains/worst-days equal an
  independent harness5.score recomputation from stored features.
- test_no_intraday: the analysis script never references 1m/hourly/funding/
  premium/options paths and no opens bar at/after 2026-09-24 is used.

## Deliverables

`research/tournament/oc_idea8/`: PLAN.md (this file), `analyze_idea8.py`,
`features_idea8.parquet`, `results.json`, REPORT.md (tables + one-line
verdict). `tests/test_oc_idea8.py`. No commits, no edits outside these two
paths. One process, opens only, RAM < 1 GB. No tuning on results; any
post-hoc change logged in REPORT.md.

VF_COMMON note: `src/agentic_alpha_lab/patterns/common.py` was read. Its
compute/events/event_study contract targets BTC-bar feature studies; this
tournament screen follows the W assignment's rung-level screen instead
(fills_U_ext exact outcomes, 5 anchor years to 2026-09-24), while honouring
the shared causality principles: as-of availability (index <= T only),
pre-anchor fits only, and no reads beyond the 2026-09-24 cutoff.
