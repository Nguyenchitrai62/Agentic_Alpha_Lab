# oc_c2ic — REPORT: does the C2 calibration fix add XS info the deployed book lacks?

Method: per anchor year 2021-2024, member weights (fixed C2 / buggy C2 / deployed
same slot) vs `y42 = open[t+43]/open[t+1]-1` (raw 42-bar forward return, 4h grid).
`xs_mean` = mean per-timestamp cross-sectional Spearman across the 5 majors;
`hit` = P(sign w == sign y42 | w != 0); `net` = P(w>0)-P(w<0); `corr` = pooled
Pearson vs deployed. Books = `0.8 x O1 + 0.2 x D` verbatim from
`oc_bookmodel_evalprep/eval_candidate.py` (D byte-identical). Scored t all
< 2025-09-24; no training, no engine. Full numbers in `results.json`.

## 1. Book: candidate (C2-fix) vs deployed (the verdict inputs)

| year | cand xs | depl xs | cand-depl | book corr | cand hit/net | depl hit/net |
|---|---|---|---|---|---|---|
| 2021 | -0.023 | -0.030 | +0.007 | 0.44 | 0.541 / -0.48 | 0.550 / +0.04 |
| 2022 | +0.018 | +0.060 | -0.041 | 0.59 | 0.470 / -0.06 | 0.479 / +0.02 |
| 2023 | +0.077 | -0.007 | +0.084 | 0.53 | 0.487 / +0.20 | 0.491 / +0.21 |
| 2024 | -0.064 | +0.047 | -0.111 | 0.11 | 0.479 / +0.33 | 0.502 / +0.23 |

Candidate wins 2/4 years (2021 tiny, 2023 clearly); pooled cand-vs-deployed
Pearson = 0.41 (< 0.7: the signals are genuinely different).

## 2. Members: fixed C2 vs deployed same slot (xs IC delta, fix corr)

| year | A | Aq | B | Bq |
|---|---|---|---|---|
| 2021 | -0.025 / 0.27 | +0.080 / 0.26 | -0.025 / 0.26 | +0.009 / 0.32 |
| 2022 | -0.029 / 0.51 | -0.036 / 0.40 | -0.068 / 0.51 | -0.058 / 0.25 |
| 2023 | +0.098 / 0.38 | +0.051 / 0.20 | +0.106 / 0.40 | +0.032 / 0.40 |
| 2024 | -0.133 / -0.16 | -0.056 / 0.07 | -0.099 / -0.18 | -0.079 / 0.09 |

Fix beats deployed in 6/16 cells (all of 2023 plus 2021 Aq/Bq); loses everywhere
in 2022/2024. All fix-vs-deployed correlations < 0.6 (two negative in 2024).
Buggy members confirm the disclosed bug: net long -0.53..-0.85 every
(year, member) vs fixed -0.62..+0.27.

## Verdict (plain)

**NO — the C2 fix does not add cross-sectional information the deployed book
lacks by the pre-registered rule: candidate-book IC beats deployed in only 2/4
years (needs >= 3), even though book correlation 0.41 < 0.7 (distinct signal).
The 2023 gain does not generalise (2022/2024 both worse, 2024 by -0.11).**

Caveats: IC only (no P&L/engine); raw (not vol-normalised) 42-bar return;
hit rates ~0.47-0.57 throughout, i.e. neither book ranks the 5-major
cross-section reliably year to year.
