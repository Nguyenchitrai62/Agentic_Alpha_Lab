# oc_dvolshort PLAN (pre-registered BEFORE any outcome is computed)

Idea #13 (NEW): DVOL gate on BOOK SHORTS.

## Hypothesis (fixed here)

`research/tournament/oc_dvolbook/REPORT.md` found high BTC DVOL (level
z-score `dvol_z90`) predicts worse book SHORT-leg P&L with 5/5-year and
4/5-LOYO sign consistency (total/long legs fail). Economic reason: high
implied vol prices fear and forced positioning; a slow momentum book's
shorts sit in the path of the fastest moves in the sample (bear-market
relief rallies) where short losses are unbounded while the long edge
survives. Scaling short exposure down when `dvol_z90` is elevated should
therefore cut book drawdown without giving up total book P&L.

Rule (fixed, from the assignment): at holding bar start `T`, with
`z = dvol_z90` exactly as `oc_dvolbook` defines it (strictly causal, see
below), if `z >` walk-forward 67th percentile of `z` (computed on data
before the anchor of the year only), multiply every book SHORT target of
that bar by 0.5 (longs unchanged).

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_bookic/compute_bookic.py::research_books_d2`
  (also mirrored in `oc_dvolbook/compute_dvolbook.py`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- DVOL: `research/tournament/oc_dvol/dvol_hourly.parquet` (BTCDVOL/ETHDVOL
  hourly closes; `t` = bar START (UTC), bar END = `t` + 1h). No refetch.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness hidden-year cut; all five years are research
  data, findings still need prospective validation).

## Exact causal definitions (fixed before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna), sorted
  4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar (no
  forward open) is dropped. `w[T,s]` is known at the close of bar `T` and
  is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolbook).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years (partition, no
  orphan bars): `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4 + 365d)`.
- DVOL as-of (exactly as oc_dvolbook): an hourly DVOL bar (start `t_h`,
  end `t_h+1h`) is usable at `T` iff its end is at or before `T`
  (`t_h+1h <= T`). `asof(T)` = close of the last usable hourly bar. For
  4h-aligned `T` this is the bar `[T-1h, T]` (fresh at the open; strictly
  causal, nothing after `T` is used).
- Coin mapping (same as oc_dvol/oc_dvolbook; no Deribit DVOL for alts):
  BTC -> BTC DVOL; ETH -> ETH DVOL; SOL/BNB/XRP -> BTC DVOL (market-fear
  proxy).
- `dvol_z90[T,s]` = (`v0` - mean(W)) / std(W, ddof=1); `v0` = asof(T) of
  the mapped coin; W = {asof(T - k*1h) : k = 1..2160} (trailing 90d of
  hourly as-of samples, current value excluded); require >= 1728 non-NaN
  else NaN; std == 0 -> NaN. `FEAT_START = 2021-06-30` (warm-up); earlier
  rows are NaN and never used for cut-offs.
- Threshold (walk-forward, strictly previous data only): for year k,
  `q67_k` = 67th percentile (quantile 2/3) of mapped `dvol_z90` over the
  training pool = (T, sym) rows with `T` on the 4h grid,
  `T` in `[FEAT_START, A_k)`, feature non-NaN (same pool construction as
  oc_dvolbook: pre-anchor 4h bars 2021-06-30..2021-09-24 plus book-grid
  bars before `A_k`, x 5 syms, pooled single threshold). Require >= 100
  training values else the year's gate is undefined (reported as FAIL;
  not expected: year 1 has ~2.5k values).
- Gate (per-row, fixed): for each (T, sym) in year k,
  `gated = (w[T,s] < 0) and isfinite(z[T,s]) and (z[T,s] > q67_k)`;
  `w_g[T,s] = 0.5 * w[T,s]` if gated else `w[T,s]`. Longs (`w > 0`),
  flats (`w == 0`), and NaN-`z` rows are unchanged. Membership of the
  short leg for P&L attribution is fixed by the ORIGINAL `w` sign so
  gated vs ungated compare the same rows.
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (gate model, from the assignment): maker 0.0002 per unit turnover.
  Per (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|`
  with `w_prev` = the previous grid bar's weight for the same sym (first
  grid bar: prev = 0). Same formula applied to the gated path with `w_g`.
  Net leg P&L per cell: `pnl = w * R1 - cost` (ungated),
  `pnl_g = w_g * R1 - cost_g` (gated). No funding, vol target, governor,
  sleeve, SL/TP, or compounding across bars in the per-cell sums; the
  equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return
  `rp[T] = sum_s pnl[T,s]` over the 5 coins. Per anchor year, equity is
  reset to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i] * (1 + rp[T_i])`. Full 5y path compounds the same way
  from the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running maximum
  strictly before the trough). Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Coverage: share of (T, sym) rows with non-NaN `z`; share of original
  short rows gated per year.

## Evaluation (fixed here)

- Per anchor year report: `q67_k`, coverage, share of shorts gated;
  short-leg P&L gated vs ungated (net, summed over original short rows);
  total book P&L gated vs ungated (net, all rows); worst week gated vs
  ungated; maxDD gated vs ungated (per-year reset paths). Full-path maxDD
  gated vs ungated as context (not part of the rule).
- DECISION RULE (from the assignment): PROMISING only if
  (a) book maxDD improves (gated DD strictly < ungated DD) in >= 4/5
  years, AND (b) total book P&L is not lower (gated >= ungated) in
  >= 3/5 years. One-line verdict. The default tournament LOYO rule is
  N/A here by construction: thresholds are already strictly walk-forward
  (no cross-year pooling), so there is no in-year fit to leave out.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters.

## Causality / alignment tests (tests/test_oc_dvolshort.py)

- test_asof_usable_at_or_before_T: sampled (T, sym) `z` values recomputed
  from DVOL panels truncated to bars with end <= T are unchanged.
- test_cutoffs_causal: year-k `q67` uses no row with `T >= A_k`
  (recomputed from the saved panel); NaN-`z` rows are never gated.
- test_books_match_oc_bookic: rebuilt books equal oc_bookic's formula
  cell by cell on the common index.
- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; anchors
  partition the grid without gaps/overlaps; gated shorts are exactly
  half the original weight and longs are bit-identical.

## Deliverables

`research/tournament/oc_dvolshort/`: PLAN.md (this file),
`compute_dvolshort.py`, `panel.parquet` (per-(T,sym) weights, gated
weights, `z`, forwards, net cells; small), `results.json`,
`REPORT.md` (tables + one-line verdict). No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h + hourly inputs only (no 1m), RAM < 1 GB.
