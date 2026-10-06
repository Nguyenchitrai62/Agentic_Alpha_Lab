# oc_underwater REPORT: time under water on the continuous 4-phase mix

Method (frozen in PLAN.md): continuous mix 1/4 each, no reset,
e,mn = `v388.mix(runs,row,g1)` ONLY (g0 = 2021-09-24 04:00, g1 = 2026-09-23
12:00 UTC, 1h); window t > 2021-09-24 00:00 UTC (43809 hours, 1825.4 days).
P = cummax(e), dd = 1-mn/P (peak from eq, trough from eq_min, same as
`reset_metric.year_reset`). Episode = peak-to-e-recovery excursion with max dd
> 5 % (nested 5 % crossings do NOT split; recovery on eq; censored at grid end).
Depth = max dd x 100. Checks: mn <= e everywhere (viol 0.0); full-path DD
reproduces official numbers EXACTLY (G2 16.82, D13BF 14.86); episode max =
full-path DD. Post-hoc informed, REPORTING ONLY (no selection). One process,
no 1m, peak RAM < 1 GB. All five years are research data; findings need
prospective validation. Repro:
`research/tournament/oc_underwater/{PLAN.md,compute_underwater.py,results.json}`;
test `tests/test_oc_underwater.py`. Dates below are UTC (hour precision in
results.json, day precision here).

## Headline (both rows, continuous mix, no reset)

row | final eq (x) | full-path DD | episodes > 5 % | underwater median / p90 / max (days) | time > 5 % | time > 10 %

- R2B1D17BFG2 (v421, deployment) | 26.39 | 16.82 | 47 | 8.71 / 63.31 / 149.33 | 29.29 % (534.6 days equiv) | 4.85 % (88.5 days equiv)
- R2B1D13BF (v424, conservative) | 19.53 | 14.86 | 35 | 10.54 / 100.75 / 148.83 | 26.81 % (489.5 days equiv) | 4.32 % (78.9 days equiv)

No censored (unrecovered) episode: every excursion recovered on eq before the
grid end 2026-09-23 12:00. All recoveries are eq-recoveries; eq_min stays <= eq.

## R2B1D17BFG2: every episode deeper than 5 % (peak -> trough -> recovery)

depth | peak | trough | recovery | days to trough | days under water

- 16.82 | 2023-04-17 | 2023-06-14 | 2023-07-13 | 58.88 | 87.83
- 14.71 | 2024-01-03 | 2024-01-03 | 2024-02-20 | 0.04 | 48.12
- 13.80 | 2023-07-14 | 2023-10-02 | 2023-10-30 | 80.50 | 108.75
- 13.18 | 2022-07-20 | 2022-11-10 | 2022-12-17 | 112.67 | 149.33
- 13.17 | 2024-03-05 | 2024-03-05 | 2024-03-11 | 0.17 | 6.21
- 12.87 | 2024-07-05 | 2024-07-16 | 2024-09-06 | 10.75 | 63.29
- 12.25 | 2024-06-07 | 2024-06-07 | 2024-07-04 | 0.12 | 26.75
- 10.94 | 2025-10-07 | 2025-10-11 | 2026-02-06 | 4.25 | 121.42
- 10.61 | 2025-09-24 | 2025-09-25 | 2025-09-29 | 0.83 | 4.83
- 10.53 | 2024-01-02 | 2024-01-03 | 2024-01-03 | 0.92 | 0.92
- 10.38 | 2022-05-10 | 2022-05-12 | 2022-06-20 | 2.17 | 41.00
- 10.33 | 2022-01-10 | 2022-01-22 | 2022-01-23 | 11.50 | 12.58
- 9.47 | 2023-12-09 | 2023-12-11 | 2023-12-14 | 1.75 | 5.33
- 8.93 | 2026-02-28 | 2026-03-04 | 2026-04-17 | 4.38 | 48.25
- 8.70 | 2024-12-09 | 2024-12-09 | 2024-12-10 | 0.88 | 1.04
- 8.53 | 2024-09-06 | 2024-09-27 | 2024-10-29 | 20.75 | 52.25
- 8.27 | 2024-02-28 | 2024-02-28 | 2024-02-29 | 0.00 | 0.79
- 8.25 | 2026-06-24 | 2026-08-18 | 2026-08-21 | 54.71 | 57.50
- 8.19 | 2026-06-06 | 2026-06-15 | 2026-06-24 | 8.79 | 17.92
- 7.82 | 2023-11-13 | 2023-11-14 | 2023-11-15 | 0.88 | 1.67
- 7.61 | 2026-09-05 | 2026-09-15 | 2026-09-18 | 9.92 | 13.00
- 7.40 | 2024-11-10 | 2024-11-10 | 2024-11-11 | 0.08 | 0.25
- 7.30 | 2024-10-29 | 2024-11-03 | 2024-11-07 | 4.83 | 9.00
- 7.20 | 2023-01-24 | 2023-01-24 | 2023-01-29 | 0.62 | 5.54
- 7.13 | 2024-04-02 | 2024-04-13 | 2024-06-04 | 11.46 | 63.33
- 7.08 | 2023-02-02 | 2023-03-14 | 2023-03-29 | 40.62 | 55.12
- 7.03 | 2022-02-16 | 2022-03-31 | 2022-03-31 | 43.46 | 43.50
- 7.01 | 2025-05-23 | 2025-07-04 | 2025-07-18 | 42.62 | 55.92
- 6.94 | 2025-07-24 | 2025-07-24 | 2025-07-27 | 0.08 | 3.50
- 6.70 | 2025-05-13 | 2025-05-18 | 2025-05-22 | 4.88 | 8.21
- 6.69 | 2023-11-02 | 2023-11-02 | 2023-11-05 | 0.46 | 3.00
- 6.35 | 2023-01-17 | 2023-01-18 | 2023-01-19 | 0.75 | 1.96
- 6.33 | 2021-11-21 | 2021-12-04 | 2021-12-14 | 13.17 | 23.58
- 5.98 | 2024-11-12 | 2024-11-12 | 2024-11-12 | 0.00 | 0.08
- 5.94 | 2026-08-28 | 2026-08-30 | 2026-09-03 | 2.88 | 6.58
- 5.90 | 2021-10-27 | 2021-10-27 | 2021-11-09 | 0.17 | 12.83
- 5.74 | 2023-11-21 | 2023-11-22 | 2023-12-04 | 0.17 | 12.25
- 5.72 | 2024-11-13 | 2024-11-13 | 2024-11-15 | 0.08 | 1.75
- 5.56 | 2025-01-30 | 2025-02-02 | 2025-02-03 | 3.42 | 4.38
- 5.54 | 2024-12-03 | 2024-12-03 | 2024-12-03 | 0.04 | 0.08
- 5.41 | 2026-08-22 | 2026-08-22 | 2026-08-22 | 0.00 | 0.08
- 5.40 | 2024-11-12 | 2024-11-12 | 2024-11-12 | 0.00 | 0.33
- 5.40 | 2024-11-12 | 2024-11-13 | 2024-11-13 | 0.21 | 0.75
- 5.36 | 2021-11-10 | 2021-11-10 | 2021-11-19 | 0.12 | 8.71
- 5.21 | 2025-02-03 | 2025-02-06 | 2025-02-14 | 3.04 | 10.50
- 5.03 | 2024-12-03 | 2024-12-03 | 2024-12-06 | 0.00 | 2.46
- 5.01 | 2023-11-09 | 2023-11-09 | 2023-11-10 | 0.00 | 0.33

