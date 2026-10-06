# oc_cbpremium REPORT: Coinbase premium as BOOK direction tilt (idea #60)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_bearshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter (longs x0.5 when BTC
4h open < 1200-bar mean, rolling 1200 min 600, open[T] inclusive).
Premium (exactly as oc_optctx): hourly inner join Coinbase BTC-USD /
Binance BTCUSDT on bar START (`prem = cb/bin - 1`), `mean24` rolling 24
min 20, `z90` rolling 2160 min 1728 shifted by one (history only); as-of =
last row with end strictly before T (`end <= T - 1s`, so for 4h T the last
usable hour is `[T-2h, T-1h]`). RULE = BASE with book LONG targets x1.15
when `z > 1`, x0.85 when `z < -1`, else x1.0 (BTC-only signal applied to
all 5 coins; shorts/flats/NaN-z bit-identical; v410 x0.5 kept inside BASE).
Screen = open-to-open 4h returns with gate costs, exactly as
oc_dvolshort/oc_bearshort: net cell = `w*R1 - 0.0002*|w - w_prev|` per sym
(first prev = 0; each path its own prev chain). Long-leg sums use BASE sign
(`w_base > 0`) so base vs rule compare identical rows. Equity per year
reset to 1 and compounded as `eq *= 1 + sum_s pnl`; maxDD =
peak-to-trough; worst week = min 42-bar compounded return. Full tables in
`results.json`; `panel.parquet` holds per-(T,sym) rows. Coverage of `z` is
100% all years (premium grids start 2020-08, fully warmed up). Base
cross-check: per-year base P&L / maxDD / bear shares reproduce
oc_bearshort's v410 base exactly (total 2.061253, full-path DD 0.100471).
Median premium is +3.36 bps (Coinbase above Binance).

## Verdict

NOT PROMISING (as assigned): total book P&L higher in 5/5 years (needs
>= 4/5: pass) BUT maxDD not worse in only 2/5 years (needs >= 4/5: fail).

## Per-year screen (net, portfolio-return units; costs included)

| year | bear share | long up / down share | long P&L base / rule | total book P&L base / rule | worst week base / rule | maxDD base / rule | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 0.763 | 0.287 / 0.161 | 0.153468 / 0.156822 | 0.291959 / 0.295310 | -0.055143 / -0.062919 | 0.086514 / 0.083498 | yes | yes |
| 22-23 | 0.407 | 0.085 / 0.125 | 0.228949 / 0.236864 | 0.252013 / 0.259930 | -0.046676 / -0.046676 | 0.071462 / 0.067830 | yes | yes |
| 23-24 | 0.217 | 0.170 / 0.242 | 0.607182 / 0.616791 | 0.564138 / 0.573746 | -0.069232 / -0.069232 | 0.087278 / 0.087397 | yes | no |
| 24-25 | 0.138 | 0.202 / 0.220 | 0.494588 / 0.496868 | 0.539535 / 0.541817 | -0.045264 / -0.043038 | 0.062817 / 0.070370 | yes | no |
| 25-26 | 0.804 | 0.362 / 0.147 | 0.235489 / 0.253521 | 0.413608 / 0.431642 | -0.074825 / -0.079609 | 0.085657 / 0.089602 | yes | no |

Counts: P&L higher 5/5; DD not worse 2/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.102295 rule (+0.18pp);
total P&L 2.061253 -> 2.102446 rule (+0.0412 over 5y, all of it via the
long leg; short leg bit-identical by construction).

Read: the tilt does what it says — it adds long size in every year
(+0.0023 to +0.0180 of book P&L per year, largest in 2025 where 36% of
base longs get the x1.15 up-tilt) but buys return by buying variance. DD
improves only in 2021 (-0.30pp) and 2022 (-0.36pp); it is flat-to-worse in
2023 (+0.01pp), clearly worse in 2024 (+0.75pp, where the rule also posts
the only worst-week win, -0.0453 to -0.0430) and worse in 2025 (+0.39pp,
where the worst week also worsens to -0.0796). The P&L leg passes 5/5 but
the DD leg fails 3/5, so the assigned conjunction fails.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, multipliers, or the
   decision rule. PLAN.md was written before `compute_cbpremium.py` ran.
2. Performance-only/reporting bugfix toward PLAN (verified, not
   outcome-driven): `bear_share` was first computed as the year-mask mean
   (~0.20 flat) instead of `mean(bear[sel])`; fixed and re-ran. Weights,
   costs, P&L and DD paths were unaffected (base P&L/maxDD reproduce
   oc_bearshort's v410 base exactly). Outcome statistics were seen before
   the fix, but the fix changes no outcome — only the reported bear-share
   column, which now matches oc_bearshort (0.763/0.407/0.217/0.138/0.804).
3. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own chain). Long-leg membership
   fixed by base sign; short leg bit-identical base vs rule. Fixed z =
   +/-1 thresholds, so the default tournament LOYO rule is N/A by
   construction (no in-year fit to leave out). Needs prospective
   validation; in-sample walk-forward style (premium z uses strictly past
   bars, but all five years were available when the idea was scored).

## One-line verdict

NOT PROMISING (as assigned): Coinbase-premium long-tilt (x1.15 when z > 1,
x0.85 when z < -1 on the v410 base) lifts book P&L in 5/5 years but leaves
maxDD not worse in only 2/5 (worse in 2023-2025) — a return-only tilt, not
a risk-safe one.
