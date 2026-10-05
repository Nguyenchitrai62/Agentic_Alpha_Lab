# oc_rips PLAN (pre-registered BEFORE any outcome statistic)

## Question

The dip ladder (limit BUYS k sigma_4h below each 4h bar open) is the BOT's dip
sleeve; its mirror (limit SELLS k sigma_4h ABOVE the open, "rip fade") lost on
average in earlier studies. It was never tested CONDITIONAL on a slow regime.
The dip sleeve is weak exactly in bear/range years (2021-22, 2022-23, 2025-26),
so a regime-conditional short-side ladder could complement it.

## Universe, grid, sigma (fixed)

- Coins (5 majors): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- 1m klines: `data/raw/btc_intraday_20260924` (BTC) and
  `data/raw/majors_intraday_20260924` (others). Minutes used: t < 2026-09-24
  00:00 UTC. Missing minutes are skipped (no fill/exit on NaN rows).
- Standard 4h grid: bars starting 00,04,08,12,16,20 UTC (pandas `floor("4h")`
  from midnight, same as the rolling_anchor_dips diagnostic). A bar has 240
  minutes with offsets 0..239; next-bar open is offset 240.
- sigma_4h per coin, known at the bar open: let O_b be 4h bar opens (first 1m
  open of each grid bar). Simple returns r_b = O_b / O_{b-1} - 1. Then
  sigma(b) = std of {r_{b-359}..r_b} (360 bars, min_periods 120, ddof=1).
  r_b uses only O_b and O_{b-1}, both known at bar b's open, so sigma(b) is
  known at the bar open. Bars with <120 returns of history are skipped.
- Rungs k in {2.5, 3.0, 4.0}. Each (coin, bar, k) is an independent rung with
  at most one fill.

## Rip ladder (short side) and dip reference (long side)

Levels (s = sigma(b), O = bar open):
- RIP level: L_rip = O * (1 + k*s). Resting limit SELL, live offsets 16..238
  inclusive (223 minutes). Fill at the FIRST minute f in the window with
  high(f) > L_rip (strict trade-through). Fill price = L_rip, maker 0.0002.
- DIP reference level (same code mirrored): L_dip = O * (1 - k*s). Resting
  limit BUY, same window. Fill at first minute with low(f) < L_dip at L_dip,
  maker 0.0002.

Exits (short notation; dip is the exact mirror with up/down flipped).
Let s, L be the rung's sigma and level, f the fill minute index, b0 the bar
start minute index (so the bar covers b0..b0+239, next-bar open b0+240):
- TP: TP_px = L * (1 - 1*s). From minute f+1 onward, if low(t) < TP_px
  (strict trade-through) the position exits at TP_px, maker 0.0002.
- STOP-CLOSE: SC_px = L * (1 + 4*s). Post-fill minutes t>f are grouped into
  non-overlapping 5-minute blocks relative to the fill: [f+1..f+5],
  [f+6..f+10], ... Block close = close of the block's last minute. At each
  completed block ending at minute c (c+1 exists), if block close > SC_px,
  exit at open(c+1), taker 0.00055. Blocks are truncated at the bar end:
  a block ending beyond b0+240 is not evaluated as a stop (timeout applies).
- BACKSTOP (touch): BS_px = L * (1 + 8*s). From minute f+1 onward, if
  high(t) >= BS_px, exit in minute t at max(BS_px, open(t)) (gap pays the
  open), taker 0.00055.
- TIMEOUT: otherwise exit at open(b0+240) (the next bar open), taker 0.00055.
  If open(b0+240) is NaN/missing, the fill is dropped (no outcome).
- Priority (same-minute stop-first): at each minute t>f, check backstop touch
  FIRST (stop wins over a TP touch in the same minute). A completed-block
  stop-close signal outranks a TP touch in the exit minute c+1 (the stop was
  already triggered). User gate rule (stop-first in one bar) is respected.
- Shorts pay no funding (gate rule: shorts receive nothing, pay nothing).
  Funding ignored for the dip reference too (holds are <4h by construction).

Net return per fill (short, equal notional, full-notional costs):
- TP exit: net = (L - TP_px)/L - 0.0002 - 0.0002.
- Stop/timeout exit at Px: net = (L - Px)/L - 0.0002 - 0.00055.
Dip mirror: net = (Px - L)/L - 0.0002 - exit fee (0.0002 TP, 0.00055 stop/time).
Win = net > 0 (strictly).

