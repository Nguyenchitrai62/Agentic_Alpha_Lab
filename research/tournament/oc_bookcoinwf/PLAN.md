# oc_bookcoinwf PLAN (pre-registered BEFORE any outcome is computed)

Idea #38 (NEW): walk-forward per-coin book gating.

## Hypothesis (fixed here)

Some majors' book legs persistently lose (or win) net of turnover, so
trading the BOT book only on coins whose own book P&L so far is positive
cuts dead-weight turnover and drawdown without giving up total book P&L.
PROMISING only under the rule below.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (itself a mirror of `oc_bookic/compute_bookic.py::research_books_d2`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness hidden-year cut; all five years are research
  data, findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (two small 4h frames only).

## Exact causal definitions (fixed before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; bars with any coin
  missing a forward open are dropped (same as oc_dvolshort: the last grid
  bar has no forward open and is dropped). `w[T,s]` is known at the close
  of bar `T` and is held over `[T, T+1)`. Forward exit `open[T+1]` must be
  at/before `CUTOFF = 2026-09-24 00:00 UTC`.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3, `Y_4 = [A_4, A_4+365d)`
  (== `[A_4, CUTOFF)`; same bounds construction as oc_dvolshort:
  `bounds = ANCHORS + [A_4 + 365d]`).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment: 0.05% per unit turnover): `cost[T,s]` =
  `0.0005 * |w[T,s] - w_prev[s]|` with `w_prev` = the previous grid bar's
  weight for the same sym in global grid order (first grid bar: prev = 0).
  Same formula on the gated path with `w_g` (global gated chain, so a coin
  dropped at a year boundary pays one unwind turnover at the boundary).
  Net cell: `pnl = w * R1 - cost` (full), `pnl_g = w_g * R1 - cost_g`
  (gated). No funding, vol target, governor, sleeve, SL/TP, compounding
  across bars in the per-cell sums; the equity path below compounds
  per-bar portfolio returns.
- History pool (strictly causal + 7d embargo): for anchor `A_k`,
  `H_k` = grid bars with `T >= 2020-08-01` AND `T < A_k - 7 days`.
  Effective lower bound is the grid start (books start 2021-09-24 00:00,
  verified before writing this plan). Every `T` in `H_k` has a valid
  forward open (by grid construction, `T+1 <= T+4h < A_k - 7d + 4h`,
  still before the anchor). History P&L per coin uses the SAME global
  per-cell series as the full path (no recomputation, no reset):
  `S_hist[k,s] = sum_{T in H_k} pnl[T,s]`.
- Gate (per-year, fixed): `G_k = {s : S_hist[k,s] > 0}` (strictly
  positive). FAIL-safe (fixed here, year 1 has empty history because
  books start exactly at `A_0`): if `H_k` is empty, `G_k` = all 5 coins
  (fall back to the full book), flagged `fallback=true` in results.
- Gated weights: for `T` in `Y_k`, `w_g[T,s] = w[T,s]` if `s in G_k`
  else `0.0`. Year-1 fallback therefore has `w_g == w` everywhere.
- Book path per variant: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins (`rp_g` analogously from `pnl_g`). Per anchor year,
  equity is reset to 1.0 at the year's first bar and compounded in grid
  order: `eq[i+1] = eq[i] * (1 + rp[T_i])`. Full 5y path compounds the same
  way from the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running maximum
  strictly before the trough). Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Per-coin per-year table: `P_full[k,s] = sum_{T in Y_k} pnl[T,s]`,
  `P_gated[k,s] = sum_{T in Y_k} pnl_g[T,s]` (excluded coins contribute
  only their boundary unwind cost, else 0).

## Evaluation (fixed here)

- Per anchor year report: `S_hist[k,s]` (all 5), gated set `G_k`
  (`fallback` flag for year 1); per-coin `P_full` / `P_gated`; total book
  P&L gated vs ungated (net, all rows); worst week gated vs ungated;
  maxDD gated vs ungated (per-year reset paths). Full-path maxDD and total
  P&L gated vs ungated as context (not part of the rule).
- DECISION RULE (from the assignment): PROMISING only if
  (a) gated book P&L not lower (`P_gated >= P_full`) in >= 4/5 years, AND
  (b) maxDD not worse (`DD_gated <= DD_full`) in >= 4/5 years.
  One-line verdict. The generic tournament same-sign/LOYO default does not
  apply: there is one signed comparison pair per year, and the gate is
  already strictly cumulative walk-forward (no in-year fit to leave out),
  so no LOYO is computed.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Note the deliberate difference from oc_dvolshort: this study
  uses the assigned 0.0005/unit turnover (oc_dvolshort used 0.0002).

## Causality / alignment tests (tests/test_oc_bookcoinwf.py)

- test_history_embargo: every `T` in `H_k` satisfies `T < A_k - 7d`;
  recomputing `S_hist` from a panel truncated to `T < A_k - 7d` is
  unchanged; year-1 history is empty and falls back to the full book.
- test_gate_applied: `w_g == w` on gated (T, sym), `w_g == 0` on excluded
  (T, sym); fallback year has `w_g == w` everywhere.
- test_books_match_dvolshort: rebuilt books equal oc_dvolshort's formula
  cell by cell on the common index (same files, same math).
- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; years partition
  the grid without gaps/overlaps; all `H_k`/`Y_k` membership keyed by `T`.

## Deliverables

`research/tournament/oc_bookcoinwf/`: PLAN.md (this file),
`compute_bookcoinwf.py`, `panel.parquet` (per-(T,sym) weights, gated
weights, forwards, net cells; small), `results.json`,
`REPORT.md` (tables + one-line verdict). No tuning on results; any
post-hoc change logged in REPORT.md. No commits. LIGHT job: one process,
4h inputs only (no 1m), RAM < 1 GB.
