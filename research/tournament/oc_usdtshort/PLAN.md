# oc_usdtshort PLAN (pre-registered BEFORE any outcome is computed)

Idea #74 (NEW): USDT/USD stablecoin premium as a BOOK SHORT-leg tilt.

## Hypothesis (fixed here)

`research/tournament/oc_usdtprem` tested the USDT/USD premium tilt only on
book LONGS (NOT PROMISING: P&L 4/5 but DD not worse only 2/5);
`research/tournament/oc_premexpo` judged the long tilt ALPHA vs an
exposure-matched control. This study tests the mirror leg, never tested in
this project: a USDT discount (z < -1 = fiat outflow / redemption pressure,
risk-off) should favour SHORT exposure (scale shorts UP), while a USDT bid
(z > 1 = fiat inflow demand) should fade shorts (scale shorts DOWN). Longs
are unchanged (no hypothesis there). If the premium times directional drift
rather than just long beta, the short tilt should raise total book P&L at no
systematic drawdown cost.

Rule (fixed, from the assignment): at holding bar start `T`, with `z` =
USDT-premium z-score exactly as `oc_usdtprem` defines it (strictly causal,
see below), book SHORT targets x1.15 when `z < -1` (fiat outflow), x0.85
when `z > 1`, else x1.0 (all 5 coins share the single market-wide signal);
longs/flats unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (also mirrored in `oc_usdtprem` / `oc_cbpremium`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`
  (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`,
  `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- USDT premium: `data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet`
  (Coinbase Exchange public REST candles, USDT-USD, granularity 3600,
  `open_time` = bar START; manifest with source, sha256, gaps, first/last).
  No refetch.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (hourly + 4h frames only).

## Exact causal definitions (fixed before seeing numbers)

- BOUND/CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt
  book index with the opens index (dropna all), sorted 4h, restricted to
  `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open
  are dropped (same as oc_dvolshort/oc_usdtprem: the last grid bar has no
  forward open and is dropped). `w[T,s]` is known at the close of bar `T`
  and is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction
  as oc_dvolshort/oc_usdtprem: `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear regime FIRST (audited v410 rule, BTC-only, causal at close
  of T, exactly as oc_usdtprem/oc_placebo): on the FULL `opens_v154`
  BTCUSDT history compute `MA1200[T] = mean(open_BTC[T-1199..T])`,
  `rolling(1200, min_periods=600)`; `bear[T] = (open_BTC[T] < MA1200[T])`
  (strict; NaN -> False; `open[T]` inclusive, known at the close of T).
  One regime flag per bar, applied to all 5 coins.
- BASE (reference, = deployed book with v410): `w_base[T,s] = 0.5*w_raw[T,s]`
  if `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats
  (`==0`) unchanged.
- USDT premium feature (identical to oc_usdtprem, single-venue, fixed here):
  hourly bar START `t` (`t < CUTOFF`), `prem[t] = close[t] - 1`
  (USDT priced in USD); `mean24[t] = mean(prem[t-23..t])`,
  `rolling(24, min_periods=20)`; `z[t] = (mean24[t] - mean(W)) / std(W,
  ddof=1)`, `W` = up to 2160 prior `mean24` values (90 days of hourly
  samples, current excluded via `.shift(1))`, `rolling(2160,
  min_periods=1728)`; std == 0 -> NaN. Grid `end[t] = t + 1h`.
- USDT as-of (strict, bars strictly before T, exactly the oc_usdtprem /
  oc_cbpremium convention): an hourly USDT row with start `t`
  (end `t+1h`) is usable at `T` iff its end is strictly before `T`
  (implemented as `end <= T - 1s`, i.e. `searchsorted(ends_ns,
  Tns - 1e9, side='left') - 1`). For 4h-aligned `T` the last usable
  hourly bar is `[T-2h, T-1h]` (1-2h staleness by design).
  `z(T)` = `z` of the last usable row (NaN if none / warm-up).
  One signal per bar, applied to all 5 coins (market-wide proxy).
- RULE (this idea, fixed multipliers, v410 first): for each (T, sym),
  if `w_base[T,s] < 0` and `z(T)` is finite:
  `mult = 1.15 if z < -1 else (0.85 if z > 1 else 1.0)`;
  `w_rule[T,s] = mult * w_base[T,s]`. If `w_base >= 0` or `z` NaN,
  `w_rule = w_base` (longs/flats/NaN-z bit-identical). Note the mirror
  orientation vs oc_usdtprem longs: shorts scale UP on outflow (z < -1).
- Costs (assignment value, oc_dvolshort mechanics): 0.05% = 0.0005 per unit
  turnover. Per (T,s) in global grid order:
  `cost_base[T,s]` = `0.0005*|w_base[T,s]-w_base_prev[s]|` (first grid bar
  prev = 0.0); same formula on the rule path with `w_rule` and its OWN
  prev chain. Net cell: `pnl_base = w_base*R1 - cost_base`,
  `pnl_rule = w_rule*R1 - cost_rule`. No funding, vol target, governor,
  sleeve, SL/TP, or compounding across bars in the per-cell sums; the
  equity path below compounds per-bar portfolio returns.
- Book path: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_rule` analogously). Per anchor year, equity reset
  to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i]*(1+rp[T_i])`. Full 5y path compounds the same way from
  the first bar of year 1 (context + placebo DD reference). maxDD =
  peak-to-trough `max(1-eq_trough/running_peak)`. Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Short-leg P&L per year = summed net cells over BASE short rows
  (`w_base < 0`) within the year, base vs rule. Total book P&L = summed
  net cells over all rows within the year. Long-leg sums are unaffected
  by construction (reported as equality check only). Tilt shares = share
  of base short rows with `z < -1` (up x1.15) / `z > 1` (down x0.85) per
  year ("share tilted" = up + down). Coverage = share of year bars with
  finite `z(T)`.

## Placebo (fixed here, stricter screen from oc_placebo, shape as oc_premexpo)

- Runs = maximal constant-mult segments of the RULE bar-mult series
  (values in {1.15, 0.85, 1.0}, exact float equality on assigned levels).
- 500 seeded placebos over the FULL 10955-bar series: each draw permutes
  the (value, length) run pairs with `np.random.default_rng(9100 + i)`
  (i = 0..499, same seeds as oc_premexpo's 5y draws) and rebuilds the
  same-length bar-mult series (total tilted-row counts per level exact;
  adjacent equal-valued pairs merge on rebuild so the run list can only
  shrink by merges -- row counts stay exact; documented oc_premexpo
  behaviour).
- Per placebo draw: `w_plac = w_base` with shorts x mult_plac
  (longs/flats bit-identical), OWN global turnover chain
  (first prev = 0, maker 0.0005), net cells `w_plac*R1 - cost_plac`.
  Deltas vs the SAME base: `dPnl_5y = sum(pnl_plac) - sum(pnl_base)` over
  the full grid; `dDD_full = maxDD_full(plac) - maxDD_full(base)` with the
  full-path equity (compounded from year-1 start, no reset).
- Gates: `gate_pnl_p95` = 95th percentile of the 500 placebo `dPnl_5y`;
  `gate_dd_p05` = 5th percentile of the 500 placebo `dDD_full`
  (DD delta: more negative = better). Real deltas use the ROUNDED 6dp
  values stored in results.json for percentile ranks (oc_placebo
  convention; ties at 0.0 carry mass).

## Evaluation (fixed here)

- Per anchor year report: coverage; bear share; tilt up/down shares of base
  shorts; short-leg P&L base vs rule (net, fixed BASE-sign membership);
  total book P&L base vs rule (net, all rows); worst week base vs rule;
  maxDD base vs rule (per-year reset paths). Full-path maxDD and total P&L
  base vs rule as context (also the placebo reference).
- DECISION RULE (stricter screen from oc_placebo, replaces the default
  same-sign/LOYO rule): PROMISING only if (a) total book P&L >= base
  (`pnl_rule >= pnl_base`) in >= 4/5 years, AND (b) maxDD not worse
  (`DD_rule <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years,
  AND (c) the 5y P&L delta >= the placebo p95, AND (d) the 5y maxDD delta
  <= the placebo p05. NaN on either side counts as FAIL. One-line verdict.
  The default tournament LOYO rule is N/A by construction: the rule has no
  fitted threshold (fixed z = +/-1 multipliers, fixed v410 regime; the
  placebo is a timing diagnostic, not a fit).
- Cost context: weights average << 1, so per-cell sums are in
  portfolio-return units; the per-year equity paths above are the scale
  that matters.

## Causality / alignment tests (tests/test_oc_usdtshort.py)

- test_books_match_usdtprem: rebuilt books equal oc_usdtprem's formula
  cell by cell on the common index (same files, same math).
- test_usdt_causal: sampled `z(T)` recomputed from the USDT hourly panel
  truncated to rows with end < T are unchanged; NaN-`z` rows are never
  tilted; longs and flats are bit-identical base vs rule; tilted shorts
  are exactly 1.15x / 0.85x base and untilted shorts bit-identical.
- test_bear_first: bear[T] recomputed from opens truncated to `<= T` is
  unchanged; base longs are exactly 0.5x raw on bear rows; rule longs
  equal base longs everywhere.
- test_grid_bounds: no `T` at/after CUTOFF; years partition the grid
  without gaps/overlaps; pnl columns finite; short-leg membership fixed by
  base sign reproduces results.json; placebo row counts per mult level are
  exact.

## Deliverables

`research/tournament/oc_usdtshort/`: PLAN.md (this file),
`compute_usdtshort.py`, `panel.parquet` (per-(T,sym)
raw/base/rule weights, bear flag, z, tilt mult, forwards, net cells;
small), `results.json`, `REPORT.md` (tables + one-line verdict). No tuning
on results; any post-hoc change logged in REPORT.md. No commits. LIGHT job:
one process, 4h + hourly inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
