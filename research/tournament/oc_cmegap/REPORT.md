# oc_cmegap REPORT: CME weekend-gap fill as a BOOK tilt (idea #69)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort/oc_bookweekend); opens = v154 4h opens. BASE = raw book +
v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean,
min 600). Grid = 10955 bars (2021-09-24..2026-09-23 16:00 UTC; last bar
dropped, no forward open) x 5 coins = 54775 rows. Gap = Binance BTCUSDT 1m
`P(Sun reopen)/P(Fri close)-1` at the assignment's DST times (winter Fri
21:00/Sun 22:00 UTC, summer Fri 20:00/Sun 21:00 UTC; season by Friday date
in [2nd-Sun-Mar, 1st-Sun-Nov)); fill = first 1m trade-through of `P_fri`
after the reopen (low <= for up-gaps, high >= for down-gaps) within 72 h.
RULE: on large-gap active rows (first 4h row after reopen .. fill or +72h,
fill known strictly before T) longs x0.75 if gap > +2%, x1.25 if gap <
-2% (all coins, on bear-filtered longs); shorts/flats/small-gaps unchanged.
Screen = open-to-open 4h returns with 0.0005/unit turnover (each path own
prev, first prev = 0). Equity per year reset to 1, `eq *= 1 + sum_s pnl`;
maxDD peak-to-trough; worst week = min 42-bar return. Full tables in
`results.json`; `panel.parquet` per-(T,sym), `gaps.parquet` per weekend.
262 weekends enumerated (one pre-anchor 2021-09-17 weekend has no grid rows;
yearly counts use reopen-in-year, 261 total); 261/261 finite gaps (no
missing 1m bars); 58 large (`|gap|>2%`: 28 up, 30 down).

## Verdict

PROMISING (as assigned): total net book P&L RULE >= BASE in 4/5 years and
book maxDD not worse (RULE <= BASE) in 5/5 years.

## Per-year screen (net, portfolio-return units; costs included)

| year | weekends | gaps>2% | fill rate (large, 72h) | affected bars (share) | affected-rows P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | P&L>=base | DD not worse |
|---|---|---|---|---|---|---|---|---|---|---|
| 21-22 | 52 | 21 | 0.523810 | 233 (0.021269) | 0.068471 / 0.070234 | 0.278895 / 0.280429 | -0.055289 / -0.055289 | 0.092278 / 0.088802 | yes | yes |
| 22-23 | 52 | 7 | 0.428571 | 106 (0.009676) | -0.090788 / -0.073597 | 0.235444 / 0.252423 | -0.047268 / -0.047268 | 0.073721 / 0.073721 | yes | yes |
| 23-24 | 53 | 11 | 0.363636 | 171 (0.015609) | 0.082194 / 0.062532 | 0.544150 / 0.524267 | -0.069471 / -0.069471 | 0.087902 / 0.087683 | no | yes |
| 24-25 | 52 | 9 | 0.444444 | 110 (0.010041) | 0.071413 / 0.071763 | 0.517693 / 0.517873 | -0.045930 / -0.045930 | 0.065296 / 0.062229 | yes | yes |
| 25-26 | 52 | 10 | 0.700000 | 122 (0.011136) | 0.014778 / 0.021622 | 0.394724 / 0.401569 | -0.075345 / -0.076266 | 0.087166 / 0.086683 | yes | yes |

Counts: total-P&L not lower 4/5; DD not worse 5/5. LOYO stability
(descriptive, fixed calendar constants): pnl 4/5, dd 5/5. Full 5y path
(context, compounded from year-1 start): maxDD 0.104644 -> 0.104644
(unchanged); total P&L 1.970907 -> 1.976562 (+0.0057 over 5y).

Read: the tilt touches only ~1-2% of grid bars (max 18 4h bars per large
weekend, less when the gap fills early; 5 weekends fill before the first
row hence 0 affected bars). Where it acts it usually helps: affected-rows
P&L improves in 4/5 years (2022 loss shrinks by ~0.017, the largest total
gain; 2025 +0.007; 2021 +0.002; 2024 +0.0004) and only 2023 loses
(-0.0196 on affected rows, -0.0199 total, the single failing year). DD
never worsens (ties in 2022 where the affected window avoids the drawdown
bars; -0.35pp in 2021, -0.31pp in 2024). Worst-week changes are nil except
2025 (-0.0753 -> -0.0763, third decimal). Fill rates 0.36-0.70 confirm gaps
do fill within 72 h about half the time, but the tilt's edge does not come
from fill prediction (the window simply expires at +72h either way).

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, DST rule, gap/fill definitions,
   thresholds (+/-2%), multipliers (x0.75/x1.25), window (+72h), costs, or
   the decision rule. PLAN.md was written before `compute_cmegap.py` ran.
2. Correctness fix toward PLAN (verified, not outcome-driven): the first
   run built the 1m close lookup with `to_numpy()` object-array keys
   looked up by `np.datetime64`, so every gap came back NaN (n_gap = 0,
   rule identical to base). Fixed to a Timestamp-indexed Series with exact
   `open_time` lookup and re-ran once; gaps 261/261 finite. No hypothesis
   or parameter was touched.
3. 2023 is the single failing year on total P&L (rule -0.0199 below base
   on affected rows); the PASS rests on 2021/2022/2024/2025 plus a
   DD-only tie-or-win in every year. Effect size is small in portfolio
   units (weights << 1; +0.0057 total over 5y) - a tilt, not an edge.
4. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); 0.0005/unit turnover
   with each path's own prev. Gaps counted by reopen-in-year while
   affected P&L is by grid-row year (disclosed in PLAN; only boundary
   weekends differ). Needs prospective validation; in-sample
   walk-forward style (no fitted parameter, but all five years were
   available when scored).

## One-line verdict

PROMISING (as assigned): CME-gap long tilt (x0.75 up-gap / x1.25 down-gap
beyond +/-2% until 1m fill or 72h) keeps total book P&L >= base in 4/5
years with maxDD never worse in 5/5 (touches ~1-2% of bars; 2023 the only
losing year) - small tilt, not a return edge.
