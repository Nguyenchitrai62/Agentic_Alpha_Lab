# oc_bookthresh PLAN (pre-registered BEFORE any outcome is computed)

Idea #48 (NEW): book signal-strength threshold — zero weak book targets.

## Hypothesis (fixed here)

Small `|target|` book weights are low-conviction outputs of the
`forward_v205.research_books_d2` blend (0.8*o1 + 0.2*(D+Dq)/2, with the
v410 bear-long filter applied first). They pay linear turnover (maker
0.0002 per unit) and add variance while contributing little expected
edge per unit weight. Zeroing a coin's book target when its strength
` |w_base|` falls below its own walk-forward 25th percentile (fitted
strictly on rows before the anchor year, per coin) should therefore
raise net book P&L (saved turnover + avoided noise trades) without
worsening book maxDD.

Rule (fixed, from the assignment): for anchor year k (anchor `A_k`),
per coin s, let `q25_{k,s}` = 25th percentile of `|w_base[U,s]|` over
training rows U with `U < A_k` (screened grid only, per coin, zeros
included). At decision bar `T` in year k, `w_rule[T,s] = 0` if
`|w_base[T,s]| < q25_{k,s}`, else `w_rule[T,s] = w_base[T,s]`
(stronger signals bit-identical; already-zero rows stay zero).

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (also mirrored in `oc_bookic/compute_bookic.py`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  full history for the causal bear MA; screened grid for returns).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment
  overrides the old tournament-harness hidden-year cut; all five years
  are research data, findings still need prospective validation).

## Exact causal definitions (fixed before seeing numbers)

- Raw book `w_raw` = `research_books_d2()` (float, per 4h bar, per sym).
- v410 bear filter FIRST (BASE = control, exactly as
  oc_bullbook/oc_bookcoinbrake): `MA1200[T]` = rolling-1200 mean
  (`min_periods=600`) of BTC 4h opens on the FULL `opens_full` history;
  `bear[T] = (BTC_open[T] < MA1200[T])` (strict, NaN -> False), with
  `open[T]` inclusive (causal at the close of T).
  `w_base[T,s] = 0.5 * w_raw[T,s]` if `bear[T]` and `w_raw[T,s] > 0`
  (longs only, strict), else `w_raw[T,s]`. Shorts/flats unchanged.
- Grid: inner join of the raw-book index with the opens index
  (dropna-any rows dropped), restricted to
  `T in [2021-09-24, 2026-09-24)` UTC, sorted 4h grid; the last grid bar
  (no forward open: `fwd1` NaN on any sym) is dropped. `w_base[T,s]` is
  known at the close of bar `T` and held over `[T, T+1)`. Forward exit
  uses `open[T+1]` only where the full 5-sym `fwd1` row is non-NaN.
  Final screened grid is the panel index (expect 10955 bars x 5 = 54775
  rows, 2021-09-24..2026-09-23 16:00 UTC).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years (partition, no
  orphan bars): `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4 + 365d)` with `A_5 = LAST_BOUND = 2026-09-24`.
- Thresholds (walk-forward, strictly previous data only, per coin):
  for year k and coin s, training pool = screened-panel rows
  `(U, s)` with `U < A_k` (all grid bars before the anchor, zeros of
  `|w_base|` included). `q25_{k,s}` = 25th percentile
  (`numpy.quantile`, linear interpolation) of `|w_base|` over that
  pool. Year 0 (`A_0` = grid start) has an EMPTY pool: thresholds are
  undefined and the rule is INACTIVE that year
  (`w_rule == w_base` on every row; share zeroed = 0; base-vs-rule
  deltas = 0 by construction). No minimum-count fallback: any later
  year has ~2000+ training rows per coin, so the >= 100-row guard is
  documentary only. No within-year, pooled-across-coins, or forward
  data enters any `q25`.
- Gate (per-row, fixed): for each `(T, s)` in year k with defined
  `q25_{k,s}`: `zeroed = (|w_base[T,s]| < q25_{k,s])`
  (strict `<`; ties at the quantile stay traded);
  `w_rule[T,s] = 0.0` if zeroed else `w_base[T,s]`. Year 0: never
  zeroed. NaN weights cannot occur (books fillna 0.0); if one did, it
  would stay unzeroed.
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open,
  4h, per sym).