## R2B1D13BF: every episode deeper than 5 % (peak -> trough -> recovery)

depth | peak | trough | recovery | days to trough | days under water

- 14.86 | 2023-04-17 | 2023-06-14 | 2023-07-13 | 58.88 | 87.75
- 14.26 | 2024-03-05 | 2024-03-05 | 2024-03-13 | 0.17 | 7.67
- 13.85 | 2024-01-02 | 2024-01-03 | 2024-02-21 | 1.00 | 49.50
- 13.55 | 2024-07-05 | 2024-07-16 | 2024-11-09 | 10.79 | 126.96
- 13.32 | 2023-07-14 | 2023-10-02 | 2023-10-31 | 80.50 | 109.42
- 11.62 | 2024-06-07 | 2024-06-07 | 2024-07-04 | 0.12 | 26.75
- 10.21 | 2022-07-20 | 2022-08-19 | 2022-12-16 | 29.58 | 148.83
- 10.18 | 2025-09-24 | 2025-09-25 | 2025-09-29 | 0.83 | 4.79
- 10.12 | 2025-10-07 | 2025-10-11 | 2026-02-05 | 4.25 | 121.17
- 8.87 | 2022-01-10 | 2022-01-22 | 2022-01-28 | 11.50 | 17.17
- 8.87 | 2026-02-28 | 2026-03-04 | 2026-04-17 | 4.38 | 48.25
- 8.66 | 2023-12-09 | 2023-12-11 | 2023-12-14 | 1.75 | 5.33
- 8.66 | 2024-02-28 | 2024-02-28 | 2024-03-02 | 0.00 | 2.21
- 8.29 | 2026-06-24 | 2026-08-18 | 2026-08-21 | 54.71 | 57.50
- 8.26 | 2026-06-06 | 2026-06-15 | 2026-06-24 | 8.79 | 17.88
- 7.77 | 2022-05-10 | 2022-05-12 | 2022-06-14 | 2.17 | 35.04
- 7.26 | 2025-05-23 | 2025-07-04 | 2025-07-18 | 42.62 | 56.00
- 7.23 | 2026-09-05 | 2026-09-15 | 2026-09-18 | 9.92 | 13.00
- 7.10 | 2024-12-09 | 2024-12-09 | 2024-12-10 | 0.88 | 1.08
- 6.89 | 2024-11-10 | 2024-11-10 | 2024-11-11 | 0.08 | 0.25
- 6.86 | 2023-11-12 | 2023-11-14 | 2023-11-15 | 2.33 | 3.12
- 6.64 | 2023-01-24 | 2023-01-24 | 2023-01-29 | 0.62 | 5.50
- 6.57 | 2022-02-10 | 2022-03-25 | 2022-04-01 | 42.92 | 49.88
- 6.30 | 2023-02-02 | 2023-03-14 | 2023-03-29 | 40.62 | 55.04
- 6.16 | 2025-05-13 | 2025-05-18 | 2025-05-22 | 4.88 | 8.12
- 6.11 | 2024-04-01 | 2024-04-13 | 2024-06-04 | 12.21 | 64.25
- 6.08 | 2025-07-24 | 2025-07-24 | 2025-07-27 | 0.08 | 3.50
- 5.97 | 2023-01-17 | 2023-01-18 | 2023-01-20 | 0.75 | 2.25
- 5.77 | 2024-11-12 | 2024-11-12 | 2024-11-12 | 0.00 | 0.08
- 5.71 | 2023-11-02 | 2023-11-02 | 2023-11-05 | 0.50 | 3.04
- 5.52 | 2024-11-13 | 2024-11-13 | 2024-11-15 | 0.04 | 1.71
- 5.51 | 2026-08-28 | 2026-08-30 | 2026-09-03 | 2.88 | 6.58
- 5.24 | 2024-11-12 | 2024-11-13 | 2024-11-13 | 0.21 | 0.75
- 5.23 | 2024-11-12 | 2024-11-12 | 2024-11-12 | 0.00 | 0.38
- 5.12 | 2025-02-03 | 2025-02-06 | 2025-02-14 | 3.04 | 10.54

