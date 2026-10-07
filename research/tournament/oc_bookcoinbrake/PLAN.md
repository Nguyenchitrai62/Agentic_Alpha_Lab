# oc_bookcoinbrake PLAN (pre-registered BEFORE any outcome is computed)

Idea #45 (NEW): per-coin book drawdown brake.

## Hypothesis (fixed here)

The deployment config's gate DD is a 59-day BNB-led book-long grind
2023-04-17..06-15 (research/tournament/oc_ddanat_g2: book longs ~-9..-11
plus dip stops+timeouts net of TPs per phase, BNB-led, synchronous on all
four phases; book shorts already offset +6.8 summed). A per-coin brake that
halves a coin's book LONG target while that coin's own recent book P&L is
in a drawdown should cut the book path's max drawdown at small yearly-P&L
cost, because long-bleed clusters are coin-persistent (BNB-led grind) while
most bars fall outside any coin's brake. Shorts are left unchanged so the
bear-filter short offset is preserved.

Rule (fixed, from the assignment): at each standard book row t, if a coin's
own book P&L over the previous 30 days (rows < t, vectorised book P&L per
coin) is below -2 x its trailing 1-year median absolute 30-day book P&L
(walk-forward, rows < t), that coin's book LONG target is x0.5 until its
30-day book P&L turns positive; shorts unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override
  of the old tournament-harness hidden-year cut; all five years are
  research data, findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (two small 4h frames only).
- Shared ext/fills/dvol/options/premium inputs listed in the header are
  NOT used: the assignment orders the screen with the vectorised BOT book
  exactly as oc_dvolshort did (plus the v410 bear filter first).

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
  and oc_coinbear.build_bears). `w_base[T,s] = 0.5*w_raw[T,s]` if
  `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged. This BASE is the reference the brake is judged
  against (the deployed book already carries this filter).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover.
  Per (T,s) in global grid order: `cost_base[T,s]` =
  `0.0002*|w_base[T,s]-w_base_prev[s]|` (first grid bar prev = 0.0);
  same formula on the rule path with `w_rule` and its OWN prev chain.
  Net cell: `pnl_base = w_base*R1 - cost_base`,
  `pnl_rule = w_rule*R1 - cost_rule`. No funding, vol target, governor,
  sleeve, SL/TP, or compounding across bars in the per-cell sums; the
  equity path below compounds per-bar portfolio returns.
- Brake state P&L (vectorised book P&L per coin, rows < t): the per-coin
  BASE net cells `pnl_base[t,s]` above (bear-filtered, net of its own
  turnover). No recursion: the trigger never uses `pnl_rule`.
- 30-day book P&L (strictly before T): `S30[T,s]` =
  `sum{pnl_base[t,s] : t on grid, T-30d <= t < T}`. Grid is regular 4h,
  so this is the previous 180 bars when available, fewer at the sample
  start (sum whatever rows exist; no prior row -> 0.0). Time-based
  definition; bar-count equivalent asserted in tests.
- Trailing 1-year scale (walk-forward, rows < t):
  `H[T,s] = {S30[t,s] : t on grid, T-365d <= t < T}` (current excluded);
  `M[T,s] = median(|x| : x in H[T,s])`. Grid-regular equivalent: median
  of absolute S30 over the previous 2190 values. Require >= 200 finite
  values in H else `M = NaN` (brake cannot trigger; early-sample
  fail-safe). Literal rule, no floor: if `M == 0`, entry is `S30 < 0`.
- Latching brake (per coin, in grid order, initial OFF before first bar):
  for each grid T in order, with `S = S30[T,s]`, `M = M[T,s]`:
  if currently OFF: turn ON iff `isfinite(S) and isfinite(M) and S < -2*M`;
  if currently ON: turn OFF iff `isfinite(S) and S > 0` (strictly
  positive), else stay ON. `brake_on[T,s]` is the state applied at T.
- Rule weights: `w_rule[T,s] = 0.5*w_base[T,s]` if
  `brake_on[T,s] and w_base[T,s] > 0`, else `w_base[T,s]`. Shorts and
  flats are bit-identical to base even when the brake is on.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_rule` analogously). Per anchor year, equity reset
  to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i]*(1+rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context only). maxDD = peak-to-trough
  `max(1-eq_trough/running_peak)`. Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Gate window: `W = [2023-04-17, 2023-06-15)` UTC (the oc_ddanat_g2 gate
  episode). Window loss = summed net cells over `T in W` (portfolio-return
  units): book total base vs rule; long-leg detail sums net cells over
  `w_base > 0` (fixed membership) for context.
- Brake-on share per coin per year: `mean(brake_on[T,s])` over year bars.

## Evaluation (fixed here)

- Per anchor year report: book P&L base vs rule (net, all rows); worst
  week base vs rule; maxDD base vs rule (per-year reset paths); brake-on
  share per coin (5 numbers); gate-window loss base vs rule (one row).
  Full-path maxDD and total P&L base vs rule as context (not part of
  the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) book maxDD not worse
  (`DD_rule <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years,
  AND (b) book P&L >= 95% of base in >= 4/5 years, where (b) is
  `pnl_rule >= 0.95*pnl_base` when `pnl_base >= 0`, else
  `pnl_rule >= 1.05*pnl_base` (symmetric 5% magnitude tolerance for a
  losing base year, same convention as oc_coinbear). NaN on either side
  counts as FAIL. One-line verdict. LOYO is N/A by construction: the
  threshold is already strictly walk-forward per (T,s) (no pooled
  in-year fit to leave out).
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_bookcoinbrake.py)

- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_bear_causal: bear[T] recomputed from opens truncated to `<= T`
  is unchanged; NaN-MA rows never halved; shorts/flats bit-identical
  under the bear filter; longs halved exactly where flagged.
- test_brake_causal: sampled (T,s) `S30`/`M`/`brake_on` recomputed from a
  panel truncated to rows with time `< T` are unchanged; `S30` uses no
  row `>= T`, `M` uses no `S30[t] with t >= T`; exit rows have `S30 > 0`
  at the exit bar; shorts unchanged under the rule.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; rule longs are exactly 0.5x base where
  brake_on, else identical.

## Deliverables

`research/tournament/oc_bookcoinbrake/`: PLAN.md (this file),
`compute_bookcoinbrake.py`, `panel.parquet` (per-(T,sym) base/rule
weights, brake flags, S30, M, forwards, net cells; small),
`results.json`, `REPORT.md` (tables + one-line verdict). No tuning on
results; any post-hoc change logged in REPORT.md. No commits. LIGHT job:
one process, 4h inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
