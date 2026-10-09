# oc_d_riskparity — REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS12 #3: risk-parity rung sizing (equal dollar-risk per rung).
size = base x (4sg/stopDist), open-to-stop parity: V1 mults 4/(k+4) on the base
5-rung grid with frozen 4sg stops (sizing-only overlay); V2 rungs 2.5/3.5/4.5/5.5sg
with depth-scaled stops 4/5/6/7sg + parity mults 4/(k'+s') (rebuilt fills +
outcomes, backstop still 8sg). No fit anywhere. STATUS: DONE — both reproductions
pass exactly; V1/V2 pre-sample + 2021-2026 replica + placebos + stop tables complete.
Tests: 7 pass (`tests/test_oc_d_riskparity.py`).

## Reproduction gates: PASS both

- Pre-sample REF ledger n = 9731 (legs 909/2986/3115/2721), base 4-phase-mean sums
  2.313362 / 2.678870 / 0.577643 / 0.297538 (exact to 1e-6).
- 2021-2026 REF ledger n = 22312, base sums 0.911273 / 0.832599 / 2.099814 /
  3.197390 / 0.677229, sum5y = 7.718304 (exact).
- V2 rebuilt ledgers (own fill sets): pre-sample n = 6783
  (legs 620/2074/2183/1906);
  2021-2026 n = 15523 (legs 2910/2860/3761/2706/3286).
  Fewer fills is mechanical (4 rungs, deeper levels fill less) — disclosed.

## PRIMARY: pre-sample 2017-2020 replica (norm = tilted/realised_mean, gain = norm-base)

| year x variant | n (REF/V2) | base | norm | gain | timing pct | block pct |
|---|---|---|---|---|---|---|
| Y2017 V1 | 909 / — | 2.313362 | 2.309535 | -0.003826 | 42.46 | 39.26 |
| Y2017 V2 | 909 / 620 | 2.313362 | 1.581262 | -0.732099 | 100.00 | 100.00 |
| Y2018 V1 | 2986 / — | 2.678870 | 2.674174 | -0.004696 | 42.96 | 66.03 |
| Y2018 V2 | 2986 / 2074 | 2.678870 | 1.901802 | -0.777068 | 100.00 | 100.00 |
| Y2019 V1 | 3115 / — | 0.577643 | 0.577626 | -0.000017 | 47.35 | 62.64 |
| Y2019 V2 | 3115 / 2183 | 0.577643 | 0.524637 | -0.053006 | 100.00 | 100.00 |
| Y2020p V1 | 2721 / — | 0.297538 | 0.360061 | +0.062523 | 99.50 | 97.50 |
| Y2020p V2 | 2721 / 1906 | 0.297538 | 0.061231 | -0.236307 | 89.51 | 67.23 |

- Helps (gain>0): V1 1/4 (only Y2020p); V2 0/4 (none).
- Timing/block pcts are DIAGNOSTIC (parity is not a timing rule, pre-registered):
  V1 timing 42/43/47/99.5, block 39/66/63/97.5; V2 timing 100/100/100/89.5,
  block 100/100/100/67.2. High V2 timing pcts mean the rung composition beats
  rung-shuffled nulls yet still loses to doing nothing — the grid itself is the problem.
- COVID leg Y2020p separately: V1 +0.062523 (helps); V2 -0.236307 (fails).

## Crash risk (stop-hit share; kinds VERBATIM mu=1.0; unknowns: 15 V1-pre / 15 REF-pre counted; V2 kinds recorded in rebuild)

Pre-sample per-rung-group stop rates (REF kinds): shallow {0,1} / mid {2} / deep {3,4}:
- Y2017: base 3.30% | shallow 3.40% / mid 1.23% / deep 4.81% | parity-weighted 3.26% (delta -0.04%)
- Y2018: base 3.29% | shallow 3.10% / mid 2.96% / deep 4.33% | parity-weighted 3.25% (delta -0.04%)
- Y2019: base 6.69% | shallow 5.49% / mid 8.41% / deep 9.36% | parity-weighted 6.53% (delta -0.15%)
- Y2020p: base 7.58% | shallow 5.27% / mid 8.21% / deep 14.39% | parity-weighted 7.25% (delta -0.33%)
- Pooled: base 5.58% vs parity-weighted 5.42% (delta -0.16%) — no FAIL (<= +1pp).
V2 pre-sample (own stops): shallow(2.5sg) 4.23% / mid(3.5sg) 4.52% / deep(4.5+5.5sg) 6.12%;
pooled V2 4.67%, parity-weighted 4.54% vs REF base 5.58% (delta -1.04%) — no FAIL,
but V2 stops LESS because wider stops are hit less often while losing MORE per stop.
2021-2026 V1 groups: deep rungs stop ~2x the base rate every year (pooled base 4.13% vs parity 4.01%, delta -0.12%) — shape helps stops marginally, returns not at all.

