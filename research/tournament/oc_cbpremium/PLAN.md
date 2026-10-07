# oc_cbpremium PLAN (pre-registered BEFORE any outcome is computed)

Idea #60 (NEW): Coinbase premium as a BOOK direction tilt.

## Hypothesis (fixed here)

`research/tournament/oc_optctx/REPORT.md` found the Coinbase-vs-Binance BTC
premium level (`cbprem_last`, `cbprem_mean24`) had a 5/5-year sign-stable
negative IC to dip-rung outcomes (lower US-spot premium goes with better dip
y1.0, surviving DVOL residualization) but LOYO tercile spreads were
sign-unstable and opposed the IC, so no tradable dip rule. For the BOOK
(directional, multi-bar open-to-open holds) the same slow US-demand signal may
matter with the opposite usability: a persistent premium/discount tilts the
multi-bar drift the book rides, so scaling book LONG exposure up when the
premium is elevated (strong US spot demand) and down when deeply negative
should raise total book P&L at no systematic drawdown cost. Shorts are
unchanged (no hypothesis there).

Rule (fixed, from the assignment): at holding bar start `T`, with `z` =
premium z-score exactly as defined below (strictly causal), book LONG targets
x1.15 when `z > 1`, x0.85 when `z < -1`, else x1.0 (all 5 coins share the
BTC-only signal); shorts/flats unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (also mirrored in `oc_bearshort/compute_bearshort.py`, mirror of
  `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Premium: `data/raw/coinbase_20260925/BTC-USD_1h.parquet` (Coinbase BTC-USD
  1h, `open_time` = bar START) + Binance BTCUSDT 1h closes from
  `research/tournament/ext/hourly_ext.parquet` (`t` = bar START, `sym ==
  BTCUSDT`). Only bar STARTs < CUTOFF are used.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (hourly + 4h frames only).
- Shared ext/fills/dvol/options inputs listed in the assignment header are
  NOT otherwise used: the screen is the vectorised BOT book exactly as
  `oc_dvolshort` did (base = v410 filter, see below).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort/oc_bearshort: the last grid bar has no
  forward open and is dropped). `w[T,s]` is known at the close of bar `T`
  and is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort/oc_bearshort: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear regime FIRST (audited v410 rule, BTC-only, causal at close
  of T): on the FULL `opens_v154` BTCUSDT history compute
  `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200, min_periods=600)`;
  `bear[T] = (open_BTC[T] < MA1200[T])` (strict; NaN -> False; `open[T]`
  inclusive, known at the close of T, exactly as v410/v410_bear_book.py,
  oc_bookcoinbrake and oc_bearshort). One regime flag per bar, applied to
  all 5 coins.
- BASE (reference, = deployed book with v410): `w_base[T,s] = 0.5*w_raw[T,s]`
  if `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged.
- Premium feature (exactly as `oc_optctx.load_premium`, BTC-only):
  inner join Coinbase and Binance hourly grids on bar START `t` (both with
  `t < CUTOFF`), `prem[t] = cb_close[t]/bin_close[t] - 1`;
  `mean24[t] = mean(prem[t-23..t])`, `rolling(24, min_periods=20)`;
  `z[t] = (mean24[t] - mean(W)) / std(W, ddof=1)`,
  `W` = up to 2160 prior `mean24` values (90 days of hourly samples,
  current excluded via `.shift(1)`), `rolling(2160, min_periods=1728)`;
  std == 0 -> NaN. Grid `end[t] = t + 1h`.
- Premium as-of (strict, exactly as oc_optctx: bars strictly before T):
  an hourly premium row with start `t` (end `t+1h`) is usable at `T` iff
  its end is strictly before `T` (implemented as `end <= T - 1s`, i.e.
  `searchsorted(ends_ns, Tns - 1e9, side='left') - 1`). For 4h-aligned `T`
  the last usable hourly bar is `[T-2h, T-1h]` (1-2h staleness by design).
  `z(T)` = `cbprem_z90` of the last usable row (NaN if none / warm-up).
  One signal per bar, applied to all 5 coins (same coin mapping spirit as
  oc_dvol: BTC market-wide proxy).
- RULE (this idea, fixed multipliers, v410 first): for each (T, sym),
  if `w_base[T,s] > 0` and `z(T)` is finite:
  `mult = 1.15 if z > 1 else (0.85 if z < -1 else 1.0)`;
  `w_rule[T,s] = mult * w_base[T,s]`. If `w_base <= 0` or `z` NaN,
  `w_rule = w_base` (shorts/flats/NaN-z bit-identical). Bear-row longs
  keep their v410 x0.5 inside `w_base`; the premium tilt multiplies on top.
- Costs (exactly as oc_dvolshort/oc_bearshort): maker 0.0002 per unit
  turnover. Per (T,s) in global grid order: `cost_base[T,s]` =
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
- Long-leg P&L per year = summed net cells over BASE long rows
  (`w_base > 0`) within the year, base vs rule. Total book P&L = summed
  net cells over all rows within the year. Short-leg sums are unaffected
  by construction (reported as equality check only). Bear share per year =
  `mean(bear[T])` over year bars; tilt shares = share of base long rows
  with `z > 1` (up) / `z < -1` (down) per year.
- Coverage: share of year bars with finite `z(T)` (expected 100%: premium
  grids start 2020-08, fully warmed up long before 2021-09-24).

## Evaluation (fixed here)

- Per anchor year report: bear share; tilt up/down shares of base longs;
  long-leg P&L base vs rule (net, fixed BASE-sign membership); total book
  P&L base vs rule (net, all rows); worst week base vs rule; maxDD base vs
  rule (per-year reset paths). Full-path maxDD and total P&L base vs rule
  as context (not part of the rule).
- DECISION RULE (assignment-specific, replaces the default same-sign/LOYO
  rule): PROMISING only if (a) total book P&L strictly higher
  (`pnl_rule > pnl_base`) in >= 4/5 years, AND (b) maxDD not worse
  (`DD_rule <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years.
  NaN on either side counts as FAIL. One-line verdict. The default
  tournament LOYO rule is N/A by construction: the rule has no fitted
  threshold (fixed z = +/-1 multipliers, fixed v410 regime), so there is
  no in-year fit to leave out.
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_cbpremium.py)

- test_books_match_bearshort: rebuilt books equal oc_bearshort's formula
  cell by cell on the common index (same files, same math).
- test_premium_causal: sampled `z(T)` recomputed from premium panels
  truncated to rows with end < T are unchanged; truncating to end <= T-1s
  boundary leaves values unchanged; NaN-`z` rows are never tilted; shorts
  and flats are bit-identical base vs rule; tilted longs are exactly
  1.15x / 0.85x base and untitled longs bit-identical.
- test_bear_first: bear[T] recomputed from opens truncated to `<= T` is
  unchanged; base longs are exactly 0.5x raw on bear rows; rule shorts
  equal base shorts everywhere.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; pnl columns finite; long-leg membership fixed by
  base sign reproduces results.json.

## Deliverables

`research/tournament/oc_cbpremium/`: PLAN.md (this file),
`compute_cbpremium.py`, `panel.parquet` (per-(T,sym) raw/base/rule
weights, bear flag, z, tilt mult, forwards, net cells; small),
`results.json`, `REPORT.md` (tables + one-line verdict). No tuning on
results; any post-hoc change logged in REPORT.md. No commits. LIGHT job:
one process, 4h + hourly inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
