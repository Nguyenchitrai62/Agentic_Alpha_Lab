# oc_bookoffset REPORT: volatility-scaled book entry offset (5y, 1m fills)

Book = `forward_v205.research_books_d2` (rebuilt exactly); grid = decisions `t`
with holding-bar open `T = t+4h` in [2021-09-24, 2026-09-24), exit `X = T+4h <=
BOUND` (10955 `T` bars, 6 leap-gap orphans excluded, 0 unscored for missing
1m). Entry attempts = every scored (coin, bar) with non-zero target (52191
attempts, ~4.77 coins/bar; both rules share the attempted set). `P0` = 1m
minute-0 open (== 4h open, checked), `PX` = next 4h open. sigma4h = trailing
360-bar std of 4h simple returns ending strictly before `T` (min 120; mean
1.46%, p5/p50/p95 0.74/1.37/2.51%; NaN fallback 0, clip [5,40] bps never binds).
Fixed: 10 bps better; vol: `clip(0.10*sigma,5,40)` (mean 14.6 bps,
p5/p50/p95 7.4/13.7/25.1 bps). Fill = strict 1m trade-through in minutes
[5,65) (buy `low < L`, sell `high > L`); fill price = limit (maker 0.02% on
entry, exit at mid). Episode = holding bar; filled `gross = w*(PX/L-1)`,
`net = gross-|w|*0.0002`, missed actual 0 with hypothetical `hyp = w*(PX/P0-1)`.
Full numbers in `results.json`.

## 1. Per anchor year (`T in [A_k, A_k+365d)`): fill rate / offsets / P&L

Fixed 10 bps (5y fill 79.2%, filled 41358/52191, total net +0.115):

| year | attempted | fill rate | mean off att/fill (bps) | filled gross | filled net | missed hyp | total net |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 9774 | 0.850 | 10.0 / 10.0 | +0.069 | -0.028 | +0.750 | -0.028 |
| 2022-09-24 | 10471 | 0.766 | 10.0 / 10.0 | +0.171 | +0.041 | +0.826 | +0.041 |
| 2023-09-24 | 10730 | 0.796 | 10.0 / 10.0 | +0.299 | +0.162 | +0.920 | +0.162 |
| 2024-09-24 | 10578 | 0.795 | 10.0 / 10.0 | +0.212 | +0.069 | +1.040 | +0.069 |
| 2025-09-24 | 10638 | 0.758 | 10.0 / 10.0 | +0.008 | -0.129 | +1.142 | -0.129 |

Vol-scaled `0.10*sigma` (5y fill 75.6%, filled 39473/52191, total net +0.334):

| year | attempted | fill rate | mean off att/fill (bps) | filled gross | filled net | missed hyp | total net |
|---|---|---|---|---|---|---|---|
| 2021 | 9774 | 0.791 | 18.6 / 18.5 | +0.143 | +0.054 | +1.040 | +0.054 |
| 2022 | 10471 | 0.723 | 14.3 / 14.1 | +0.228 | +0.102 | +0.870 | +0.102 |
| 2023 | 10730 | 0.772 | 13.5 / 13.5 | +0.342 | +0.206 | +0.992 | +0.206 |
| 2024 | 10578 | 0.758 | 14.6 / 14.5 | +0.234 | +0.093 | +1.138 | +0.093 |
| 2025 | 10638 | 0.740 | 11.9 / 11.9 | +0.018 | -0.121 | +1.165 | -0.121 |

Entry improvement = posted offset by construction (fill at the limit); vol
posts deeper on average (+8.6 bps in 2021, +1.9 bps in 2025) and fills 2-6 pp
less. Missed-hyp sums are large positive under both rules (unfilled straight-
through trends would have won at minute-0); vol misses slightly more trend
P&L but earns more on its fills in every year.

## 2. Decision (pre-registered: vol total_net > fix in >= 4/5 years)

| year | fix total_net | vol total_net | d = vol-fix | LOYO-holdout pass |
|---|---|---|---|---|
| 2021-09-24 | -0.0282 | +0.0536 | +0.0818 | yes |
| 2022-09-24 | +0.0413 | +0.1019 | +0.0606 | yes |
| 2023-09-24 | +0.1620 | +0.2061 | +0.0441 | yes |
| 2024-09-24 | +0.0687 | +0.0930 | +0.0242 | yes |
| 2025-09-24 | -0.1292 | -0.1207 | +0.0085 | yes |

Positive years 5/5, LOYO 5/5, first-four-year 4/4. 5y totals: fix +0.115,
vol +0.334 (delta +0.219). Compounded year-return side row (bar-net product):
fix -0.048/+0.028/+0.157/+0.059/-0.133, vol +0.036/+0.092/+0.209/+0.085/-0.125
— same 5/5 ranking.

## Caveats / post-hoc log

1. No post-hoc change to definitions, offsets, windows, fill rule, costs, or
   the decision rule. Only additions after the run: compounded side row and
   first-four-year sensitivity (descriptive, rule untouched).
2. From-flat independent-episode simplification (disclosed in PLAN): each bar's
   target is attempted from flat; carry, adds/reduces, SL/TP, governor, vol
   target and min-notional are ignored, exit is at the next 4h mid with no
   fee — the RELATIVE offset ranking is the object, not the absolute level
   (absolute one-bar sums are small after maker fees and miss large trend
   P&L by construction).
3. Year = `[A_k, A_k+365d)` per the assignment; 6 bars (2024-09-23..2024-09-24)
   are orphaned and excluded (a `[A_k,A_{k+1})` partition would assign them to
   2023; effect on a 5/5 result is nil by inspection of the margin).
4. All five years were available when the rule was frozen (assignment); no
   hidden year remains — adoption needs prospective validation.

## One-line verdict

PROMISING as assigned: vol-scaled offset beats fixed 10 bps on total book P&L in 5/5 years (LOYO 5/5).

## Leader note (2026-10-06)
Closed without an engine run: the deployed BOT book runs in engine trade mode, whose entry limit is ALREADY volatility-scaled
(off = max(min_off, k_off x sigma_4h), k_off 0.25, deep 0.75; engine_user._trade_bar). The fixed 10 bps baseline of this screen is the
legacy engine_real convention, not the deployed rule, so the screen's gain is already part of the pipeline.
