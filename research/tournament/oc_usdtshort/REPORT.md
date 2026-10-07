# oc_usdtshort REPORT: USDT/USD premium BOOK SHORT-leg tilt (idea #74)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_usdtprem's formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = raw book + v410 bear-long filter FIRST (BTC-only,
longs x0.5 when BTC 4h open < 1200-bar mean, open[T] inclusive). RULE = BASE
with SHORT targets x1.15 when USDT-premium `z < -1` (fiat outflow), x0.85
when `z > 1`, else x1.0 (one market-wide signal for all 5 coins;
longs/flats/NaN-z bit-identical). Signal: identical to oc_usdtprem
(Coinbase Exchange USDT-USD 1h, `prem = close - 1`,
`mean24 = rolling(24, min 20)`, `z = (mean24 - trailing-2160 mean)/std(ddof=1)`
current excluded, as-of = last hourly row with end strictly before T
(`end <= T - 1s`; for 4h T the bar `[T-2h, T-1h]`)). Screen = open-to-open 4h
returns with gate costs 0.0005/unit turnover (assignment value, oc_dvolshort
mechanics, each path its own prev chain): net cell = `w*R1 - 0.0005*|w-w_prev|`
per sym (first prev = 0). Short-leg sums use fixed BASE-sign membership so
base vs rule compare identical rows. Equity per year reset to 1 and compounded
as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. Coverage of `z` is 100% all years (USDT history from
2021-05-04, fully warmed up before 2021-09-24). Rule bar-mult runs: 357
maximal constant segments over the 10955-bar series.

## Verdict

NOT PROMISING (stricter screen): total book P&L >= base in 5/5 years and the
5y P&L delta beats the placebo p95, but maxDD not worse in only 3/5 years
(needs >= 4/5) and the full-path DD delta (-0.0005) misses the placebo p05
(-0.0040; percentile 28.2).

## Per-year screen (net, portfolio-return units; costs included)

| year | coverage | share shorts tilted (up x1.15 / down x0.85) | short P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | P&L >= base | DD not worse |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 1.0 | 0.353 (0.291/0.062) | 0.132620 / 0.141944 | 0.278895 / 0.288219 | -0.055289 / -0.055289 | 0.092278 / 0.094648 | yes | no |
| 22-23 | 1.0 | 0.178 (0.132/0.046) | 0.015585 / 0.020552 | 0.235444 / 0.240407 | -0.047268 / -0.047268 | 0.073721 / 0.070933 | yes | yes |
| 23-24 | 1.0 | 0.375 (0.205/0.169) | -0.050913 / -0.041034 | 0.544150 / 0.554038 | -0.069471 / -0.066132 | 0.087902 / 0.083528 | yes | yes |
| 24-25 | 1.0 | 0.286 (0.169/0.117) | 0.037334 / 0.037434 | 0.517693 / 0.517787 | -0.045930 / -0.045575 | 0.065296 / 0.067906 | yes | no |
| 25-26 | 1.0 | 0.478 (0.360/0.118) | 0.168207 / 0.190255 | 0.394724 / 0.416776 | -0.075345 / -0.075345 | 0.087166 / 0.087026 | yes | yes |

Counts: P&L >= base 5/5; DD not worse 3/5. Long legs unaffected by
construction (5y long-leg diff <= 6.9e-06, from the rule path's own turnover
chain at short/long flip bars only). Full 5y path (context, compounded from
year-1 start): total P&L 1.970907 -> 2.017227 rule (5y delta +0.046320);
maxDD 0.104644 -> 0.104118 rule (delta -0.000526).

## Placebo (500 full-series block-shuffles by run, seeds 9100+i, oc_premexpo shape)

Row counts per mult level exact per draw; only timing shuffled. 5y P&L deltas:
p95 gate = 0.026595; real +0.046320 -> percentile 99.6 -> PASS. Full-path DD
deltas (more negative = better): p05 gate = -0.003970; real -0.000526 ->
percentile 28.2 -> FAIL.

Read: the outflow-tilted short leg adds P&L in every year (2021 +0.009,
2022 +0.005, 2023 +0.010, 2024 +0.0001, 2025 +0.022; timing beats 99.6% of
shuffles) but drawdown control is inconsistent -- per-year DD worsens in
2021 (+0.0024) and 2024 (+0.0026), and the full-path DD improvement is
ordinary under the timing placebo. Return edge without the required
drawdown control.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the decision
   rule. PLAN.md was written before `compute_usdtshort.py` ran.
2. Costs are the assignment's 0.0005/unit (oc_dvolshort mechanics: per-sym
   chain, first prev = 0, each path its own chain; verified in
   tests/test_oc_usdtshort.py).
3. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
   funding, SL/TP, or engine limit path). Needs prospective validation; all
   five years were available when the idea was scored.
4. USDT-USD listed 2021-05-04 on Coinbase, so the 90d z needs warm-up;
   coverage is still 100% on the scored grid (2021-09-24 on).

## One-line verdict

NOT PROMISING (stricter screen): short-tilt P&L >= base 5/5 with 5y delta
+0.046 beating placebo p95, but DD not worse only 3/5 and full-path DD delta
-0.0005 missing placebo p05 -- return edge, no drawdown control.
