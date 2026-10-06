# oc_usdtprem REPORT: USDT/USD premium BOOK inflow tilt (idea #71)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_cbpremium's formula); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = raw book + v410 bear-long filter FIRST (BTC-only,
longs x0.5 when BTC 4h open < 1200-bar mean, open[T] inclusive). RULE = BASE
with LONG targets x1.15 when USDT-premium `z > 1`, x0.85 when `z < -1`, else
x1.0 (one market-wide signal for all 5 coins; shorts/flats/NaN-z
bit-identical). Signal: Coinbase Exchange USDT-USD 1h
(`data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet`, 47240 rows,
2021-05-04 01:00 .. 2026-09-23 23:00 UTC, sha256
c6970f93...5e5c4269, 3 small gaps of 4/6/5 missing hours; Kraken fallback
not needed), `prem = close - 1`, `mean24 = rolling(24, min 20)`,
`z = (mean24 - trailing-2160 mean)/std(ddof=1)` current excluded, as-of =
last hourly row with end strictly before T (`end <= T - 1s`; for 4h T the
bar `[T-2h, T-1h]`). Screen = open-to-open 4h returns with gate costs
0.0005/unit turnover (assignment value, oc_dvolshort mechanics, each path
its own prev chain): net cell = `w*R1 - 0.0005*|w - w_prev|` per sym (first
prev = 0). Long-leg sums use fixed BASE-sign membership so base vs rule
compare identical rows. Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. Coverage of `z` is 100% all years (USDT history starts
2021-05-04, fully warmed up before 2021-09-24). Median USDT premium is
+0.5 bps.

## Verdict

NOT PROMISING (as assigned): total book P&L not lower in 4/5 years but
maxDD not worse in only 2/5 years (needs >= 4/5 on both). The tilt adds
return almost everywhere yet slightly deepens drawdown in 2023-2025.

## Per-year screen (net, portfolio-return units; costs included)

| year | coverage | share longs tilted (up/down) | long P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | P&L not lower | DD not worse |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 1.0 | 0.494 (0.322/0.172) | 0.146420 / 0.145668 | 0.278895 / 0.278144 | -0.055289 / -0.059614 | 0.092278 / 0.089537 | no | yes |
| 22-23 | 1.0 | 0.191 (0.072/0.120) | 0.219915 / 0.227123 | 0.235444 / 0.242656 | -0.047268 / -0.047268 | 0.073721 / 0.069382 | yes | yes |
| 23-24 | 1.0 | 0.404 (0.244/0.160) | 0.595114 / 0.635446 | 0.544150 / 0.584484 | -0.069471 / -0.069471 | 0.087902 / 0.088036 | yes | no |
| 24-25 | 1.0 | 0.437 (0.268/0.169) | 0.480437 / 0.501237 | 0.517693 / 0.538500 | -0.045930 / -0.044255 | 0.065296 / 0.069031 | yes | no |
| 25-26 | 1.0 | 0.522 (0.373/0.148) | 0.226569 / 0.250202 | 0.394724 / 0.418366 | -0.075345 / -0.079620 | 0.087166 / 0.089970 | yes | no |

Counts: P&L not lower 4/5; DD not worse 2/5. Short legs bit-identical by
construction (checked per year, diffs <= 8e-06 from the rule path's own
turnover chain). Full 5y path (context, compounded from year-1 start):
total P&L 1.970907 -> 2.062149 rule (+0.091 over 5y); maxDD
0.104644 -> 0.101883 rule (full-path DD improves while 3 of 5 per-year
DDs worsen).

Read: the inflow tilt lifts the long leg in 4/5 years (2023 +0.040,
2024 +0.021, 2025 +0.024, 2022 +0.007; only 2021 -0.0008) but the extra
long exposure costs 0.1-0.4pp of per-year maxDD in 2023 (+0.0001),
2024 (+0.0037) and 2025 (+0.0028), and worsens the worst week in 2021
and 2025. Return edge without the drawdown control the rule requires.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, thresholds, or the
   decision rule. PLAN.md was written before `compute_usdtprem.py` ran.
2. Costs are the assignment's 0.0005/unit (not oc_dvolshort/oc_cbpremium's
   0.0002); mechanics identical (per-sym chain, first prev = 0, each path
   its own chain; verified in tests/test_oc_usdtprem.py).
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path). Needs prospective
   validation; all five years were available when the idea was scored.
4. USDT-USD listed 2021-05-04 on Coinbase, so the 90d z needs warm-up;
   coverage is still 100% on the scored grid (2021-09-24 on). Three tiny
   source gaps (4/6/5 missing hourly bars) are bridged by as-of lookup,
   never forward-filled.

## One-line verdict

NOT PROMISING (as assigned): USDT inflow tilt (BASE longs x1.15 when z > 1,
x0.85 when z < -1) lifts total book P&L in 4/5 years but leaves maxDD worse
in 3/5 (DD not worse only 2/5; 5y total +0.091) — return edge, no drawdown
control.