- Costs (gate model, exactly as oc_dvolshort): maker 0.0002 per unit
  turnover. Per sym in grid order:
  `cost_base[T,s] = 0.0002 * |w_base[T,s] - w_base_prev[s]|`,
  `cost_rule[T,s] = 0.0002 * |w_rule[T,s] - w_rule_prev[s]|`,
  each path with its OWN prev (first grid bar: prev = 0). Net cells:
  `pnl_base = w_base * R1 - cost_base`,
  `pnl_rule = w_rule * R1 - cost_rule`. No funding, vol target,
  governor, sleeve, SL/TP, or compounding across bars in the per-cell
  sums; the equity path below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return
  `rp_base[T] = sum_s pnl_base[T,s]`, `rp_rule[T]` ditto. Per anchor
  year, equity reset to 1.0 at the year's first bar and compounded in
  grid order: `eq[i+1] = eq[i] * (1 + rp[T_i])`. Full 5y path compounds
  the same way from the first bar of year 1 (context only). maxDD of a
  path = `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running
  maximum strictly before the trough). Worst week = minimum 42-bar
  (7-day) compounded return inside the year:
  `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Coverage: share of year rows newly zeroed
  (`w_base != 0` but `w_rule == 0`) and share already-zero; per-coin
  `q25_{k,s}` values saved.

## Evaluation (fixed here)

- Per anchor year report: per-coin `q25_{k,s}`; share of rows newly
  zeroed (overall + per coin); book P&L net base vs rule
  (summed `pnl` over all year rows); turnover cost base vs rule
  (summed `cost`); worst week base vs rule; maxDD base vs rule
  (per-year reset paths). Full-path maxDD / total P&L base vs rule as
  context (not part of the rule).
- DECISION RULE (from the assignment): PROMISING only if
  (a) net book P&L strictly higher (rule > base) in >= 4/5 years, AND
  (b) maxDD not worse (rule <= base + 1e-12) in >= 4/5 years.
  One-line verdict. Year 0 ties on both legs by construction (rule
  inactive), so a PASS requires winning all four later years on P&L
  and losing DD nowhere except at most one year.
- LOYO side row (descriptive, NOT part of the verdict; default
  tournament stability): effect `d_k = total_pnl_rule_k -
  total_pnl_base_k`; held-out h holds if `sign(d_h) ==
  sign(mean_{k!=h} d_k)` with `mean_{k!=h} d_k > 0`; report count /5.
- Cost context: weights average << 1, so per-cell bps overstate
  portfolio impact; the portfolio sums and equity paths above are the
  scale that matters.

## Causality / alignment tests (tests/test_oc_bookthresh.py)

- test_books_match_dvolshort: rebuilt books equal
  oc_dvolshort's `research_books_d2` cell by cell on the common index.
- test_bear_filter_exact: BASE longs in bear bars are exactly half the
  raw weight, shorts/flats bit-identical; bear flags recomputed from
  the full opens history (rolling 1200, min 600, strict, NaN->False).
- test_thresholds_causal: saved per-(year, coin) `q25` equals the 25th
  percentile of `|w_base|` over screened-panel rows with `T < A_k`
  only (recomputed from `panel.parquet`); year-0 thresholds are NaN
  (undefined, rule inactive); zeroing is exactly
  `|w_base| < q25` on years 1..4 and nowhere in year 0.
- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; anchors
  partition the panel without gaps/overlaps; non-zeroed rows are
  bit-identical between paths; costs use own-path prev with first
  prev = 0.

## Deliverables

`research/tournament/oc_bookthresh/`: PLAN.md (this file),
`compute_bookthresh.py`, `panel.parquet` (per-(T,sym) base/rule
weights, thresholds, forwards, costs, net cells; small),
`results.json`, `REPORT.md` (tables + one-line verdict). No tuning on
results; any post-hoc change logged in REPORT.md. No commits. LIGHT
job: one process, 4h inputs only (no 1m), RAM < 1 GB.
