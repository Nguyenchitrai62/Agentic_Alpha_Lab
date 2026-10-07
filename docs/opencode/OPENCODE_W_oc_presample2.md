# OpenCode task oc_presample2 - do the dip-sleeve DESIGN CHOICES made on 2021-2026 also hold on never-used 2017-2020 data?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presample2/` and `tests/test_oc_presample2.py`.
Reuse research/tournament/oc_presample (read REPORT.md, PLAN.md, presample.py; copy, do not edit) and its data
data/raw/spot_1m_presample_20261007 (Binance spot 1m 2017-08..2020-09, BTC/ETH/BNB/XRP; SOL absent).

## Why
oc_presample showed the frozen G2 dip sleeve is profitable on 2017Q4-2020 with no losing year. That period is a SECOND untouched validation
set. Every dip-sleeve design choice of the deployment was selected on 2021-2026 (research/CLOSED_DIRECTIONS map, docs/CLOSED_DIRECTIONS.md
sections 1 and 6). If the same ranking of choices holds on 2017-2020, the choices generalise; if not, they were partly fitted to 2021-2026.

## Rows (fixed; same harness as oc_presample's G2 arm, 4 clock phases, dip-only, R2 agent size 1, gate costs; change ONE knob per row)
- G2: the oc_presample G2 arm (reproduce its numbers exactly first).
- NOB1: no corr-aware sizing (w = 1 instead of 1/(1+n)).
- KD13 / KD20: dip multiplier 1.3 / 2.0 instead of 1.7 (budget scales with it as in the deployment rows D13BF / G2K20).
- NOCAP: no gross cap (G = none).
- TOUCH: touch stop at 4 sigma instead of the close5 stop (+8 sigma backstop unchanged).
- TP15: take-profit 1.5 sigma instead of 1.0.
For each row and each pre-sample year (2017Q4, 2018, 2019, 2020-Jan..Aug): 4-phase mean %/month, mean DD and worst-phase DD (1m-marked),
fills, stops, win. Then a rank table: in the research years these choices were judged G2 > NOB1 (DD 25 -> 14), D17 between D13 and K20 on
the return / DD frontier, cap = same return with less tail, close5 > touch, TP 1.0 > 1.5 (cite the research numbers from
docs/CLOSED_DIRECTIONS.md / research-map when you state them). Does the pre-sample agree, row by row?
No parameter may be changed after seeing a pre-sample number; extra rows must be labelled post-hoc. Vietnamese 3-line verdict on whether the
design choices generalise.
