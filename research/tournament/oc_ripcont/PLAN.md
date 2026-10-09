# oc_ripcont PLAN (pre-registered BEFORE any outcome statistic)

## Question

oc_rips sold rips and LOST in every regime (win 51-69% but negative means:
small TP wins vs large stop/timeout losses) -> rips tend to CONTINUE. The mirror
was never tested: after a rip, does a limit bid on the first pullback earn
momentum continuation inside the bar? Long sleeve, fills in up-moves (different
times than the dip ladder -> diversification), maker entries.

## Universe, grids, sigma (fixed)

- Coins (5 majors): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, Binance USD-M.
- 1m klines: `data/raw/btc_intraday_20260924` (BTC `klines_1m_*.parquet`) and
  `data/raw/majors_intraday_20260924` (`{SYM}_1m_*.parquet`). Minutes used:
  t < 2026-09-24 00:00 UTC. Missing minutes (NaN) are skipped: no trigger /
  fill / exit on NaN rows; a bar whose open O is NaN/non-positive or whose
  sigma is NaN/non-positive is skipped.
- Four clock grids (shift s = 0,1,2,3 h): bars start at minutes with
  (t - s hours) floored to 4h == t, i.e. grids {00,04,...,20} + s hours.
  Each bar has 240 minutes, offsets 0..239; next-bar open is offset 240.
  Each clock is 1/4 of the capital (4-phase convention). At most one entry
  per (coin, bar, clock).
- sigma per (coin, clock, bar), known at the bar open T: let O_b be the 4h bar
  opens of that clock (first 1m open of each grid bar). Log returns
  r_b = ln(O_b / O_{b-1}). sigma(b) = std of {r_{b-359}..r_b} (360 bars,
  min_periods 120, ddof=1). r_b uses only O_b and O_{b-1}, both known at bar
  b's open, so sigma(b) is known at T. Bars with <120 returns are skipped.
  NOTE: oc_rips used simple returns; the difference is second-order (logged
  here because the assignment says log returns). Same 360/120 window.

## Trigger, entry, exits (fixed; reuse oc_rips data loading/exit patterns)

Levels (s = sigma(b), O = bar open at T):
- Trigger: first minute m with offset 5..239 inside [T, T+4h) with
  high(m) >= O * exp(+k * s). Minutes 0..4 are never fills (pipeline delay;
  gate: no fill in first 5 min after a 4h close).
- Entry: from minute m+1 a resting BUY limit at L = O * exp((k-1.0) * s)
  (one-sigma pullback below the trigger), valid offsets m+1..199. Fill at the
  FIRST minute f in that window with low(f) < L (strict trade-through).
  Fill price = L, maker 0.0002. If no minute trades through, no fill.
  One entry per coin per bar (first trigger only; later re-rips in the same
  bar are ignored).
- Exits (from minute f+1 to offset 239 inclusive):
  - TP: TP_px = L * exp(+0.75 * s). If high(t) > TP_px (strict trade-through)
    exit at TP_px, maker 0.0002.
  - SL: SL_px = L * exp(-1.0 * s). If low(t) <= SL_px (touch) exit at SL_px,
    taker 0.00055 (market stop, filled at the stop price).
  - Same-minute priority: STOP FIRST (SL checked before TP each minute).
  - TIMEOUT: otherwise exit at open(T+4h) (offset 240), taker 0.00055.
    If that open is NaN/missing, the fill is dropped (no outcome).
- Funding (gate): longs pay 0.0001 per 8h settlement (00/08/16 UTC) with
  fill_time < t_settle <= exit_time. Shorts N/A (all positions long).
- Net per fill (full-notional, long):
  net = (exit_px - L) / L - 0.0002 - exit_fee - funding,
  exit_fee = 0.0002 (TP) or 0.00055 (SL/timeout). Win = net > 0 strictly.
- Size: notional 0.10 x sub-account (clock) equity per fill, fixed. A clock is
  1/4 of total equity, so one fill = 0.025 x total equity. Per-year "sum" is
  reported both as raw sum(net) and scaled total-equity sum = 0.025 * sum(net).
  Per-fill mean bps = 1e4 * mean(net). Daily-sum DD groups scaled daily sums
  by fill date (UTC) over the dev path.

## Pre-registered variants (at most 3; ONLY these)

