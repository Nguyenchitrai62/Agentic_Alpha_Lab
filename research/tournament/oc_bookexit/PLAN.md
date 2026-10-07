# oc_bookexit PLAN — learned exit levels for BOOK trades (idea #31, pre-registered BEFORE any outcome is computed, 2026-10-06)

## Hypothesis
Book trade win rate is ~0.515 (oc_kpi) while dip rungs use learned TP agents.
Episodes unlikely to run +1.5 ATR before -1.0 ATR should bank a small win with
a tight take-profit (+1.0 ATR) instead of riding to the default exit. A
walk-forward HistGradientBoostingClassifier from entry-time state should
identify those episodes and raise book win rate without lowering book P&L.

## Inputs (read-only, never edited)
- Books: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `scripts/forward_v205.py` (same files, same math) from
  `artifacts/research/engine_real/` (members + opens).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- 4h high/low/close: `research/tournament/ext/hourly_ext.parquet` (majors
  only: BTC/ETH/SOL/BNB/XRP), each 4h bar T aggregates hours T..T+3
  (open=first hour open, high=max high, low=min low, close=hour-T+3 close;
  NaN if any of the 4 hours missing).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override of
  the old RULES.md hidden-year cut; all five years are research data;
  findings need prospective validation). No 1m data, one process, RAM < 1 GB.

## Exact causal definitions (fixed now, before seeing numbers)
- BOUND = 2026-09-24 00:00 UTC. Grid = inner join of books index with opens
  index (dropna all), asserted regular 4h, scored bars `open[t] < BOUND` with
  `open[t+1] <= BOUND`. Next-bar simple return `r_c[t] = open_c[t+1]/open_c[t]-1`.
  Weight `w_c[t]` is known at the close of bar `t`.
- ATR4h: per coin, true range `TR[i] = max(high[i]-low[i], |high[i]-close[i-1]|,
  |low[i]-close[i-1]|)` on the hourly-aggregated 4h bars;
  `ATR[t] = mean(TR[t-13..t])` (14-bar SMA, NaN unless all 14 present).
  ATR is known at the close of bar `t`.
- BOOK TRADE (per coin, on base weights): maximal run `[a..b]` of scored bars
  with constant nonzero sign (`|w| < 1e-12` = flat), exactly as oc_bookbrake.
  Entry bar `a` (opens at `open[a]`), exit bar `b`, closure `close_t=open[b+1]`
  (episodes ending on the last scored bar have no closure and are EXCLUDED
  from train and test). Default net (0.05% per unit turnover, FEE=0.0005):
  `net = sum_{t=a..b} w[t]*r[t] - FEE*(|w[a]| + sum|w[t]-w[t-1]| + |w[b]|)`.
- LABEL (uses the realised path; it is the prediction target, never a
  feature): with entry open `E=open[a]`, side `s=sign(w[a])`, `A=ATR[a-1]`
  (close strictly before `open[a]`; episode excluded if NaN):
  long: up-touch = first bar in `[a..b]` with `high >= E+1.5A`,
  down-touch = first bar with `low <= E-1.0A`; label=1 iff up-touch exists
  and (no down-touch or up-bar < down-bar). Same-bar touch of both levels =
  adverse first -> label 0 (stop-first, as AGENTS.md). Mirrored for shorts.
  Episodes with missing HLC in `[a..b]` are excluded (count reported).
- ENTRY FEATURES (all computable at the close of bar `a-1`, i.e. before
  `open[a]`; episode excluded if any NaN, count reported):
  1. `wgt` = signed signal weight `w[a]`; 2. `abs_w` = `|w[a]|`;
  3. `vol4h` = trailing-360-bar std of 4h open-to-open returns as of bar
     `a-1` (min 120 bars); 4. `trend30d` = `open[a-1]/open[a-180]-1` (full
     180 bars required); 5. `btc_trend30d` = same for BTCUSDT;
  6. `hour` = `open[a].hour` in {0,4,8,12,16,20}; 7. `coin` = integer id
  (BNB=0, BTC=1, ETH=2, SOL=3, XRP=4).
- MODEL (fixed by assignment, no tuning): `HistGradientBoostingClassifier(
  max_depth=3, max_iter=200, min_samples_leaf=200)` on the 7 features.
- WALK-FORWARD: anchors `A_k = 2021-09-24 .. 2025-09-24`, test year
  `Y_k = [A_k, A_k+365d)` keyed by ENTRY bar `open[a]`. Train for year k =
  episodes with `close_t < A_k - 7 days` (strictly, causal). One model per
  year; predict test-year episodes; flagged iff predicted P(label=1) < 0.45.
- RULE: flagged episodes that touch `+1.0A` favourably (first bar in `[a..b]`
  with `high >= E+1.0A` long / `low <= E-1.0A` short):
  `rule_net = 1.0*(A/E)*|w[a]| - 2*FEE*|w[a]|` (bank the small win at entry
  size: entry + exit legs only, no intra churn — disclosed simplification).
  Flagged episodes never touching +1.0A, and all unflagged episodes:
  `rule_net = default net`.

## Statistics (fixed)
- Per test year k, rule vs default on entry-keyed episodes: n, label rate,
  flagged share (rule only), book P&L as SUM of episode nets and as
  compounded trade-equity `prod(1+net)-1` (close-ordered), win rate =
  `mean(net > 0)` (strict), book path = close-ordered cumprod year-rebased
  from 1.0 (spillover: episodes keyed by entry, ordered by close — disclosed),
  maxDD on that path, worst week = min trailing-7-day return on the
  daily-ffilled path (full 7-day windows inside the year only).
- Train size per year (after NaN exclusions) and full-period totals.
- Effect `D = P&L_rule - P&L_default` (sums) per year + leave-one-year-out
  means as supplementary context only.

## Decision rule (fixed, assignment-specific)
- PROMISING only if `P&L_rule >= P&L_default` in >= 4/5 years AND
  `win_rate_rule > win_rate_default` (strict) in >= 4/5 years.
- One-line verdict in REPORT.md (`PROMISING` / `NOT PROMISING`).

## Protocol
- PLAN.md written before any outcome computation. Then
  `compute_bookexit.py` -> `results.json`, then REPORT.md (tables + verdict).
- No commits; write ONLY under `research/tournament/oc_bookexit/`
  (+ `tests/test_oc_bookexit.py`).
