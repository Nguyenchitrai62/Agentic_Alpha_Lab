# oc_agentens — REPORT (seed-ensemble R2 dip agents, phase s=0)

## S0 reproduction gate (must pass before screening)

| check | value |
|---|---|
| seed rows (each of 5) / ens rows | 273850 / 273850 |
| S0 vs oc_rlbear V0 overlap | 273850 |
| size_match / tp_match | 1.0000 / 1.0000 |

S0 reproduces the deployed V0 table EXACTLY (hence v376 hidden s0).
Table agreement vs S0 (all rows): size ~0.92, tp ~0.75-0.77 per new seed;
ENS agrees 0.950 / 0.848. Keys aligned across seeds: True.
ENS value counts: size {1.0:215303, 1.5:39167, 0.5:19380},
tp {1.0:157241, 1.5:115086, 0.5:1523}.

## Rung-level screen (majors x rungs 2.5..5.0, outcome = size * y_tableTP, daily sums by exit date)

| year | n | S0 | S101 | S202 | S303 | S404 | ENS | ENS>=S0? |
|---|---|---|---|---|---|---|---|---|
| 2021 | 990 | 4.4849 | 4.4849 | 4.4849 | 4.4849 | 4.4849 | 4.4849 | tie |
| 2022 | 1045 | 0.9238 | 0.6031 | 0.5822 | 0.6836 | 0.6206 | 0.7186 | no (-0.2052) |
| 2023 | 1330 | 6.6272 | 6.9251 | 6.6033 | 6.2937 | 6.3536 | 6.4576 | no (-0.1696) |
| 2024 | 989 | 4.2650 | 4.2978 | 4.3662 | 4.4557 | 4.5576 | 4.2718 | yes (+0.0068) |
| 2025 | 1144 | 1.9059 | 1.4020 | 1.5482 | 1.8047 | 1.4729 | 1.6986 | no (-0.2073) |

Years ENS>=S0: 2/5 (2021 tie, 2024). Worst year sum: S0 0.9238 (2022)
vs ENS 0.7186 (2022) — worse by 0.2052.

## Dispersion of the 5 single seeds (how lucky is the deployed seed?)

| year | range | std | best | S0 rank | S0 - mean |
|---|---|---|---|---|---|
| 2021 | 0.0000 | 0.0000 | S0 (tie) | 1 | +0.0000 |
| 2022 | 0.3416 | 0.1400 | S0 | 1 | +0.2411 |
| 2023 | 0.6315 | 0.2516 | S101 | 2 | +0.0667 |
| 2024 | 0.2925 | 0.1194 | S404 | 5 | -0.1234 |
| 2025 | 0.5039 | 0.2179 | S0 | 1 | +0.2792 |

The deployed seed is the BEST single seed in 2022 and 2025 (incl. the most
recent year), rank 2 in 2023, last in 2024 — i.e. a lucky draw where it
matters most. Seed noise is material (ranges 0.29-0.63 where present) but
the majority vote lands mid-pack, never best, and loses to S0 in both of
S0's best years. 2021 has ZERO dispersion: all 5 tables agree on every
screened fill (size/tp 100%), because the jj=0 fits train on <10k rows so
HGB never engages its stochastic early-stopping split (same mechanism as
documented in v303) — fits are deterministic regardless of seed.

Fill win rates S0/ENS: 2021 0.671/0.671, 2022 0.692/0.695, 2023 0.765/0.765,
2024 0.688/0.686, 2025 0.656/0.654. maxDD S0/ENS: 2021 0.539/0.539,
2022 1.914/1.915, 2023 0.575/0.614, 2024 0.703/0.733, 2025 0.588/0.788.
Dropped fills with missing table rows: 0 in every year.

## Verdict

NOT PROMISING: ensemble beats/matches the deployed seed in only 2/5 years (needs >=3/5) and its worst year (0.7186) is worse than deployed (0.9238).

## Caveats / leakage notes

- Rung-level counterfactual screen only (no engine replay, no costs beyond
  the y's embedded maker/taker/funding); prospective logs still required
  for any winner (none here).
- maxDD is of the cumulative daily-sum path from 0 (absolute units,
  identical for all V); fill WR = mean(out>0), day WR over exit days.
- Leakage checklist: table state at bar-open minutes only; fits/mu/rules
  on t_exit < A-7d; seeds (0/101/202/303/404, v303 convention) fixed in
  PLAN.md before any outcome; ensemble vote uses tables only (no y, no
  test-year statistic); S0 100% match confirms pipeline fidelity.
- No post-hoc changes; scripts are build_ensemble.py + screen_ensemble.py.
