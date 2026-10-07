# oc_tpbyn REPORT: take-profit choice conditional on market-flush count n

## Setup
Majors (BTC/ETH/SOL/BNB/XRP) R2 rungs (`x1` in {2.5,3,3.5,4,5}) from
`research/tournament/ext/fills_U_ext.parquet` joined 1:1 to
`research/tournament/oc_b1shape/fills_n.parquet` (`n` = `n25` detections
among the 4 other majors, `close(f-1) <= O(T)*(1-2.5*sigma(T))`; no 1m read
here). Join keys (sym, Bx=T, t_fill, f, k): 6876/6876 rows joined,
max |y1.0 diff| = 0. Years = 5 anchors 2021-09-24..2025-09-24,
`[anchor, anchor+365d)` keyed by `T` (5498 fills: 990/1045/1330/989/1144).
Outcomes `y0.5/y1.0/y1.5` are exact nets (fees/funding in). All 5 years are
research data per assignment (disclosed vs RULES.md hidden-year rule);
a PROMISING rule still needs prospective validation.

## Mean net by n bucket (unweighted rung means; 2+ = n in {2,3,4})

| year | n=0: mean y0.5/y1.0/y1.5 (n) | n=1: mean y0.5/y1.0/y1.5 (n) | n=2+: mean y0.5/y1.0/y1.5 (n) | mean(y1.5-y1.0) by bucket |
|---|---|---|---|---|
| 2021-09-24 | .003189/.004532/.004177 (422) | .001701/.001273/.000675 (177) | .003041/.004191/.004120 (391) | -0.000355 / -0.000598 / -0.000072 |
| 2022-09-24 | -.000515/.000080/.000911 (515) | .000585/.002016/.001537 (189) | -.001370/-.000085/-.000123 (341) | +0.000831 / -0.000479 / -0.000038 |
| 2023-09-24 | .002598/.004720/.005181 (659) | .001128/.002854/.003950 (227) | .000969/.003419/.004820 (444) | +0.000461 / +0.001097 / +0.001401 |
| 2024-09-24 | .002488/.003677/.003603 (460) | .003702/.004731/.005166 (183) | .002886/.004361/.005320 (346) | -0.000074 / +0.000435 / +0.000959 |
| 2025-09-24 | .000743/.000858/.000345 (443) | .000321/.001399/.001284 (203) | .000822/.001755/.002280 (498) | -0.000512 / -0.000114 / +0.000525 |
| overall | .001707/.002855/.002984 (2499) | .001441/.002455/.002567 (979) | .001267/.002728/.003309 (2020) | +0.000128 / +0.000111 / +0.000581 |

## Rule test at sizes 1/(1+n), equal exposure (w' = w/mean(w) per year)
A = always TP 1.0 (`yA = y1.0`); B = TP 1.5 iff n>=2 else 1.0
(`yB = y1.5 if n>=2 else y1.0`). S = sum(w'*y); days by T.floor(D).

| rule | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| A always1.0 S | 3.9546 | 0.2905 | 5.7374 | 3.9523 | 1.2367 |
| B tp15_if_n2 S | 3.8849 | 0.2692 | 5.9402 | 4.1116 | 1.2885 |
| D = B - A | -0.0697 | -0.0213 | +0.2028 | +0.1593 | +0.0518 |
| LOO mean D excl. year | +0.0982 | +0.0861 | +0.0300 | +0.0409 | +0.0678 |

Tails (context only): worst-day per year A: -0.7134/-1.0811/-0.3979/-0.3312/-0.9030
(overall -1.0811, maxDD -1.6976); B: -0.8180/-1.0733/-0.3850/-0.3190/-1.1003
(overall -1.1003, maxDD -1.7204). B deepens the overall worst day (-1.10 vs -1.08)
and maxDD (-1.72 vs -1.70).

## Decision (PROMISING = D>0 in >=4/5y AND LOO D>0 in >=4/5)
D>0 in 3/5 years (2023, 2024, 2025); LOO>0 in 5/5. First condition fails.

## Verdict
NOT PROMISING: conditional TP 1.5 on n>=2 gains in 2023-2025 but loses in 2021-2022, so it fails the pre-registered >=4/5-year rule (LOO passes 5/5 but does not rescue it); keep always-1.0.

## Caveats / repro
- The 2+ bucket's mean(y1.5-y1.0) is positive in 3/5 years (2023-2025) and ~0 in
  2021-2022, matching the rule-level D signs; bucket means are unweighted while
  S uses 1/(1+n) weights, so magnitudes differ by construction.
- y1.5 wins on flushed fills only in the later years; no threshold was fit.
- Repro: `research/tournament/oc_tpbyn/{PLAN.md,analyze_tpbyn.py,results.json,
  REPORT.md}` (reuses `oc_b1shape/fills_n.parquet`; one process, no 1m, RAM < 1 GB)
  + `tests/test_oc_tpbyn.py`.
