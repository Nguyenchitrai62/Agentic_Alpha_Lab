# oc_d_ddrank — REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS12 #1 drawdown-rank rotation (buy the deepest coin harder): rank coins by
trailing-30d DD-depth of own 4h closes (frozen 180 bars / min 60, closes with
close_time <= T only); V1 deepest x1.25 / shallowest x0.75 / middle x1.0; V2 top-2
deep x1.25 else x1.0 (frozen K2-family mults, no fit). 4h closes only (spot
pre-sample OK). Replica PRIMARY + 2021-2026 SECONDARY; engine only if PRIMARY
pass AND SECONDARY pass. B1/cap/stops kept in every leg by inheritance (replica
has no budget/cap; engine not run).

STATUS: DONE — no engine (valid negative). Pre-sample ledger reproduces exactly
(n=9731, legs 909/2986/3115/2721, base 2.313362/2.678870/0.577643/0.297538);
2021-2026 ledger reproduces exactly (n=22312, sum5y 7.718304). Rank-shuffle /
timing / block placebos (1000/yr) + stop-kind recompute (15 unknown, as cboostpre)
complete. Tests: 3 pass (`tests/test_oc_d_ddrank.py`).

## PRIMARY: pre-sample replica 2017..2020-09-23 (SPOT fills/exits, perp gate costs)

| year x variant | n | base | norm | gain | rank pct | timing pct | block pct | boosted% / deweighted% |
|---|---|---|---|---|---|---|---|---|
| Y2017 V1 | 909 | 2.313362 | 2.336324 | +0.022963 | 93.71 | 73.93 | 24.18 | 0.307 / 0.512 |
| Y2018 V1 | 2986 | 2.678870 | 2.444739 | -0.234132 | 13.39 | 0.10 | 0.10 | 0.278 / 0.226 |
| Y2019 V1 | 3115 | 0.577643 | 0.480913 | -0.096730 | 42.46 | 1.40 | 8.29 | 0.203 / 0.285 |
| Y2020p V1 | 2721 | 0.297538 | 0.194863 | -0.102674 | 11.89 | 0.80 | 0.80 | 0.241 / 0.283 |
| Y2017 V2 | 909 | 2.313362 | 2.326682 | +0.013320 | 97.30 | 76.92 | 0.10 | 0.541 / 0.000 |
| Y2018 V2 | 2986 | 2.678870 | 2.594740 | -0.084130 | 50.55 | 0.10 | 0.30 | 0.533 / 0.000 |
| Y2019 V2 | 3115 | 0.577643 | 0.540190 | -0.037453 | 19.38 | 9.39 | 25.97 | 0.460 / 0.000 |
| Y2020p V2 | 2721 | 0.297538 | 0.263699 | -0.033839 | 50.45 | 10.39 | 13.49 | 0.480 / 0.000 |

- Helps (gain>0): V1 1/4 (only Y2017 +0.023), V2 1/4 (only Y2017 +0.013).
- COVID leg Y2020p (must survive): V1 -0.103, V2 -0.034 — BOTH NEGATIVE (fail).
- Rank-shuffle (primary null): V1 93.7/13.4/42.5/11.9, V2 97.3/50.6/19.4/50.5
  (only V2-Y2017 >= 95; Y2018 timing collapses to 0.1-0.3 for both).
- Timing (diagnostic, cross-sectional idea): V1 73.9/0.1/1.4/0.8,
  V2 76.9/0.1/9.4/10.4. Block: V1 24.2/0.1/8.3/0.8, V2 0.1/0.3/26.0/13.5.
- PRIMARY pass = >=3/4 AND Y2020p>0 AND pooled stop<=+1pp: V1 FAIL, V2 FAIL.

## Crash risk (stop-hit share; kinds recomputed verbatim mu=1.0; 15 unknown)

| year | base stop% | V1 boosted% (delta) | V1 deweighted% (delta) | V2 boosted% (delta) | base TP% |
|---|---|---|---|---|---|
| Y2017 | 3.30 | 1.08 (-2.23) | 4.30 (+1.00) | 2.03 (-1.27) | 80.31 |
| Y2018 | 3.29 | 2.77 (-0.52) | 2.23 (-1.06) | 2.52 (-0.77) | 55.82 |
| Y2019 | 6.69 | 4.27 (-2.42) | 5.63 (-1.06) | 6.57 (-0.11) | 55.27 |
| Y2020p | 7.58 | 8.55 (+0.97) | 5.99 (-1.59) | 8.44 (+0.86) | 59.49 |

- Pooled: base 5.58%; V1 boosted 4.55% (-1.03pp), V1 de-weighted 4.69% (-0.89pp); V2 boosted 5.28% (-0.30pp).
- Stop-rate check (fail if pooled boosted >+1pp): V1 PASS (-1.03pp), V2 PASS (-0.30pp) —
  the rule does NOT lever stops; it just buys the wrong dips (Y2020p boosted stops
  +0.86/+0.97pp on a 7.58% base, same crash-leg mechanism as every tilt).

## SECONDARY: 2021-2026 replica gate (oc_k2placebo ledger; dSum5y>=+0.273, sum-half>=4/5)

