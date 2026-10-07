# oc_expirybook PLAN (pre-registered BEFORE any outcome is computed)

Idea #62 (NEW): options-expiry week effect on the BOOK.

## Hypothesis (fixed here)

`research/tournament/oc_expiry/REPORT.md` studied Deribit monthly-expiry
windows on dip fills (NOT_PROMISING: WEEK dip spread flips sign 3+/2-,
LOYO 3/5) and reported book gross P&L descriptively (WEEK spread negative
in 5/5 but tiny, ~1-3 bps/bar). The BOOK itself was never gated. Hypothesis:
holding bars that start in the 48 hours before a Deribit monthly BTC
options expiry behave worse (expiry pinning / hedging flows / weekend-like
illiquidity), so halving book exposure on those bars should not hurt total
book P&L and should not worsen book maxDD.

Rule (fixed, from the assignment): Deribit monthly BTC options expire on
the last Friday of each month at 08:00 UTC; for book holding bars that
start in the 48 hours before an expiry, book targets x0.5 (both sides);
otherwise unchanged.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2`
  (also mirrored in `oc_bookic/compute_bookic.py`):
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`,
  union index, missing -> 0.0, from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old tournament-harness hidden-year cut; all five years are research
  data, findings still need prospective validation).

## Exact causal definitions (fixed before seeing numbers)

- Expiry calendar (pure function of year/month, no market input):
  `E(y,m)` = last Friday of month m, 08:00 UTC, for 2021-01 .. 2026-09.
  Friday == weekday 4; `back = (last_day.weekday() - 4) % 7`.
- Expiry window (half-open, on bar-open time T):
  `in_exp(T)` = True iff T in `[E - 48h, E)` for some expiry E.
  The calendar is known years in advance: zero leakage by construction.
- Grid: inner join of the book index with the opens index (dropna), sorted
  4h grid; `T` in `[2021-09-24, 2026-09-24)` UTC; the last grid bar (no
  forward open) is dropped. `w[T,s]` is known at the close of bar `T` and
  is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before
  `CUTOFF = 2026-09-24 00:00 UTC` (same boundary as oc_dvolshort).
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years (partition, no
  orphan bars): `Y_k = [A_k, A_{k+1})` for k = 0..3,
  `Y_4 = [A_4, A_4 + 365d)` (= 2026-09-24).
- BASE (v410 bear filter FIRST, audited, causal): on the FULL BTC 4h opens
  history, `MA1200[T] = rolling(1200, min_periods=600).mean()` of
  `open[T]` inclusive; `bear[T] = open[T] < MA1200[T]` (NaN -> False).
  BASE weights: `w_b = w_raw` except longs (`w_raw > 0`) on bear bars are
  `0.5 * w_raw`. Shorts/flats unchanged. Reindexed to the grid.
- RULE (fixed): `w_r[T,s] = 0.5 * w_b[T,s]` if `in_exp(T)` else `w_b[T,s]`
  (both sides, longs and shorts; flats stay 0).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- Costs (exactly as oc_dvolshort): maker 0.0002 per unit turnover.
  Per (T, s) in grid order: `cost[T,s] = 0.0002 * |w[T,s] - w_prev[s]|`
  with `w_prev` = the previous grid bar's weight for the same sym (first
  grid bar: prev = 0). Same formula applied to the rule path with its own
  `w_r` prev. Net cell P&L: `pnl_b = w_b * R1 - cost_b`,
  `pnl_r = w_r * R1 - cost_r`. No funding, vol target, governor, sleeve,
  SL/TP, or compounding across bars in the per-cell sums; the equity path
  below compounds per-bar portfolio returns.
- Book path per variant: per-bar portfolio return
  `rp[T] = sum_s pnl[T,s]` over the 5 coins. Per anchor year, equity is
  reset to 1.0 at the year's first bar and compounded in grid order:
  `eq[i+1] = eq[i] * (1 + rp[T_i])`. Full 5y path compounds the same way
  from the first bar of year 1 (context only). maxDD of a path =
  `max_{peak<trough} (1 - eq_trough / eq_peak)` (peak running maximum
  strictly before the trough). Worst week = minimum 42-bar (7-day)
  compounded return inside the year: `min_{i>=42} (eq[i]/eq[i-42] - 1)`.
- Expiry-window attribution: `win_pnl_b = sum pnl_b` over bars with
  `in_exp(T)` in the year; `win_pnl_r` likewise; `out_pnl_*` over the
  complement. `win + out = total` per variant by construction.

## Evaluation (fixed here)

- Per anchor year report: `n_bars`, expiry-window share of bars;
  book P&L net on expiry-window bars base vs rule; total book P&L base vs
  rule (net, all rows); retention = rule/base (None if base <= 0; then
  pass iff rule >= base); worst week base vs rule; maxDD base vs rule
  (per-year reset paths). Full-path maxDD/total base vs rule as context
  (not part of the rule).
- DECISION RULE (from the assignment, overrides the tournament default):
  PROMISING only if (a) book maxDD not worse (`rule <= base`) in >= 4/5
  years, AND (b) total book P&L >= 98% of base in >= 4/5 years, where
  (b) per year = `rule >= 0.98 * base` if `base > 0`, else `rule >= base`.
  One-line verdict. The default tournament LOYO rule is N/A here by
  construction: the rule has no fitted parameter (pure calendar + fixed
  0.5 factor), so there is nothing to leave out.
- Cost context: weights average << 1, so per-cell bps overstate portfolio
  impact; the portfolio sums and equity paths above are the scale that
  matters.

## Causality / alignment tests (tests/test_oc_expirybook.py)

- test_expiry_calendar_hand_checked: explicit dates: Sep 2025 -> Fri
  2025-09-26 08:00 UTC; Feb 2024 (leap) -> Fri 2024-02-23 08:00 UTC;
  Jun 2026 -> Fri 2026-06-26 08:00 UTC; every expiry is a Friday 08:00 UTC;
  window flags equal `[E-48h, E)` membership.
- test_rule_math: rule weights are exactly 0.5x base on expiry-window bars
  (both sides) and bit-identical off-window; window flags need no market
  data (pure timestamps).
- test_bear_matches_v410: bear flags match rolling(1200, min 600) on full
  BTC opens (NaN -> False); BASE longs halved in bear, shorts/flats
  unchanged; BASE matches raw book + filter on sampled rows.
- test_turnover_cost_and_partition: per-sym costs equal
  0.0002*|w - w_prev| (first prev = 0) on both paths; anchors partition
  the grid without gaps/overlaps; window + complement P&L sums to totals;
  decision counts match the rule.

## Deliverables

`research/tournament/oc_expirybook/`: PLAN.md (this file),
`compute_expirybook.py`, `panel.parquet` (per-(T,sym) weights, flags,
forwards, net cells; small), `results.json`, `REPORT.md` (tables +
one-line verdict). No tuning on results; any post-hoc change logged in
REPORT.md. No commits. LIGHT job: one process, 4h inputs only (no 1m),
RAM < 1 GB.
