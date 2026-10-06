# oc_phasedisp: single-clock dispersion of R2B1D17BFG2

Source: `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl`, strat R2B1D17BFG2, per-phase hourly t/eq/eq_min.
Method: `reset_metric.py` logic restricted to one phase (phase equity rebased to 1.0 at each anchor; R = 100*(end**(1/12)-1), DD = marked peak-to-trough in the 365d segment). Mix = 4 sub-accounts reset to 1/4 each anchor. 5y mean = geometric mean of the five yearly monthly rates. Full-path DD from 2021-09-24, no reset. Script: `phase_disp.py` -> `results.json`. Mix reproduces `v421_result.json` (5.41 / worst 2.588 / DD 16.91 / full 16.82).

## Per anchor year (R %/month, DD %)

| year (anchor->+365d) | phase0 (0h) | phase1 (1h) | phase2 (2h) | phase3 (3h) | 4-phase mix |
|---|---|---|---|---|---|
| 2021-09-24 | 4.567, 13.41 | 2.919, 22.46 | 2.153, 13.70 | 0.188, 15.94 | 2.588, 10.86 |
| 2022-09-24 | 3.571, 16.91 | 3.942, 15.67 | 3.226, 17.39 | 2.312, 17.99 | 3.282, 16.91 |
| 2023-09-24 | 11.249, 14.56 | 4.226, 18.91 | 6.412, 20.07 | -2.431, 43.23 | 6.045, 15.81 |
| 2024-09-24 | 10.023, 10.75 | 9.645, 15.22 | 11.849, 10.14 | 11.040, 10.90 | 10.677, 8.27 |
| 2025-09-24 | 5.427, 11.88 | 3.577, 21.21 | 4.590, 13.69 | 4.905, 14.21 | 4.648, 12.90 |
| 5y mean | 6.923 | 4.834 | 5.592 | 3.102 | 5.410 |
| worst year | 3.571 | 2.919 | 2.153 | -2.431 (losing) | 2.588 |
| max yearly DD | 16.91 | 22.46 | 20.07 | 43.23 | 16.91 |
| full-path DD | 16.91 | 22.46 | 20.07 | 43.55 | 16.82 |

Read: no single clock dominates every year (best year rotates: 2021->p0, 2022->p1, 2023->p0, 2024->p2, 2025->p0); the mix never wins a single year but never loses one either.

## Vi (plain)

Bot chay bon dong ho vi chay mot dong ho duy nhat la danh bac vao may man cua gio cat 4h: chi lech nhau 1-3 gio ma ket qua 5 nam phan tan tu 3.10 den 6.92%/thang, nam te nhat cua mot dong ho don le xuong toi -2.431%/thang (dong ho 3, nam 2023) trong khi hon hop 4 dong ho van duong 2.588%/thang va khong nam nao lo, va drawdown don le te nhat len toi 43.55% full-path (43.23% trong nam 2023) so voi hon hop chi 16.82%, nen gop bon dong ho moi nguoi 1/4 von la cach khoa chenh lech gio chu khong phai de cong them loi nhuan.
