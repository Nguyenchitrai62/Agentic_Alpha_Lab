# oc_bookbrake — PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Implements idea #17 ("BOOK loss-cluster brake") EXACTLY as described in
`docs/opencode/OPENCODE_W_oc_bookbrake.md`. This PLAN is written before any
brake outcome is computed. Single fixed rule, no fitted parameter.

## Hypothesis

oc_ddanat17 (`research/tournament/oc_ddanat17/REPORT.md`) shows two of the
five big D17BF drawdowns are book-led bleeds (2022-02/03 book long+short
-7.5%, 2023-07/10 short squeeze + long bleed -10%), unlike dip cascades.
Book losses arrive in clusters (churn against a slow momentum book). Halving
ALL book targets for bars whose prior 72h saw >= 3 losing book trades close
should cut the book path's max drawdown at small yearly-P&L cost, because
most bars (and most P&L) fall outside loss clusters.

## Inputs (read-only, never edited)

- Books: `research_books_d2` rebuilt EXACTLY as `scripts/forward_v205.py`
  (`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2` with A=`member_A_O1_orders`,
  Aq=`member_Aq_O1_orders`, B=`member_B_tv`, Bq=`member_Bq_tv`;
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2` with D=`members_v154[D]`,
  Dq=`members_quarterly_D`; union index, missing -> 0.0) from
  `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override of
  the tournament-harness dev cutoff; all five years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (two small 4h frames only).

## Exact causal definitions (fixed now, before seeing numbers)

- BOUND = 2026-09-24 00:00 UTC. Grid = inner join of books index with opens
  index (dropna all), sorted 4h, restricted to bars with
  `open[t] < BOUND` and `open[t+1] <= BOUND`. Weight `w_c[t]` is known at the
  close of bar `t`.
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. Every scored
  bar has its forward return inside the bound.
- Turnover (L1, undrifted — disclosed simplification as in oc_bookvol):
  `TO_base[t] = sum_c |w_c[t] - w_c[t-1]|`, first grid bar vs flat 0.
  Cost `0.0005 * TO[t]` (0.05% per unit turnover, as assigned).
  Base net: `pn_base[t] = sum_c w_c[t]*r_c[t] - 0.0005*TO_base[t]`.
- BOOK TRADE (per coin, on BASE weights only — disclosed, no recursion):
  with `sgn[t] = sign(w_c[t])` (exact `0.0` = flat; `|w| < 1e-12` treated as
  flat), a trade is a maximal run `[a..b]` of scored bars with constant
  nonzero sign. Entry = `a` (prior bar flat or opposite sign), exit = `b`.
  Trade net (gross + its own turnover: entry leg `|w[a]|`, intra moves,
  flatten leg `|w[b]|`; a direct flip's `|diff|` is split exactly into the
  closing flatten leg and the opening leg, so trade costs partition the
  vectorised turnover):
  `net_k = sum_{t=a..b} w_c[t]*r_c[t]
  - 0.0005*(|w_c[a]| + sum_{t=a+1..b}|w_c[t]-w_c[t-1]| + |w_c[b]|)`.
  LOSS iff `net_k < 0` strictly (zero is not a loss).
  Closure time `c_k = open[b+1]` (the first grid-bar open after the exit bar;
  known then because `r[b]` is known at `open[b+1]` and `w[a],w[b]` were known
  at their closes). A trade ending on the last scored bar has no `b+1` grid
  bar and yields no closure event.
- BRAKE (fixed single value, causal, derived from BASE trades only):
  at holding bar start `T = open[t]`, let
  `N[t] = #{closures c_k (any coin) : T - 72h <= c_k < T}` (strictly before T).
  `scale[t] = 0.5` if `N[t] >= 3`, else `1.0`. All five coins share the same
  `scale[t]` (it multiplies ALL book targets for that bar).
- Braked weights `ws_c[t] = scale[t]*w_c[t]` (same sign as base, so leg
  membership is unchanged). Braked net
  `pn_brake[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO_brake[t]` with
  `TO_brake[t] = sum_c |ws_c[t]-ws_c[t-1]|`, first bar vs flat 0.
- Equity: compounded from 1.0 at the grid start,
  `eq[t+1] = eq[t]*(1+pn[t])` (weights are fractions of equity).
- Anchor years: `A_k = 2021-09-24 .. 2025-09-24`, partition `[A_k, A_{k+1})`
  for k=0..3 and `[A_4, A_4+365d)` for the last (leap-day fix as in
  oc_bookic: literal +365d for all would orphan 6 bars; fixed here before
  seeing outcomes). Masks keyed by bar `open_time`.
- Per (variant, year) on year bars: net return `= prod(1+pn)-1`; maxDD on the
  year-rebased equity (start 1.0): `max(1 - eq/running-peak)`; worst week =
  minimum compounded 42-bar (7-day) net return over all 42-consecutive-bar
  windows fully inside the year; brake-on share = `mean(scale==0.5)`.
- Legs (descriptive, same stats): long-leg gross
  `lg_base[t] = sum_{c:w_c[t]>0} w_c[t]*r_c[t]`,
  `lg_brake[t] = sum_{c:ws_c[t]>0} ws_c[t]*r_c[t]` (same for shorts with `<`);
  leg equity compounded from leg gross only — turnover costs are NOT
  allocated to legs (disclosed, as in oc_bullshort); costs live at book level.

## Decision rule (assignment-specific, fixed now)

- PROMISING only if BOTH hold on the NET book path (with 0.05% turnover):
  (a) `DD_brake < DD_base` strictly (tolerance 0) in >= 4 of 5 anchor years,
  AND (b) `Ret_brake >= Ret_base` (not lower, tolerance 0) in >= 3 of 5 years.
  NaN on either side counts as FAIL. LOYO is not needed (no fitted parameter).
- This replaces the default same-sign/LOO rule. One-line verdict in REPORT.md
  (PROMISING / NOT PROMISING).

## Resources / constraints

- Write ONLY to `research/tournament/oc_bookbrake/`
  (+ `tests/test_oc_bookbrake.py`). No commits, no edits outside these paths.
- One process; only 4h opens + book parquets are loaded. No 1m data.

## Outputs

- `research/tournament/oc_bookbrake/`: PLAN.md (this file),
  `compute_bookbrake.py`, `results.json`, REPORT.md (tables + one-line
  verdict). No tuning on results; any post-hoc change logged in REPORT.md.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
