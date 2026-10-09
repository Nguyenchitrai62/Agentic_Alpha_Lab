# oc_d_calendar — REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS12 #4 thin-book calendar tilt (weekend/session overshoot): timestamps only, zero-fit
trigger (stationary rates by construction). V1 Sat/Sun-UTC signal bars dip x1.25 else x1.0;
V2 00-08 UTC bars x1.2 else x1.0 (frozen UTC windows, no fit; market-wide per time-bar:
every coin shares one mult per (shift, T)). Replica PRIMARY + 2021-2026 SECONDARY; engine
only if PRIMARY pass AND SECONDARY pass for the same variant. B1/cap/stops kept in every
leg by inheritance (replica has no budget/cap; engine not run).

STATUS: DONE — no engine (valid negative). Pre-sample ledger reproduces exactly
(n=9731, legs 909/2986/3115/2721, base 2.313362/2.678870/0.577643/0.297538);
2021-2026 ledger reproduces exactly (n=22312, sum5y 7.718304). Timing / block placebos
(1000/yr) + stop-kind recompute (15 unknown, identical totals to oc_cboostpre: TP 5729 /
time 3445 / stop 480 / backstop 62) complete. Tests: 6 pass
(`tests/test_oc_d_calendar.py`).

## PRIMARY: pre-sample replica 2017..2020-09-23 (SPOT fills/exits, perp gate costs)

| year x variant | n | base | norm | gain | timing pct | block pct | boosted% |
|---|---|---|---|---|---|---|---|
| Y2017 V1 | 909 | 2.313362 | 2.309657 | -0.003705 | 33.07 | 27.17 | 0.271 |
| Y2018 V1 | 2986 | 2.678870 | 2.663324 | -0.015546 | 1.40 | 1.10 | 0.156 |
| Y2019 V1 | 3115 | 0.577643 | 0.558957 | -0.018686 | 27.17 | 26.37 | 0.180 |
| Y2020p V1 | 2721 | 0.297538 | 0.210117 | -0.087421 | 9.89 | 18.38 | 0.264 |
| Y2017 V2 | 909 | 2.313362 | 2.367062 | +0.053700 | 96.50 | 99.00 | 0.320 |
| Y2018 V2 | 2986 | 2.678870 | 2.657578 | -0.021293 | 13.29 | 7.69 | 0.294 |
| Y2019 V2 | 3115 | 0.577643 | 0.659560 | +0.081917 | 93.21 | 97.90 | 0.259 |
| Y2020p V2 | 2721 | 0.297538 | 0.134744 | -0.162794 | 0.40 | 0.40 | 0.255 |

- Helps (gain>0): V1 0/4, V2 2/4 (Y2017 +0.054, Y2019 +0.082).
- COVID leg Y2020p (must survive): V1 -0.087, V2 -0.163 — BOTH NEGATIVE (fail).
  The 2020-03-12 crash was a Thursday (V1-neutral by construction, disclosed per IDEAS12),
  yet both variants lose the COVID leg: weekend/session sizing levers the crash downdrafts,
  not the rebound — same mechanism as every presampletilt tilt (all fail Y2020p).
- Timing (PRIMARY null, this IS a timing rule): V1 33.1/1.4/27.2/9.9 (never significant);
  V2 96.5/13.3/93.2/0.4 (Y2017 timing-significant with a +0.054 gain; Y2019 93.2/97.9 just
  below/above on timing/block with +0.082). Block: V1 27.2/1.1/26.4/18.4,
  V2 99.0/7.7/97.9/0.4.
- PRIMARY pass = >=3/4 AND Y2020p>0 AND pooled stop<=+1pp: V1 FAIL, V2 FAIL.
- Round-trip ~4-8 bps bounds all effects: the two positive pre-sample gains (+0.054/+0.082)
  are at most a few bps/month-equivalent on normalised sums and do not survive the COVID leg.

## Crash risk (stop-hit share; kinds recomputed verbatim mu=1.0; 15 unknown)

| year | base stop% | V1 boosted% (delta) | V2 boosted% (delta) | base TP% |
|---|---|---|---|---|
| Y2017 | 3.30 | 0.81 (-2.49) | 1.03 (-2.27) | 80.31 |
| Y2018 | 3.29 | 2.80 (-0.49) | 4.22 (+0.93) | 55.82 |
| Y2019 | 6.69 | 11.09 (+4.40) | 1.61 (-5.08) | 55.27 |
| Y2020p | 7.58 | 7.51 (-0.07) | 15.05 (+7.47) | 59.49 |

- Pooled: base 5.58%; V1 boosted 6.59% (+1.01pp), V2 boosted 5.89% (+0.31pp).
- Stop-rate check (fail if pooled boosted >+1pp, b7breaker standard): V1 FAIL (+1.01pp,
  borderline but over), V2 PASS (+0.31pp) — but V2 fails gains, so nothing passes overall.
- Y2020p: V2 session-boosted fills stop at 15.05% vs 7.58% base (+7.47pp) — the session tilt
  levers the crash leg hard; V1 weekend tilt is neutral in Y2020p (-0.07pp) but loses on
  returns anyway. Y2019 V1 boosted stops +4.40pp on a 6.69% base (weekend fills catch the
  2019 downdrafts).

## SECONDARY: 2021-2026 replica gate (oc_k2placebo ledger; dSum5y>=+0.273, sum-half>=4/5)