## Regimes at the bar open (daily, strictly before the day)

Regime day D = floor(bar open, calendar day, UTC). Every regime value labelled
D uses ONLY data with timestamps < D 00:00 UTC (same causal day rule as
research/tournament/oc_regime/regime.py; formulas below match its definitions,
recomputed from 1m closes so they cover the full span to 2026-09-24):
- Daily close C(sym, day E) = close of the last non-NaN 1m bar with
  open_time < (E+1) 00:00 UTC (i.e. the day's last minute).
- trend90 = log(C_BTC(D-1) / C_BTC(D-91)) (needs 91 daily closes ending D-1).
- below200 = C_BTC(D-1) < mean(C_BTC over the 200 days ending D-1).
- volratio = std of BTC daily log returns over the 30 days ending D-1 divided
  by the median of trailing 30d stds over the 365 windows ending <= D-1
  (same construction as regime.py: 394d window, median of last 365 values).
- breadth50 = fraction of the 5 majors with C(sym,D-1) above their 50d SMA
  (mean of daily closes over the 50 days ending D-1; coin counted only if all
  50 closes are non-NaN; NaN if no coin qualifies).
NaN regime -> the conditional rule is inactive for that bar (no rips).
Cross-check: trend90/volratio/breadth50 are compared against
oc_regime/regimes_daily.parquet over their overlap (2021-01-01..2026-09-01);
the parquet is NOT an input (it ends 2026-09-01, before the test path ends).

## Pre-registered conditional rules (at most 3)

- R1 = rips only when below200 is True (BTC below its 200-day mean).
- R2 = rips only when trend90 < 0 AND volratio < 1.0 (downtrend, calm vol).
- R3 = rips only when breadth50 < 0.4 (narrow/weak breadth).
UNCOND = all rips (no gate). DIP = mirrored dip reference (no gate).
The rule is evaluated per bar from that bar's regime day; fills inherit the
rule of their bar. No threshold was fit on outcomes (0.4/1.0/0 are the
assignment's example constants, fixed here).

## Scoring (fixed)

- Anchor years: fills with fill minute t in [A, A+365d) for
  A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24} (UTC).
  Per (rule x year), pooling all 5 coins x 3 k rungs: fills (n), mean net
  return per fill in bps (1e4 * mean(net)), win rate (mean(net>0)), sum of net
  returns (equal-notional units), daily-sum max DD (group net by fill date
  UTC, cumulative sum over the 5-year path restricted to that rule, max
  peak-to-trough; full-path DD reported per rule plus the per-year sums).
- 5-year sum = sum of net over all fills in the 5 anchor years.
- Leave-one-year-out sign check: for each rule and each held-out year h, sign
  of mean_h vs sign of the pooled mean of the other 4 years; report matches/5.
- Correlation: Pearson correlation of daily P&L (fill-date sums, all 5 years,
  days aligned, zeros for empty days) between each rip rule and DIP.
- DECISION RULE (fixed, from the assignment): a rule is PROMISING only if
  (i) its mean net return is > +5 bps in >= 4 of 5 years, AND (ii) its 5-year
  sum is positive, AND (iii) its daily-sum DD is below 2x the unconditional
  dip ladder's daily-sum DD (DIP computed with the same code, mirrored).
  All three must hold; otherwise NOT PROMISING.

## Causality / correctness tests (tests/test_oc_rips.py)

- test_regime_truncation: 20 days (seed 7) in 2022-01..2026-08; recompute the 4
  regime values from 1m data truncated to t < day and assert equality with the
  full-panel row (uses the study's own regime builder, not the parquet).
- test_fill_tp / test_stop_backstop / test_timeout: 3 hand-made synthetic
  minute paths exercising TP, backstop-stop (incl. same-minute stop-first over
  TP), and timeout exits with exact expected nets.
- All backtest helpers used by the tests live in research/tournament/oc_rips/.

## Deliverables

research/tournament/oc_rips/: PLAN.md (this file), regimes.py, backtest.py,
run.py, results.json, REPORT.md. tests/test_oc_rips.py. One heavy process,
RAM < 2.5 GB (one coin in memory at a time), no commits, no edits outside the
two allowed paths. Data up to 2026-09-24 00:00 UTC may be used; any finding
needs prospective validation. Post-hoc changes, if any, are logged in
REPORT.md.
