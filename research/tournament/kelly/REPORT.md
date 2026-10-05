# kelly worker report (saved by the leader from the worker's hand-back, 2026-10-05)
Bar-open features (17) + k + deployed tp + lsig (log 2 x std of 168 closed hourly returns); stop event y_dep < -2 sig; HGB depth 3,
lr 0.05, 300 it, min leaf 200, cross-fitted j % 2; size = clip(c max(mu, 0) / V, 0, 2), c from training OOF predictions.
Gain vs deployed (equal exposure), 2021 / 2022 / 2023 / 2024 / total:
- V1 quantile_kelly: -0.151 / +0.970 / +0.792 / +0.228 / +1.838 (graduates)
- V2 meanvar:        +1.094 / +1.884 / +0.690 / +1.053 / +4.720 (graduates 4/4)
- V3 bucket_ev:      +1.202 / +1.298 / +0.328 / +0.562 / +3.390 (graduates 4/4)
Worst day per year V2 -0.687 / -0.655 / -0.689 / -0.481 vs deployed -0.434 / -1.915 / -0.577 / -0.703 (worse in calm years).
Daily Sharpe deployed 5.27 / 0.72 / 7.58 / 5.31 vs V2 5.59 / 3.44 / 7.75 / 6.35. Equal-volatility rescaling keeps the gains (+4.65).
Post-hoc (not a variant): mean-only sizing +8.33 equal notional; V2 skips ~20 % of rungs, 30-40 % at the cap 2.
Caveats: no capital budget / margin in the harness; concentration at the cap in crashes must be checked by the engine.
