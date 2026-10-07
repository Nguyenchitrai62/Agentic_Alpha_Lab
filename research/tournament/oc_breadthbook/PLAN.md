# oc_breadthbook PLAN (pre-registered BEFORE any outcome is computed)

Idea #63 (NEW): breadth brake on BOOK LONGS.

## Hypothesis (fixed here)

`research/tournament/oc_grindsignal/REPORT.md` (diagnostic, 30 stats, extreme
= pct <= 5 / >= 95 vs all 4h grid bars) found exactly ONE stat meeting the
pre-fixed >= 3-of-4 same-tail bar: breadth HIGH (E0 grind 2023-04-17 100.0,
E1 2023-07-14 76.7, E2 2024-01-03 100.0, E3 2025-10-07 100.0; n_extreme = 3,
tail hi). Breadth = 1.0 (all five majors above their 200-day mean) holds on
23.3% of grid bars, so 3/4 DD-episode starts at the maximum (4th at 0.8, same
direction; binomial p ~ 4% under independence -- suggestive, not proof, and
one of 30 stats tested). Economic reason: drawdowns begin from fully extended
bull-market tops, never from weakness; a slow momentum book's longs bought
into the extended top grind down first (oc_ddanat_g2: 59-day BNB-led
long bleed 2023-04-17..06-15). Trimming long exposure while breadth is pinned
at 1.0 should therefore cut book drawdown at small yearly-P&L cost, because
most bars fall outside the brake while the worst episode starts sit inside it.
Shorts are left unchanged.

Rule (fixed, from the assignment): at each standard book row t, breadth =
share of the five majors whose daily close (last complete day before t) is
above its 200-day mean; when breadth = 1.0, book LONG targets x0.75; else
unchanged; shorts unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Daily closes: derived ONLY from
  `research/tournament/ext/hourly_ext.parquet` (hourly OHLC 35 coins,
  2020-08-01..2026-09-23 23:00 open; columns t = bar START UTC, close).
  No refetch. No 1m data of any kind.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness hidden-year cut; all five years are research
  data, findings still need prospective validation).
