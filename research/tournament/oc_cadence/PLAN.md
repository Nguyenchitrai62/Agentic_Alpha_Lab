# oc_cadence PLAN (pre-registered BEFORE any outcome is computed)

Idea #47 (NEW): slower book cadence. The BOT book re-targets every 4h.

## Hypothesis (fixed here)

The BOT book (`forward_v205.research_books_d2` with the v410 bear-long
filter) re-targets every 4h. A 4h re-target pays L1 turnover on every
wiggle of the underlying members; if much of that wiggle is noise, holding
each target for 8h should cut turnover costs by roughly half while the
stale-position drag stays small, so net book P&L rises without
systematically worsening book maxDD. The 12h cadence is a pre-registered
sensitivity (reported only, NOT for selection) to check for monotonicity.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (= `oc_bookic` formula: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`,
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/` member caches.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar window).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, 4h opens + book parquets only (no 1m data),
  RAM < 1 GB.

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of the book index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar
  (no forward open) is dropped and every kept bar must have all 5 forward
  opens non-NaN (same boundary as oc_dvolshort/oc_bullbook). Weight
  `w[T,s]` is known at the close of bar `T` and is held over `[T, T+1)`.
  Expected: 10955 bars (2190/2190/2196/2190/2189 per anchor year).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition the grid
  with no gaps/overlaps: `Y_k = [B_k, B_{k+1})`, `B = ANCHORS +
  [2026-09-24]`.
- Bear filter FIRST (audited v410, exactly as oc_bullbook): on the FULL BTC
  opens history, `MA1200[T] = mean(BTC_open[T-1199..T])` via
  `rolling(1200, min_periods=600).mean()`; `bear[T] iff BTC_open[T] <
  MA1200[T]` (strict; equality or NaN-MA -> False, weight unchanged).
  Flag at `T` uses `open[T]` inclusive, i.e. known at the close of bar `T`.
  `BASE[T,s] = 0.5 * w[T,s] where bear[T] and w[T,s] > 0, else w[T,s]`
  (longs only; shorts/flat unchanged).
- Cadence (fixed rule from the assignment, applied to BASE): let
  `i = 0..N-1` be the ordinal of `T` in the sorted grid
  (`i = 0` is 2021-09-24 00:00 UTC). `can8[i] iff i % 2 == 0`
  (rows whose 4h index is even may CHANGE the target);
  `can12[i] iff i % 3 == 0`. Per coin `s`:
  `W8[T_0,s] = BASE[T_0,s]`, `W8[T_i,s] = BASE[T_i,s]` if `can8[i]`
  else `W8[T_{i-1},s]`; same for `W12` with `can12`. The hold mask is
  time-only (same for all 5 coins) and strictly causal: `W8[T_i]`
  uses only `BASE` rows at even ordinals `<= i`.
- Returns: `R1[T,s] = open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (gate model from the assignment): 0.05% per unit turnover,
  `COST = 0.0005`. Per (T, s) in grid order with each path's OWN prev
  (first grid bar prev = 0):
  `cost_P[T,s] = COST * |W_P[T,s] - W_P[prev,s]|` for
  `P in {base, 8h, 12h}`. Gross cell `g_P = W_P * R1`;
  net cell `n_P = g_P - cost_P`.
- Book path per variant: per-bar portfolio net return
  `rp_P[T] = sum_s n_P[T,s]`. Per anchor year, equity reset to 1.0 at the
  year's first bar and compounded in grid order:
  `eq[i+1] = eq[i] * (1 + rp_P[T_i])`. Full 5y path compounds the same way
  from the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running maximum
  strictly before the trough). Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
  Gross P&L per year = `sum_{T,s} g_P`; turnover = `sum |W_P - W_P_prev|`;
  cost = `COST * turnover`; net P&L = `gross - cost` (= `sum n_P`).
- Coverage: share of grid bars with `bear`; share of (T,sym) cells where
  `W8 != BASE` is not reported (held rows equal BASE only by coincidence);
  instead report turnover and cost per path per year (the selection scale).

## Evaluation (fixed here)

- Per anchor year report, BASE vs 8H: gross book P&L, turnover, cost, net
  book P&L, worst week (net path), maxDD (net path, per-year reset).
  Same columns for 12H as a sensitivity (NOT for selection).
  Full-path maxDD / total P&L per variant as context (not part of rule).
- DECISION RULE (from the assignment, binding): PROMISING only if
  (a) net book P&L strictly higher (`net_8h > net_base`) in >= 4/5 years,
  AND (b) maxDD not worse (`maxDD_8h <= maxDD_base`) in >= 4/5 years.
  12h plays no role in the verdict. One-line verdict.
- LOYO side row (descriptive, NOT for selection): on the per-year net-P&L
  difference `d = net_8h - net_base`, held-out year `h` holds if
  `sign(d[h]) == sign(mean(d[k], k != h))` and the leave-out mean is
  positive; reported as `loyo_higher_count`. Covers the default tournament
  stability rule without changing the binding rule above.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters.

## Causality / alignment tests (tests/test_oc_cadence.py)

- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; anchors partition
  the grid without gaps/overlaps; expected 10955 bars.
- test_books_match_oc_dvolshort: rebuilt raw books equal the oc_dvolshort
  formula cell by cell on the common index.
- test_bear_causal: bear flags recomputed from opens truncated to
  `<= T+4h` are unchanged; bear uses only `open <= T`.
- test_cadence_hold: `W8` equals `BASE` on even ordinals and equals the
  previous held value on odd ordinals (per coin); `W12` equals `BASE` on
  `i % 3 == 0` and holds otherwise; row 0 equals BASE on all paths.
- test_cost_math: per-year `cost == 0.0005 * turnover` (tight tolerance)
  and `net == gross - cost`; decision counts recomputed from the year rows
  match `results.json`.

## Deliverables

`research/tournament/oc_cadence/`: PLAN.md (this file),
`compute_cadence.py`, `results.json`, `REPORT.md` (tables + one-line
verdict). No tuning on results; any post-hoc change logged in REPORT.md.
No commits. LIGHT job: one process, 4h + book inputs only (no 1m),
RAM < 1 GB.
