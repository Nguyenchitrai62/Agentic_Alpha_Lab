# oc_blendsens PLAN (pre-registered BEFORE any outcome is computed)

SENSITIVITY, no selection: where does the deployed BOT book weight sit?

## Hypothesis (fixed here)

The deployed BOT book is `0.8 x O1 + 0.2 x Dmean` with
`O1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2` (A/Aq = member_A/Aq_O1_orders,
B/Bq = member_B/Bq_tv) and `Dmean = (D+Dq)/2` (D = members_v154 xs D,
Dq = members_quarterly_D), i.e. `scripts/forward_v205.py::research_books_d2`.
If the 0.8/0.2 choice sits on a performance plateau, small moves to
0.7/0.3 or 0.9/0.1 change per-year net book P&L only slightly and with
inconsistent sign across the five anchor years; if it sits on a slope,
raising (or lowering) the O1 weight helps with a consistent sign.
O1-only and D-only are the extreme anchors showing what each leg does alone.

## Inputs (read-only, never edited)

- Book legs rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (mirror of `oc_bookic` / `scripts/forward_v205.py`): same 6 parquet
  files from `artifacts/research/engine_real/`, union index, missing -> 0.0.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old harness hidden-year cut; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (a few small 4h frames only).

## Exact causal definitions (fixed before seeing numbers)

- Legs: `o1` and `dmean` on the union index, missing -> 0.0 (same code as
  oc_dvolshort). Raw blends (5, fixed):
  `w(alpha) = alpha*o1 + (1-alpha)*dmean` for
  alpha in {1.0 (O1 only), 0.9, 0.8 (deployed), 0.7, 0.0 (D only)}.
  No fitting: alphas are assignment-fixed, identical every year.
- v410 bear filter FIRST (audited rule, BTC-only, causal at the close of T):
  on the FULL BTC 4h-open history,
  `MA1200[T] = mean(open[T-1199..T])` via `rolling(1200, min_periods=600)`
  (open[T] inclusive, known at the close of T); `bear[T] = open[T] < MA`
  (strict, NaN -> False). Per blend, `wb[T,s] = 0.5*w[T,s]` where
  `bear[T] and w[T,s] > 0`, else `w[T,s]`. Shorts/flats unchanged.
- Grid: inner join of the raw-blend index with the opens index (dropna all),
  sorted 4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC. `wb[T,s]` is known
  at the close of bar `T` and held over `[T, T+1)`. Forward exit `open[T+1]`
  must be at/before `CUTOFF = 2026-09-24 00:00 UTC`; bars with any coin
  missing a forward open are dropped (same as oc_dvolshort: the last grid
  bar is dropped).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no
  orphan bars: `Y_k = [A_k, A_{k+1})` k = 0..3, `Y_4 = [A_4, A_4+365d)`
  (== `[A_4, CUTOFF)`; `bounds = ANCHORS + [A_4+365d]`, as oc_dvolshort).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (assignment: 0.05% per unit turnover): `cost[T,s]` =
  `0.0005 * |wb[T,s] - wprev[s]|`, `wprev` = previous grid bar's filtered
  weight for the same sym in global grid order (first grid bar: prev = 0).
  Each blend has its OWN prev chain (same convention as oc_dvolshort, only
  the rate differs: oc_dvolshort used 0.0002). Net cell:
  `pnl = wb * R1 - cost`. No funding, vol target, governor, sleeve, SL/TP,
  or compounding across bars in the per-cell sums; the equity path below
  compounds per-bar portfolio returns.
- Book path per blend: per-bar portfolio return `rp[T] = sum_s pnl[T,s]`
  over the 5 coins. Per anchor year, equity reset to 1.0 at the year's
  first bar, compounded in grid order: `eq[i+1] = eq[i]*(1+rp[T_i])`.
  Full 5y path compounds the same way from the first bar of year 1
  (context only). maxDD = `max_{peak<trough}(1 - eq_trough/eq_peak)`
  (peak running maximum strictly before the trough). Worst week = minimum
  42-bar (7-day) compounded return inside the year:
  `min_{i>=42}(eq[i]/eq[i-42]-1)`. Turnover per blend/year also reported.
- Effects (per year k, net portfolio-return units):
  `E1[k] = net_08[k] - net_07[k]` (does 0.7->0.8 help?),
  `E2[k] = net_09[k] - net_08[k]` (does 0.8->0.9 help?),
  context `EO[k] = net_O1[k] - net_D[k]` (O1-only minus D-only).
  LOYO for E1/E2: for each held-out year h, `m_{-h} = mean over the other
  4 years`; LOYO holds at h iff `sign(E[h]) == sign(m_{-h})`
  (strict, zeros fail). Count holds/5.

## Evaluation (fixed here)

- Per anchor year report, per blend (O1, 0.9, 0.8, 0.7, D): book P&L net
  (sum of net cells), worst week, maxDD (per-year reset paths), plus
  turnover and cost. Full-path maxDD/total per blend as context.
- PLATEAU rule (pre-registered; SENSITIVITY, no selection, so no
  PROMISING verdict is issued): the deployed 0.8/0.2 sits on a plateau iff
  (a) NEITHER E1 NOR E2 meets the default selection bar
  (same sign in >= 4/5 years AND LOYO holds in >= 4/5), i.e. there is no
  consistent local slope through 0.8 in either direction; AND
  (b) the mean adjacent step is small:
  `mean_k(|E1[k]|+|E2[k]|)/2 < 0.01` (under 1pp of portfolio return per
  0.1 alpha step on average). Otherwise the verdict names the slope
  (UPHILL toward more O1 if E1,E2 positive-consistent; DOWNHILL toward
  more D if negative-consistent; MIXED/cliff otherwise). One-line verdict.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters. Vectorised open-to-open screen only (no vol target, governor,
  dip sleeve, funding, SL/TP, or engine limit path).

## Causality / alignment tests (tests/test_oc_blendsens.py)

- test_blend_math: 0.8 blend equals oc_dvolshort's d2 formula cell by cell
  on the common index; 0.9/0.7 are exact convex mixes of the rebuilt legs;
  O1-only == o1, D-only == dmean.
- test_bear_filter_exact: bear flags equal rolling(1200,min600) strict
  `<` on full BTC history (NaN->False); filtered longs are exactly half
  the raw blend where bear, shorts bit-identical.
- test_grid_bounds: no `T` at/after 2026-09-24 00:00 UTC; years partition
  the grid without gaps/overlaps; last bar has a forward open <= CUTOFF.
- test_cost_math: per-blend `cost == 0.0005*turnover` (tight tolerance);
  each blend's prev chain starts at 0.

## Deliverables

`research/tournament/oc_blendsens/`: PLAN.md (this file),
`compute_blendsens.py`, `panel.parquet` (per-(T,sym,blend) filtered
weights, forwards, net cells; small), `results.json`,
`REPORT.md` (tables + one-line plateau verdict). No tuning on results;
any post-hoc change logged in REPORT.md. No commits. LIGHT job: one
process, 4h inputs only (no 1m), RAM < 1 GB.
