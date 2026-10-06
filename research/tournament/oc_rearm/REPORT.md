# oc_rearm REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

B1 base (oc_b1deeper arm-B1 exact replica: static bid at lv, live offsets
16..238, strict low < lv fill, size 1/(1+n), D0 exits from the fill price,
maker 0.0002 / taker 0.00055, longs pay 0.0001 on settling timeouts) vs the
re-arm rule (idea #67): after a rung's take-profit fills strictly inside the
bar, the same bid at the same price lv is re-placed from the next minute with
size 1/(1+n) recomputed at its own fill minute, at most one refill per rung
per bar, exits unchanged, stop-first. Majors x R2 depths (2.5/3/3.5/4/5),
bars with open in [2021-09-24, 2026-09-24), 4 clock phases (0/1/2/3h grid
shifts; dip sums swing hard with phase, e.g. 2021 rule sums per shift
+1.95/+0.94/-0.18/-0.85, so all metrics are 4-phase means / pooled).
Replica validated: shift-0 base fills per year = 990/1045/1330/989/1144 with
raw sums 2.39/0.18/3.81/2.58/0.71, tick-identical to oc_b1deeper B1.
Market data to 2026-09-24 is research data: any result needs prospective
validation (disclosed vs RULES.md hidden-year rule).

Two cap variants (weights are raw w*y; win rates pooled over phases; DD in
w*y units, 1 pp = 0.01):
- V0 (pre-registered, results.json): G = 2.0 on size_mult weights in both
  arms. Binds on the MEDIAN fill bar (fills cluster: median 4, mean 7.2, max
  49 candidates per phase-bar; median exit minute 211): 60% of base fills
  skipped, 69% of re-armed candidates parent-skipped.
- V1 (disclosed post-hoc unit fix, results_v1.json, run_rearm_v1.py): the
  only change is G1 = 2.0/K ~= 31.2 with K = kd*SIZE/(4*S_REF) =
  1.7*0.25/(4*1.657) ~= 0.0641 from engine/G2 constants only (s*g = 1, R2
  size = 1, budget skips omitted; no data fitting), i.e. G = 2.0 on
  deployment-scale equity notionals. The cap then never binds (all 22312
  base + 4745 re-armed candidates kept), deployment-like. Candidates, exits,
  fees, scoring and the decision rule are V0-identical.

## Per-year base vs rule, 4-phase means (V1; n = trades, win = net>0 share)

| year | base n/sum/worst/DD | rule n/sum/worst/DD | re-armed n/win/share |
|---|---|---|---|
| 2021 | 1042.8/0.911/-0.740/0.856 | 1276.5/0.466/-0.954/1.065 | 935/0.620/-0.957 |
| 2022 | 1014.8/0.833/-0.726/0.951 | 1244.2/0.663/-0.785/1.081 | 918/0.685/-0.256 |
| 2023 | 1338.0/2.100/-0.735/0.800 | 1613.2/2.171/-0.767/0.941 | 1101/0.740/+0.033 |
| 2024 | 989.5/3.197/-0.274/0.355 | 1201.2/3.548/-0.461/0.505 | 847/0.719/+0.099 |
| 2025 | 1193.0/0.677/-0.508/0.607 | 1429.0/0.716/-0.705/0.795 | 944/0.679/+0.054 |
| pooled 5y | base win 0.699 | rule win 0.696 | re-armed win 0.690, 4745 fills |

Renormalised (exposure-neutral) 4-phase-mean sums, base vs rule:
2021: 1.507/0.779; 2022: 1.247/1.021; 2023: 3.169/3.366; 2024: 4.885/5.507;
2025: 1.147/1.247 -- same 3/5 pattern, so the verdict does not hinge on
renormalisation.

## Decision (PROMISING = sum higher in >=4/5 AND DD within 1pp in >=4/5 AND re-armed win >=60%)

| check | V0 (G=2.0 literal) | V1 (G=2.0 deployment-scale) |
|---|---|---|
| sum higher | 1/5 (only 2023) | 3/5 (2023/2024/2025) |
| DD within 1pp | 1/5 (only 2025) | 0/5 (rule DD worse every year, +0.13..+0.21) |
| re-armed win >=60% | 64.9% YES | 69.0% YES (every year 62-74%) |
| PROMISING | NO | NO |

## Notes

- Re-armed fills win 62-74% per year, yet LOSE money in 2021 (-0.96x the
  rule total) and 2022 (-0.26x): small TPs (+1sg minus fees) against full
  stop/backstop/timeout tails -- the classic short-gamma profile of
  re-dipping into a level that just TP'd. Positive but small share (+3..+10%)
  in 2023-2025.
- The rule adds ~22% more trades and raises maxDD in all 5 years under both
  cap mappings (V0 DD also worse in 4/5 despite the heavy cap suppression),
  and worsens the worst day in all 5 years. Extra exposure is not free.
- V0 and V1 agree on the verdict from opposite cap regimes (always-binding
  vs never-binding guardrail), so the rejection is not a cap artifact.
- Repro: `research/tournament/oc_rearm/{PLAN.md,rearm.py,run_rearm.py,
  run_rearm_v1.py,results.json,results_v1.json,fills_candidates.parquet}` +
  `tests/test_oc_rearm.py` (8 tests pass); one process, peak RAM ~0.3 GB.

## Verdict

VERDICT: NOT PROMISING -- the re-arm adds losing-or-thin P&L in 2 of 5 years and raises drawdown in all 5 years under both cap mappings, so the once-per-bar rung limit stands.