| year x variant | n | base | norm | gain | timing pct | block pct |
|---|---|---|---|---|---|---|
| 2021-09-24 V1 | 4171 | 0.911273 | 0.812577 | -0.098696 | 2.30 | 4.00 |
| 2022-09-24 V1 | 4059 | 0.832599 | 0.836513 | +0.003914 | 34.87 | 29.57 |
| 2023-09-24 V1 | 5352 | 2.099814 | 1.936828 | -0.162986 | 0.10 | 0.30 |
| 2024-09-24 V1 | 3958 | 3.197390 | 3.201078 | +0.003688 | 2.20 | 0.80 |
| 2025-09-24 V1 | 4772 | 0.677229 | 0.706165 | +0.028936 | 66.13 | 63.14 |
| 2021-09-24 V2 | 4171 | 0.911273 | 0.773975 | -0.137298 | 0.70 | 0.50 |
| 2022-09-24 V2 | 4059 | 0.832599 | 0.800456 | -0.032143 | 16.58 | 10.49 |
| 2023-09-24 V2 | 5352 | 2.099814 | 2.149251 | +0.049438 | 54.35 | 42.36 |
| 2024-09-24 V2 | 3958 | 3.197390 | 3.159521 | -0.037869 | 0.10 | 0.10 |
| 2025-09-24 V2 | 4772 | 0.677229 | 0.753196 | +0.075968 | 98.00 | 98.00 |

- V1: gains -0.099/+0.004/-0.163/+0.004/+0.029; dSum5y=-0.225 (<+0.273 FAIL), sum-half=3/5
  (FAIL). Timing never >=95 (best 66.1 in 2025).
- V2: gains -0.137/-0.032/+0.049/-0.038/+0.076; dSum5y=-0.082 (<+0.273 FAIL), sum-half=2/5
  (FAIL). Only 2025 timing-significant (98.0/98.0 with +0.076) — one year cannot clear the
  +0.273 placebo-p95 bar; 2021/2024 timing collapses to 0.1-0.7.
- SECONDARY pass = dSum5y>=+0.273 AND >=4/5: V1 FAIL, V2 FAIL (dSum and sum-half).
- 2023 kills V1 (-0.163, timing 0.1): weekend sizing fades the 2023 trend year; 2021 kills
  V2 (-0.137, timing 0.7). Round-trip ~4-8 bps bounds all effects (largest single-year gain
  +0.076 is dust against the bar).

## Engine vs G2: NOT RUN (per PLAN, valid negative)

- Gate required PRIMARY pass AND SECONDARY pass for the same variant; no variant
  passes either leg (PRIMARY 0/4 and 2/4 + COVID fail both; SECONDARY dSum fail both), so no
  4-phase engine, no exposure-matched constant control, no Bybit S5 row, no G2
  reproduction row in this study (G2 5.41/16.91/16.82 quoted from v421, not rerun).
- Candidate-credibility checks: (1) fit-free/sign-stable PASS by construction (timestamps
  only, frozen UTC windows, no fits); (2) beats exposure control FAIL (norm gains negative
  or dust vs the 1.0-mult no-change row); (3) Bybit leg NOT RUN; (4) pre-sample leg FAIL.
  1/4 — adopt nothing.

## Leakage checklist

- Feature timing: calendar mults use the decision time's own weekday/hour only, known at T;
  no price and no future bar enters the trigger; truncation-tested on synthetic grids
  (tests/test_oc_d_calendar.py).
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; Sat/Sun, 00-08 UTC, 1.25/1.2, seeds 20261007/20261008, BLOCK 42 all
  frozen ex-ante, never scanned; no statistic from any test year feeds any choice;
  pre-sample years never used for any fit (there is nothing to fit).
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  perms reassign mults within (year, shift) only (timing uniform, block-42 chronological).
- Gate costs inside reused replica outcomes (maker 0.0002/taker 0.00055, adverse long
  funding 0.0001/8h). Coverage: all fills joined (exact match on the (shift, T) panel,
  0 missing via causal ffill); 15 unknown kinds (0.15%) excluded from rates only.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).

## What worked and what did not

- Worked: panels reproduce the calendar geometry exactly (V1 28.6% weekend bars = 2/7,
  V2 33.3% session bars = 8/24); both ledgers reproduce to the digit; stop recompute matches
  oc_cboostpre kind totals exactly (verbatim logic confirmed); V2 Y2017 timing 96.5/block
  99.0 with +0.054 and V2 2025 timing 98.0/98.0 with +0.076 show the tilt occasionally
  aligns with rebounds — but never enough to clear either gate.
- Did not: everywhere else — V1 helps 0/4 pre-sample years; V2 2/4 but COVID-negative;
  V1 pooled stops +1.01pp (borderline breach); V2 Y2020p boosted stops +7.47pp; secondary
  dSums (-0.225/-0.082) miss +0.273 by an order of magnitude; sum-halves 3/5 and 2/5.
  Thin-book weekend/session overshoot does not survive the crash legs it is supposed to be
  orthogonal to (COVID Thursday neutrality does not save the leg).
- Post-hoc log: one pre-outcome test-expectation fix (flat-tape outcome_kind level 110 ->
  100; the helper was correct, the test's synthetic level was underwater) fixed before the
  first passing run — no method/threshold/window touched after any outcome. No other change.

## Vietnamese verdict

Cả hai biến thể đều rớt cả hai cổng: pre-sample V1 giúp 0/4 năm còn V2 giúp 2/4 nhưng chân
COVID Y2020p âm sâu (-0,09/-0,16, bắt buộc sống sót nhưng chết), stop gộp V1 +1,01pp chạm
ngưỡng fail còn V2 tăng stop chân COVID +7,47pp; 2021-2026 dSum -0,23/-0,08 dưới xa +0,273
dù V2 năm 2025 timing 98 với +0,08.
Calendar không phải edge độc lập mà là đòn bẩy theo thời điểm của chân crash — tilt giờ/ngày
không cứu được drawdown nó cam kết trung lập.
Kết luận: REJECT cả V1 lẫn V2 — không engine, không adopt, không cần prospective engine.