- C1: k = 2.0 (all bars).
- C2: k = 3.0 (all bars).
- C3: C1 gated on the deployed book being long that coin at the bar open.
  DROPPED before any computation: no causal per-bar deployed-book weight
  exists for all four clocks across 2021-2026. `scripts/forward_v205.py`
  `live_books()` is prospective-only (shadow log from 2026-09-27, no dev
  coverage); `research_books_*` member parquets are in-sample ensemble outputs
  with no per-anchor embargo (not a walk-forward causal book); the v376
  `r2_table_s*.parquet` files are dip-rung tables, not book weights. Per the
  assignment ("if no causal per-bar book weight exists for all four clocks,
  drop C3 and say why - do not invent one"), C3 is NOT tested. No replacement
  variant is added.

## Placebo (fixed)

- For each of C1/C2, on dev4 years only: per (coin, anchor-year) let N_cy =
  actual fills. Each of 200 draws picks N_cy random (bar, minute) pairs:
  uniform random bar with T in [A, A+365d) of the same year and same clock
  mixture as the actual fills (bars pooled across the 4 clocks), random minute
  offset uniform 5..199. Limit L_pbo = 1m open of that minute; entry assumed
  filled immediately at L_pbo (maker 0.0002) so every draw has the same N_cy
  fills (this isolates the trigger/pullback edge; documented limitation:
  placebo fills do not require a trade-through). Exits use the same bar's
  sigma with the same TP/SL multiples (TP = L*exp(0.75s), SL = L*exp(-1.0s),
  timeout next-bar open taker) and the same funding rule. Seed 7.
- Statistic: pooled dev4 mean net bps per placebo draw. Report the actual
  variant's pooled dev4 mean percentile vs the 200 placebo means
  (percentile = fraction of placebo means <= actual, x100), plus the placebo
  mean-of-means and 95th percentile. Gate needs percentile >= 95.

## Scoring (fixed)

- Anchor years: fills with fill minute t in [A, A+365d) for
  A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24} = dev4, plus
  2025-09-24 = most-recent year. Dev4 is computed first for C1+C2; the
  most-recent year is scored ONCE, only for the chosen variant (and the dip
  reference row below), after the choice is frozen.
- Per (variant x year), pooling 5 coins x 4 clocks: fills n, mean net bps/fill,
  win rate, raw sum(net), scaled sum (0.025x), TP/SL/timeout shares, daily-sum
  max DD (fill-date sums, cumulative over the dev4 path for the gate; full
  dev4 DD reported per variant). Dev sum = sum over dev4 fills.
- Daily P&L correlation: Pearson of variant daily scaled P&L (fill-date sums,
  dev4 days aligned, zeros for empty days) vs G2 4-phase hourly-equity daily
  returns (R2B1D17BFG2 from v421_runs.pkl via v388.hourly mix; labelled
  alternative allowed by the assignment since oc_rips dip fills were not
  persisted). Dip scale reference (no recompute): oc_rips mirrored dip 5y sum
  +11.68, dip daily-sum DD 1.28 (results.json DIP _5y dd = 1.2796); the gate
  uses 2 x 1.2796 = 2.5592 as the DD cap.
- DECISION (assignment gate): PROMISING only if ALL hold on dev4:
  (i) mean net/fill > +5 bps in >= 3 of 4 dev years, AND (ii) dev sum > 0,
  AND (iii) placebo percentile >= 95, AND (iv) daily-sum DD < 2 x dip DD
  (2.5592). Otherwise NOT PROMISING.
- CHOICE RULE (pre-registered): if exactly one of C1/C2 is PROMISING it is
  chosen. If both are PROMISING, pick the higher dev4 WORST-year mean bps
  (ties -> higher dev4 mean). If neither is PROMISING, no overlay; the
  "chosen variant" for the single most-recent-year scoring is still the one
  with the higher dev4 worst-year mean bps (ties -> higher mean), labelled as
  non-promising. The most-recent year is never used to pick.
- OVERLAY (only if PROMISING): sleeve on G2 4-phase hourly equity at fixed
  notional 0.05 x total equity per fill: hourly dSleeve(h) = 0.05 x sum of
  nets exiting in hour h (exit-time sums; fixed-notional screen, sleeve
  notional does not compound intra-year - labelled). A(t) = A(t-1)(1+r_bot)
  + dSleeve, with r_bot from the stored G2 mix. Report per-year 4-phase reset
  metric (reset to 1.0 at each anchor, same as reset_metric.year_reset),
  yearly + full-path DD (max of marked/close convention: here close-only path
  plus the 1m-marked convention is N/A for the sleeve screen - labelled),
  vs G2. Book/dip engine is NOT modified (screen only).

## G2 baseline (must reproduce exactly before any overlay)

- Deployed reference G2 = R2B1D17BFG2 in v421 (v421_result.json): 5.41 %/month
  4-phase reset metric, max yearly DD 16.91, full-path DD 16.82. Hourly equity
  from v421_runs.pkl via v388.hourly + 4-phase mean. f=0 must reproduce the
  yearly (R, DD) rows to the digit before any overlay; if not, stop.

## Causality / correctness tests (tests/test_oc_ripcont.py)

- test_sigma_truncation: synthetic bar-open series; sigma from truncated vs
  full panel equal; last-360/log/min_periods behaviour incl. NaN when <120.
- test_trigger_pullback_tp / test_stop_first / test_timeout_funding: hand-made
  1m paths with exact expected L/TP/SL/fill/exit/net (incl. same-minute
  stop-first over TP, timeout taker, one funding settlement deduction).
- test_no_fill_first5min_or_no_pullback: no trigger in offsets 0..4 alone;
  trigger with no pullback -> no fill.
- All backtest helpers used by tests live in research/tournament/oc_ripcont/.

## Deliverables

research/tournament/oc_ripcont/: PLAN.md (this file), backtest.py, run.py,
results.json, REPORT.md. tests/test_oc_ripcont.py. Heavy run via the shared
semaphore (scripts/heavy_slot.py, never --leader), one coin in memory at a
time. No edits outside the two allowed paths. Data < 2026-09-24 only. Post-hoc
changes, if any, logged in REPORT.md as disclosed extra rows (original kept).
