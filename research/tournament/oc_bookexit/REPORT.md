# oc_bookexit REPORT — learned exit levels for BOOK trades, idea #31 (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Book = `forward_v205.research_books_d2` (rebuilt exactly); opens = v154 4h
opens; 4h high/low/close = hourly_ext majors aggregated (hours T..T+3).
Grid 2021-09-24 00:00 .. 2026-09-23 20:00 (10956 scored 4h bars,
`r[t] = open[t+4h]/open[t]-1`). Episodes = maximal constant-sign runs per
coin (entry to flat/sign change); default net = gross - 0.05% turnover
(entry + intra + flatten legs). Label = reaches +1.5x ATR4h before -1.0x
ATR4h (ATR = trailing-14 4h true-range SMA at entry; same-bar touch =
adverse first). Model = HGB(max_depth=3, max_iter=200, min_samples_leaf=200)
on 7 entry-time features (wgt, |w|, vol4h, 30d trend, BTC trend, hour, coin
id); walk-forward train = episodes with close < anchor-7d; flagged iff
p < 0.45; flagged + touch of +1.0 ATR -> bank `1.0*(A/E)*|w[a]|-2*FEE*|w[a]|`,
else default. Per-year stats keyed by entry; path = close-ordered cumprod
(simultaneous closes compound), year-rebased; worst week = min trailing-7d
on daily-ffilled path. Repro: `research/tournament/oc_bookexit/{PLAN.md,
compute_bookexit.py,results.json}`.

## Episode census
1148 episodes (label rate 0.362); excluded 29 (5 no-close last-bar, 9 NaN
ATR/HLC, 15 NaN features). Per coin (n / label rate): BNB 238/0.332,
BTC 195/0.374, ETH 188/0.415, SOL 233/0.352, XRP 294/0.354.

## Per anchor year: book P&L (sum of episode nets), win rate, maxDD, worst week — default vs rule
| year | n | train (rate) | flagged | P&L def -> rule | win def -> rule | maxDD def -> rule | worst-week def -> rule |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 287 | 0 (—) | 0 (no train data) | +0.0303 -> +0.0303 | 0.4634 -> 0.4634 | 0.1389 -> 0.1389 | -0.0492 -> -0.0492 |
| 2022-09-24 | 189 | 281 (0.317) | 189 (100%) | +0.2784 -> -0.0349 | 0.4127 -> 0.6667 | 0.0457 -> 0.0370 | -0.0414 -> -0.0125 |
| 2023-09-24 | 197 | 466 (0.328) | 188 (95%) | +0.5629 -> -0.0418 | 0.4112 -> 0.6853 | 0.0575 -> 0.0505 | -0.0402 -> -0.0315 |
| 2024-09-24 | 262 | 664 (0.343) | 232 (89%) | +0.5797 -> -0.0380 | 0.4504 -> 0.7061 | 0.0371 -> 0.0650 | -0.0262 -> -0.0324 |
| 2025-09-24 | 213 | 925 (0.362) | 156 (73%) | +0.1921 -> +0.0135 | 0.5070 -> 0.6385 | 0.0307 -> 0.0183 | -0.0146 -> -0.0134 |

Effect on P&L sums (rule-default): 0.0000, -0.3133, -0.6047, -0.6177,
-0.1786. Leave-one-year-out means: all 5 negative (-0.43, -0.35, -0.28,
-0.27, -0.38). Compounded trade-equity deltas agree in sign every year.

## Decision
Book P&L not lower in 1/5 years (only the 2021 tie; required >= 4/5). Win
rate up in 4/5 years (all four scored years, +13 to +27pp; 2021 tied, not
strict). Required BOTH >= 4/5.

## Verdict
VERDICT: NOT PROMISING — the +1.0 ATR bank raises win rate in every scored
year but gives up 18–62pp of yearly book P&L (caps the runners that earn the
book's return; base label rate ~0.36 keeps predictions under the 0.45 flag
threshold for 73–100% of test episodes).

## Caveats / post-hoc log
Single post-hoc change (no outcome seen before it): PLAN assumed trainable
history for every anchor, but BOT books start exactly at 2021-09-24, so year
0 has zero causal training rows — year 0 runs rule == default (tie), logged
in results.json as `no_train_data`. Anything else follows PLAN exactly.
Simplifications (disclosed): vectorised 4h open-to-open P&L (0.05%/turnover,
no vol target/governor, SL/TP engine, funding, sleeve, cross-year
compounding); rule TP valued at entry size (entry + exit legs, no intra
churn); year stats entry-keyed with close-ordered path (small close
spillover at edges); coin feature stored as integer `coin_id`.
Tests: `tests/test_oc_bookexit.py` (5 pass: segmentation/cost partition,
label stop-first, TP value math, train-mask embargo edge, feature causality
under future perturbation).