| year x variant | n | base | norm | gain | rank pct | timing pct | block pct |
|---|---|---|---|---|---|---|---|
| 2021-09-24 V1 | 4171 | 0.911273 | 0.906142 | -0.005130 | 13.19 | 46.55 | 4.40 |
| 2022-09-24 V1 | 4059 | 0.832599 | 0.701205 | -0.131393 | 0.10 | 0.30 | 0.30 |
| 2023-09-24 V1 | 5352 | 2.099814 | 2.255636 | +0.155822 | 100.00 | 100.00 | 88.01 |
| 2024-09-24 V1 | 3958 | 3.197390 | 3.255518 | +0.058128 | 100.00 | 98.50 | 13.29 |
| 2025-09-24 V1 | 4772 | 0.677229 | 0.738877 | +0.061648 | 99.80 | 98.70 | 65.53 |
| 2021-09-24 V2 | 4171 | 0.911273 | 0.930801 | +0.019529 | 10.99 | 74.03 | 27.27 |
| 2022-09-24 V2 | 4059 | 0.832599 | 0.799131 | -0.033468 | 0.30 | 14.79 | 6.29 |
| 2023-09-24 V2 | 5352 | 2.099814 | 2.175882 | +0.076068 | 99.80 | 99.40 | 65.53 |
| 2024-09-24 V2 | 3958 | 3.197390 | 3.286764 | +0.089373 | 100.00 | 100.00 | 80.22 |
| 2025-09-24 V2 | 4772 | 0.677229 | 0.721395 | +0.044167 | 99.70 | 99.10 | 73.33 |

- V1: gains -0.005/-0.131/+0.156/+0.058/+0.062; dSum5y=+0.139 (<+0.273 FAIL), sum-half=3/5 (FAIL). Rank 13.2/0.1/100/100/99.8; timing 46.6/0.3/100/98.5/98.7.
- V2: gains +0.020/-0.033/+0.076/+0.089/+0.044; dSum5y=+0.196 (<+0.273 FAIL), sum-half=4/5 (pass alone). Rank 11.0/0.3/99.8/100/99.7; timing 74.0/14.8/99.4/100/99.1.
- SECONDARY pass = dSum5y>=+0.273 AND >=4/5: V1 FAIL, V2 FAIL (dSum).
- 2022 kills both (V1 -0.131 rank 0.1, V2 -0.033 rank 0.3): deepest-coin sizing
  levers the 2022 bear flushes (LUNA/FTX), exactly the epicenter risk pre-registered
  in IDEAS12 (SOL-FTX, XRP-SEC). 2023-2025 gains are timing-significant but too small
  to clear the +0.273 placebo-p95 bar (round-trip ~4-8 bps bounds all effects).

## Engine vs G2: NOT RUN (per PLAN, valid negative)

- Gate required PRIMARY pass AND SECONDARY pass for the same variant; no variant
  passes either leg (PRIMARY 1/4 + COVID fail both; SECONDARY dSum fail both), so no
  4-phase engine, no exposure-matched constant control, no Bybit S5 row, no G2
  reproduction row in this study (G2 5.41/16.91/16.82 quoted from v421, not rerun).
- Candidate-credibility checks: (1) fit-free/sign-stable PASS by construction (no fits,
  distribution-free rank); (2) beats exposure control FAIL (norm gains negative/dust);
  (3) Bybit leg NOT RUN; (4) pre-sample leg FAIL. 1/4 — adopt nothing.

## Leakage checklist

- Feature timing: DD-depth at T uses closes with close_time <= T only (window
  C[j-180..j-1], current C[j-1]; tested bar never in its own window; ranking at (s,T)
  uses only DD available at T; truncation-tested on real pre-sample bars.
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; 180/60/1.25/0.75/top-2/seeds 20261007-09+BLOCK 42 all frozen
  ex-ante, never scanned; no statistic from any test year feeds any choice; pre-sample
  years never used for any fit (there is nothing to fit).
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  perms reassign mults within year only (rank-shuffle within (y,s,T) bars; timing
  uniform within year; block-42 within (y,sym,s)).
- Gate costs inside reused replica outcomes (maker 0.0002/taker 0.00055, adverse long
  funding 0.0001/8h). Coverage: all fills joined (0 missing mults via causal ffill);
  15 unknown kinds (0.15%) excluded from rates only; early-bar NaN DD -> mult 1.0 (counted).
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).

## What worked and what did not

- Worked: stop-rate check passes (boosted stops do NOT rise pooled); Y2017 tiny gains
  (+0.023/+0.013, V2 rank 97.3); 2023-2025 secondary gains positive with strong
  rank/timing significance (V1 2023 rank 100/timing 100, V2 2024 rank 100/timing 100).
- Did not: everywhere else — pre-sample 2018/2019/2020p all negative both variants;
  2022 negative both; dSums (+0.139/+0.196) miss +0.273; COVID leg fails (must-survive
  violated). Buying the deepest coin buys the epicenter (2022 bear, 2020 COVID crash).
- Post-hoc log: none to the method (one pre-report syntax typo in compute_ddrank_2021.py, fixed before
  its first run, produced no outcome; two test-expectation typos fixed before passing;
  no method/threshold/window touched after any outcome). Post-report presentation fix only:
  stop-rate table values were written as fractions (0.03) under a % header — corrected to
  percentages (3.30) from tmp/stop_presample.json; no number changed.

## Vietnamese verdict

Cả hai biến thể đều rớt cả hai cổng: pre-sample chỉ giúp 1/4 năm và chân COVID Y2020p âm
(-0,10/-0,03, bắt buộc sống sót nhưng chết), 2021-2026 dSum +0,14/+0,20 dưới +0,273 dù 2023-2025
dương; mua đồng sâu nhất là mua đúng tâm chấn (2022 bear, COVID crash).
Stop gộp không tăng (V1 -1,03pp, V2 -0,30pp) nhưng edge không đủ bù round-trip 4-8 bps.
Kết luận: REJECT cả V1 lẫn V2 — không engine, không adopt, không cần prospective engine.