## What hurts most (both rows agree on the calendar)

- Worst: spring 2023 (peak 2023-04-17, trough 2023-06-14, recovered mid-July
  2023): G2 -16.82 % over 87.8 days under water; D13BF -14.86 % over 87.8 days.
- Longest: summer-autumn 2022 (peak 2022-07-20): G2 -13.18 %, 149.3 days under
  water (trough only on 2022-11-10, recovered 2022-12-17); D13BF -10.21 %,
  148.8 days (recovered 2022-12-16). A slow 5-month grind, not one crash bar.
- Sharpest: 2024-01-03 and 2024-03-05 are one-bar shocks (trough same day,
  depth 13-15 % on the conservative eq_min mark) but eq needs 6-50 days to
  make a new high; 2024-06-07 (-12 %) needs ~27 days.
- Recent: 2025-10-07 -> recovery Feb 2026 (~121 days, -11 % G2 / -10 % D13BF);
  the user starting Oct 2025 lives 4 months under water before a new high.

## Tom tat tieng Viet cho tai lieu trien khai (nguoi dung se trai qua dieu gi)

- Cau hinh trien khai R2B1D17BFG2 (BOT): trong 5 nam co 47 lan "chim" sau hon
  5 % duoi dinh. Mot nua so lan chi can duoi 9 ngay la co dinh cao moi, nhung
  1/10 so lan keo dai tren 63 ngay, lau nhat 149 ngay (~5 thang, he-thu 2022).
  Tong cong ban se song ~29 % thoi gian (535/1825 ngay) o muc thap hon dinh
  cu tren 5 %, va ~5 % thoi gian (89 ngay) thap hon tren 10 %. Muc chim sau
  nhat -16.8 % (thang 4-7/2023, 88 ngay moi ve dinh); cac cu chim -10..-15 %
  thuong can 1-4 thang de lap dinh moi, ke ca khi day chi la 1 cay nen xau
  (03/01/2024, 05/03/2024). Day KHONG phai loi nhuan deu moi tuan.
- Ban than trong R2B1D13BF: it lan chim hon (35 lan), sau nhat -14.9 %
  (cung thang 4-7/2023), lau nhat 148.8 ngay (he-thu 2022), ~27 % thoi gian
  duoi dinh tren 5 %, ~4 % thoi gian duoi tren 10 %. Doi lai loi nhuan 5 nam
  thap hon (19.5x so voi 26.4x cua G2).
- Di an tien that gan nhat de hinh dung: tu 07/10/2025 phai cho toi dau thang
  02/2026 (~121 ngay) tai khoan moi vuot dinh cu, giua chang co luc am sau
  nhat -11 %.

## Caveats / post-hoc log

1. Post-hoc informed by design: rows picked after seeing five years; labelled,
   no PROMISING gate, no selection. Continuous-mix (no-reset) convention per
   assignment; per-year reset DDs differ (official: G2 max yearly 16.91,
   D13BF 14.98).
2. Conservative mark: trough from eq_min (intraday/4h lows), peak and recovery
   from eq closes. Same-day depth (e.g. 2024-01-03) is the eq_min touch; a
   user watching closes sees less that day but waits the same days for a new
   high. No 1m data loaded, so the gate DD (max of 4h-close and 1m-marked) is
   NOT evaluated here.
3. (none yet — no post-hoc change; PLAN frozen before outcomes.)

## One-line verdict

REPORTING ONLY: G2 lives ~29 % of the 5 years > 5 % under water (47 episodes,
worst -16.8 % / 88 days, longest 149 days in 2022) and D13BF ~27 % (35
episodes, worst -14.9 % / 88 days, longest 149 days) — every excursion
recovered before 2026-09-23, none censored.