- Shared ext/fills/dvol/options/premium inputs listed in the header are
  NOT used except hourly_ext: the assignment orders the screen with the
  vectorised BOT book exactly as oc_dvolshort did (plus the v410 bear
  filter first).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort: the last grid bar has no forward
  open and is dropped). `w[T,s]` is known at the close of bar `T` and is
  held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear filter FIRST (audited v410 rule, BTC-only, causal at close
  of T): on the FULL `opens_v154` BTCUSDT history compute
  `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200, min_periods=600)`;
  `bear[T] = (open_BTC[T] < MA1200[T])` (strict; NaN -> False; `open[T]`
  inclusive, known at the close of T, exactly as v410/v410_bear_book.py
  and oc_bookcoinbrake.build). `w_base[T,s] = 0.5*w_raw[T,s]` if
  `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged. This BASE is the reference the breadth brake is
  judged against (the deployed book already carries this filter).
- Daily close (strictly causal): an hourly bar `[t, t+1h]` has end
  `t+1h`. Daily day ending at midnight `E` (00:00 UTC) has close
  `C(E,s)` = close of the hourly bar with `t = E - 1h` (bar `[E-1h, E]`)
  if that exact row exists in hourly_ext, else NaN (no forward-fill,
  no substitution). Only hourly bars with end <= T can enter any
  quantity used at T (see below).
- Last complete day before T: `e0(T)` = T floored to midnight
  (`T.normalize()`, i.e. the largest midnight <= T). The day ending at
  `e0(T)` is complete at T: if T is 00:00 its close bar `[T-1h, T]` ends
  exactly at T; if T is 04:00/08:00/... the day ended at today's 00:00,
  hours ago. The breadth close used at T is `C0(T,s) = C(e0(T), s)`,
  whose hourly bar end `e0(T) <= T` always. Nothing after T is used.
- 200-day mean (current excluded, mirrors oc_grindsignal's
  `[T-200d, T)` hourly-mean convention at daily resolution):
  `M(E,s)` = mean of `{C(E-k*1d, s) : k = 1..200}` (the 200 daily closes
  strictly before E). Require all 200 non-NaN else NaN (fail-safe;
  not expected on the grid: hourly_ext starts 2020-08-01, so the first
  grid bar 2021-09-24 has > 400 prior days).
- Per-coin flag: `above[T,s]` = `isfinite(C0) and isfinite(M) and
  (C0 > M)` (strict; NaN on either side -> False).
- Breadth: `breadth[T]` = mean of `above[T,s]` over the 5 majors IF all
  5 coins have finite C0 and finite M at T, else NaN (same NaN rule as
  oc_grindsignal's breadth). Range {0.0, 0.2, ..., 1.0} or NaN.
  `breadth_on[T]` = `isfinite(breadth[T]) and (breadth[T] == 1.0)`.
  NaN-breadth rows are never gated. Fixed threshold 1.0 (no fitted
  parameter, no walk-forward percentile).
- Rule weights: `w_rule[T,s] = 0.75*w_base[T,s]` if
  `breadth_on[T] and w_base[T,s] > 0`, else `w_base[T,s]`. Shorts and
  flats are bit-identical to base even when the brake is on. Combined
  bear+breadth longs are 0.375x raw (v410 first, then breadth).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover.
  Per (T,s) in global grid order: `cost_base[T,s]` =
  `0.0002*|w_base[T,s]-w_base_prev[s]|` (first grid bar prev = 0.0);
  same formula on the rule path with `w_rule` and its OWN prev chain.
  Net cell: `pnl_base = w_base*R1 - cost_base`,
  `pnl_rule = w_rule*R1 - cost_rule`. No funding, vol target, governor,
  sleeve, SL/TP, or compounding across bars in the per-cell sums; the
  equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_rule` analogously). Per anchor year, equity reset
  to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i]*(1+rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context only). maxDD = peak-to-trough
  `max(1-eq_trough/running_peak)`. Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Breadth-on share per year: `mean(breadth_on[T])` over year bars;
  coverage per year: `mean(isfinite(breadth[T]))` over year bars.

## Evaluation (fixed here)

- Per anchor year report: book P&L base vs rule (net, all rows); worst
  week base vs rule; maxDD base vs rule (per-year reset paths);
  breadth-on share + coverage (2 numbers per year). Full-path maxDD and
  total P&L base vs rule as context (not part of the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) book maxDD not worse
  (`DD_rule <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years,
  AND (b) book P&L >= 95% of base in >= 4/5 years, where (b) is
  `pnl_rule >= 0.95*pnl_base` when `pnl_base >= 0`, else
  `pnl_rule >= 1.05*pnl_base` (symmetric 5% magnitude tolerance for a
  losing base year, same convention as oc_bookcoinbrake). NaN on either
  side counts as FAIL. One-line verdict. LOYO is N/A by construction:
  the threshold (1.0) is fixed with no in-year fit to leave out (v410's
  MA is per-bar causal, no pooling).
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_breadthbook.py)

- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_bear_matches_bookcoinbrake: bear[T] recomputed from opens
  truncated to `<= T` is unchanged; NaN-MA rows never halved;
  shorts/flats bit-identical under the bear filter.
- test_breadth_causal: sampled T `breadth`/`breadth_on` recomputed from
  hourly_ext truncated to bar-ends <= T are unchanged; `C0` uses no bar
  ending after T; `M` uses no daily close at/after e0(T); NaN-breadth
  rows are never gated; shorts unchanged under the rule.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; rule longs are exactly 0.75x base where
  breadth_on, else identical.

## Deliverables

`research/tournament/oc_breadthbook/`: PLAN.md (this file),
`compute_breadthbook.py`, `panel.parquet` (per-(T,sym) base/rule
weights, bear/breadth flags, forwards, net cells; small),
`results.json`, `REPORT.md` (tables + one-line verdict). No tuning on
results; any post-hoc change logged in REPORT.md. No commits. LIGHT job:
one process, 4h + hourly inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