## SECONDARY: 2021-2026 replica gate (dSum5y >= +0.273 AND sum-half >= 4/5)

| year x variant | base | norm | gain |
|---|---|---|---|
| 2021-09-24 V1 | 0.911273 | 0.902208 | -0.009064 |
| 2021-09-24 V2 | 0.911273 | 0.542350 | -0.368923 |
| 2022-09-24 V1 | 0.832599 | 0.829611 | -0.002988 |
| 2022-09-24 V2 | 0.832599 | 0.550995 | -0.281604 |
| 2023-09-24 V1 | 2.099814 | 2.110947 | +0.011134 |
| 2023-09-24 V2 | 2.099814 | 1.572852 | -0.526961 |
| 2024-09-24 V1 | 3.197390 | 3.138160 | -0.059231 |
| 2024-09-24 V2 | 3.197390 | 2.009790 | -1.187600 |
| 2025-09-24 V1 | 0.677229 | 0.640069 | -0.037160 |
| 2025-09-24 V2 | 0.677229 | 0.382090 | -0.295139 |

- V1: dSum5y = -0.097309, sum-half = 1/5 → FAIL.
- V2: dSum5y = -2.660227, sum-half = 0/5 → FAIL.

## Engine vs G2: NOT RUN (no variant passes PRIMARY + SECONDARY)

- V1 PRIMARY: 1/4 helps (needs >= 3/4) → FAIL (COVID leg helps alone).
- V2 PRIMARY: 0/4 helps, COVID leg -0.236 → FAIL.
- V1 SECONDARY: dSum5y -0.097 < +0.273, 1/5 < 4/5 → FAIL.
- V2 SECONDARY: gate failed (see row above) → FAIL.
- Per the frozen plan, ENGINE (G2 reproduction 5.41/16.91/16.82, exposure-matched
  constant control, Bybit S5) runs ONLY for a variant passing both gates.
  No engine claim is made; no full-path DD exists for these variants.
- Candidate-credibility checks: (1) fit-free rule passes by construction; (2) beats
  exposure control — N/A, no engine; (3) Bybit leg — N/A, no engine; (4) pre-sample
  leg — FAILS for both. Verdict: REJECT.

## Leakage checklist

- Feature timing: V1 uses rung index only (no features); V2 levels/stops use O/sg
  available at bar open T only; V2 fills/outcomes causal on 1m (live 16..238 strict
  trade-through, stop-first); truncation-tested in tests/test_oc_d_riskparity.py.
- Label windows: no labels fit anywhere. Fit windows: no fits — every constant
  (2.5/3/3.5/4/5, 4/5/6/7, 4/(k+s), seeds 20261008/20261009, BLOCK 42) is frozen
  ex-ante arithmetic, never scanned; no statistic from any test year feeds any choice.
- Fill timing: inherited replica cores; perms reassign mults within (year[, coin, phase]) only.
- Gate costs inside all replica outcomes (maker 0.0002/taker 0.00055, adverse long
  funding 0.0001/8h). Coverage: V1 joins exact on rung (0 misses); V1-pre unknowns 15
  (0.15%); V1-2021 unknowns 0; V2 fill deltas disclosed above.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).

## What failed and why

- V1 (pure parity sizing on the G2 grid): exposure-normalised gains are ~0 in
  2017-2019 (-0.004/-0.005/-0.000) and +0.063 in the COVID leg — the parity shape
  (0.62..0.44 across rungs) is too flat to matter outside the crash leg, and the
  2021-2026 gate is negative (dSum5y -0.097, 1/5). Round-trip 4-8 bps bounds it all.
- V2 (depth-scaled grid + wider stops): loses EVERY pre-sample year (-0.73/-0.78/-0.05/-0.24).
  Mechanism: dropping the earning 3.0sg rung (oc_contrib: shallow earns every year) and
  pushing size to 4.5/5.5sg rungs that fill less but bleed more per stop outweighs the
  lower stop frequency; wider stops cut stop counts (4.67% vs 5.58%) while deepening
  the average stop loss. Crash-reducing by construction in COUNT, not in P&L.
- This closes the direction per the 2-variant limit (Kelly-sized tails UP and breached DD;
  parity sizes them DOWN and still loses — the deep rungs cannot be rescued by sizing).

## Vietnamese verdict

V1 chỉ giúp đúng chân COVID (+0,06) còn 3 năm pre-sample ~0 và 2021-2026 âm (dSum -0,10, 1/5).
V2 thua cả 4 năm pre-sample (-0,73/-0,78/-0,05/-0,24): bỏ rung 3.0sg đang kiếm tiền và dời size
ra rung sâu stop rộng — ít stop hơn nhưng mỗi stop lỗ nặng hơn, không cứu được rung sâu.
Kết luận: REJECT cả hai variant, đóng hướng risk-parity rung sizing, không cần bằng chứng prospective.

