# oc_skewbook — REPORT: Deribit skew / put-buy share as BOOK context (5y gross)

Book = `forward_v205.research_books_d2` (rebuilt exactly; year totals match
oc_bookic to 6dp); opens = v154 4h opens. Context = BTC options skew
(`iv_otm_put - iv_otm_call`, last COMPLETE 4h bar, asof-backward) + BTC
put-buy share; ETH skew secondary. Metric = `w[t] x (open[t+1]/open[t]-1)`,
gross, NO costs. Full tables in `results.json`.

## 1. Primary effect: high-minus-low skew-tercile book P&L per anchor year

Cut-offs q33/q67 from pre-anchor skew history only (2019-01-01 on).

| year | cut q33/q67 | low | mid | high | E=high-low | sign |
|---|---|---|---|---|---|---|
| 2021-09-24 | 0.29/9.87 | -0.059 | -0.009 | +0.388 | **+0.447** | pos |
| 2022-09-24 | 2.02/10.49 | +0.233 | +0.140 | -0.055 | **-0.288** | neg |
| 2023-09-24 | 1.21/9.49 | +0.375 | +0.274 | -0.071 | **-0.446** | neg |
| 2024-09-24 | 0.85/8.41 | +0.100 | +0.143 | +0.329 | **+0.229** | pos |
| 2025-09-24 | 1.11/8.03 | +0.103 | +0.358 | +0.030 | **-0.073** | neg |

Same sign in 3/5 (need >= 4). LOYO holds 3/5 (excluding 2022 or 2023 flips
the 5y sign to pos). => rule criterion (a) and (b) both FAIL.

## 2. Spearman IC of BTC skew vs next 1-day / 7-day return, per (year, coin)

| year | BNB 1d/7d | BTC 1d/7d | ETH 1d/7d | SOL 1d/7d | XRP 1d/7d |
|---|---|---|---|---|---|
| 2021 | +0.04/+0.06 | +0.01/+0.09 | -0.00/+0.02 | +0.02/+0.04 | +0.03/+0.08 |
| 2022 | +0.02/+0.08 | +0.04/+0.15 | +0.05/+0.13 | -0.01/+0.00 | +0.00/+0.07 |
| 2023 | +0.03/+0.06 | -0.02/-0.00 | -0.01/-0.00 | -0.02/-0.03 | -0.01/+0.06 |
| 2024 | +0.06/+0.10 | +0.01/-0.04 | -0.01/-0.04 | +0.05/+0.03 | +0.03/+0.05 |
| 2025 | -0.00/-0.02 | +0.03/+0.08 | +0.03/+0.07 | +0.02/+0.06 | +0.00/+0.06 |

Small (|IC| <= 0.15), mostly positive at 7d, but sign/magnitude wander by
year (BTC/ETH 7d negative in 2023-2024). Put-buy share: 1d IC negative every
year x coin (-0.04..-0.11), 7d IC near zero and mixed (-0.07..+0.10). ETH
skew agrees with BTC skew where both exist. Nothing tradeable or stable.

## 3. Book P&L by skew tercile x leg (supporting; long | short inside total)

| year | low (L/S) | high (L/S) |
|---|---|---|
| 2021 | -0.082/+0.023 | +0.329/+0.059 |
| 2022 | +0.222/+0.011 | -0.061/+0.006 |
| 2023 | +0.313/+0.062 | +0.041/**-0.112** |
| 2024 | -0.011/+0.111 | +0.387/-0.058 |
| 2025 | +0.070/+0.033 | +0.008/+0.022 |

High-skew bars carry the 2023 short-leg loss (-0.112) but also the best
2021 (+0.388) and 2024 (+0.329) gains — the "fear is bad for the book" story
holds in 2022-2023 and reverses in 2021/2024.

## Verdict (one line)

**NOT PROMISING: the high-minus-low skew effect is sign-unstable (3 neg /
2 pos across the 5 anchor years, LOYO holds only 3/5) and the skew/put-buy
ICs are tiny and wandering — no skew-conditioned book rule is proposed.**

Caveats: gross vectorised P&L only (no spread/fees/funding, no vol target,
governor, SL/TP, sleeve, compounding); timing is next-4h-bar open-to-open,
not the engine's limit-fill path; Deribit BTC/ETH options proxy the whole
5-coin book; effect magnitudes (E up to +/-0.45 weight x return units) look
large next to ~4-8 bps round-trip costs, but sign instability, not costs,
is what fails the rule — a gate fitted on 2022-2023 would have destroyed
2024 high-skew gains.
