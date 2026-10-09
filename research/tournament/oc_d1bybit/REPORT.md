# oc_d1bybit — REPORT (2026-10-08)

Question: does the downside-share dip tilt D1 keep its dev edge under frictions
and on BYBIT prices (S5)? Same check oc_c2bybit did for C2, now for D1
(risk = risk_D1 trailing-6d downside-RV share, x1.25/x0.75 outer quintiles, frozen
oc_downshare fits.json D1). PLAN.md was written BEFORE any outcome; no definition
changed after outcomes. Engine via heavy_slot (sequential shifts, heartbeat every
600 s; 12 engine rows = 48 phase sims). pytest 4/4.

STATUS: DONE. 12 engine rows (REF/D1 x base/S1/S2/S3/S4/S5, 4 phases each) +
CPU scoring + D1-vs-C2 Spearman. Reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- Base REF == `v421_result.json` G2 (R2B1D17BFG2) all 5 years + 5y 5.410 +
  full-path DD 16.82.
- Base D1 == `oc_downshare` dev_table/last_table (dev 2.921/12.59, 3.604/16.09,
  6.541/15.74, 10.191/8.19; Y4 4.591/13.38; full-path DD 15.98).
- REF_S1..S5 == `oc_c2bybit` tmp/c2bybit_table.json REF_S* (== v421_audit
  ROBUST.md G2 friction row) to the digit, so friction implementations are
  exactly the existing ones. Comparison valid.

## 1. Dev4 (anchors 2021..2024 — NO contamination risk: downside share uses only
4h closes, no model, no pretraining; C2 side-by-side dev still possibly-contaminated)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| fric | REF | D1 | gap dev4 |
|---|---|---|---|
| base | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 \| 5.601/2.588/16.91 | 2.921/12.59, 3.604/16.09, 6.541/15.74, 10.191/8.19 \| 5.776/2.921/16.09 | +0.175 |
| S1 | 1.975/11.18, 2.592/17.45, 4.853/16.01, 9.712/8.31 \| 4.740/1.975/17.45 | 2.204/12.95, 2.791/16.94, 5.140/15.83, 9.294/8.22 \| 4.821/2.204/16.94 | +0.081 |
| S2 | 2.513/11.09, 3.132/16.91, 5.624/15.82, 10.479/8.29 \| 5.391/2.513/16.91 | 2.856/12.53, 3.455/16.30, 6.298/15.83, 9.993/8.21 \| 5.613/2.856/16.30 | +0.222 |
| S3 | 2.070/11.85, 2.476/17.32, 4.346/16.03, 9.798/8.36 \| 4.628/2.070/17.32 | 2.345/13.43, 2.958/16.72, 4.619/15.86, 9.309/8.27 \| 4.773/2.345/16.72 | +0.145 |
| S4 | 2.363/11.06, 2.915/17.31, 4.422/17.08, 10.460/8.27 \| 4.992/2.363/17.31 | 2.600/13.33, 3.340/16.55, 4.800/16.89, 10.013/8.20 \| 5.149/2.600/16.89 | +0.157 |
| S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 \| 4.994/2.129/18.11 | 2.182/13.29, 3.320/17.31, 5.190/16.51, 9.899/9.16 \| 5.107/2.182/17.31 | +0.113 |

S5 y2021 is a SHORT window (Bybit from 2021-11-15, labelled). No losing dev year
in any row. D1 DD <= REF DD by maxDD in 5/6 dev4 rows (base 16.09 vs 16.91).

C2 side-by-side dev4 gaps (oc_c2bybit, read-only): base +0.138, S1 +0.113,
S2 +0.171, S3 +0.136, S4 +0.248, S5 +0.261. D1 beats C2 on base/S2/S3/S4 gaps,
trails on S1/S5.

## 2. Post-release year Y4 2025-09-24..2026-09-23 (clean BUT already scored once by oc_downshare for base+D1 — every Y4 number here is a labelled DIAGNOSTIC re-score under frictions)

| fric | REF R/DD | D1 R/DD | gap Y4 |
|---|---|---|---|
| base | 4.648/12.90 | 4.591/13.38 | -0.057 |
| S1 | 3.900/13.61 | 3.863/13.82 | -0.037 |
| S2 | 4.501/12.98 | 4.428/13.45 | -0.073 |
| S3 | 4.380/12.75 | 4.315/13.07 | -0.065 |
| S4 | 4.522/13.54 | 4.501/13.76 | -0.021 |
| S5 | 4.443/12.37 | 4.418/12.66 | -0.025 |

D1 LOSES the clean year under every friction (diagnostic), same sign as base.
Absolute Y4 stays below the 5.0 gate in both rows (D1 base 4.591). Contrast C2
Y4 gaps (read-only): base +0.106, S1 +0.088, S2 +0.097, S3 +0.102, S4 +0.096,
S5 +0.115 — C2 beats REF in the clean year under every friction while D1 loses
under every friction.

## 3. Five-year path + full-path DD (v388.mix from 2021-09-24)

| fric | REF 5y R/W/DD/full | D1 5y R/W/DD/full | gap 5y |
|---|---|---|---|
| base | 5.410/2.588/16.91/16.82 | 5.538/2.921/15.98/15.98 | +0.128 |
| S1 | 4.571/1.975/17.45/17.37 | 4.628/2.204/16.94/16.82 | +0.057 |
| S2 | 5.212/2.513/16.91/16.86 | 5.375/2.856/16.30/16.21 | +0.163 |
| S3 | 4.578/2.070/17.32/17.24 | 4.681/2.345/16.72/16.62 | +0.103 |
| S4 | 4.898/2.363/17.31/17.24 | 5.019/2.600/16.89/16.45 | +0.121 |
| S5 | 4.883/2.129/18.11/18.09 | 4.969/2.182/17.31/17.26 | +0.086 |

All D1 full-path DDs <= 20 (worst 17.26 on S5) and below the matching REF
full-path DD in every friction. No losing year anywhere. All-trade win rates
move <= 0.001 (e.g. base Y4 D1 0.6276 vs REF 0.6267; S5 Y4 D1 0.6251 vs REF
0.6247) — the tilt is sizing, not trade selection. C2 5y gaps for reference:
base +0.132, S1 +0.108, S2 +0.157, S3 +0.129, S4 +0.217, S5 +0.232.

## 4. D1-vs-C2 multiplier Spearman per year (frozen fits + frozen features, CPU-only)

Intersection of frozen feature rows (majors x 4 shifts, T in year y) with both
risk_D1 and ch_q10 present; mults via anchor-y fits only:

| year | n | Spearman rho |
|---|---|---|
| 2021 | 43800 | 0.2024 |
| 2022 | 43800 | 0.0202 |
| 2023 | 43800 | -0.0074 |
| 2024 | 43800 | 0.0299 |
| 2025 | 43785 | 0.1090 |

Different signals: |rho| <= 0.20 every year, near zero in 2022-2024. D1's
friction behaviour is independent evidence from C2, not a re-test of the same tilt.

## 5. Leakage / causality checks (how verified)

- Feature timing: downside share for bar open T uses ONLY the 36 closes ending
  at bars closing <= T on that shift's grid (inherited oc_downshare);
  `test_d1_truncation_causal_on_frozen_features` recomputes D1 multipliers from
  a truncated frozen feature table — identical on the kept prefix; multiset
  subset of {0.75, 1.0, 1.25}.
- Label windows: fits.json reused frozen (harness rows t_exit < A - 7d,
  shift-0 only); year y uses anchor-y fit only, never a later anchor; 2022/2023
  direction -1 is the frozen Spearman outcome, not a choice.
- Fit windows: no refit here; S5 is a price-source switch, not a fit; Spearman
  uses only frozen anchor-y fits + frozen features.
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in
  source; S5 live0 2021-11-15 + Bybit dir); engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001
  per 8h; S1 stress maker 0.0004 / taker 0.0012).
- `tests/test_oc_d1bybit.py` 4/4 pass.

## 6. Post-hoc log

- No PLAN definition changed after outcomes. All 12 rows scored as
  pre-registered; reproduction gates passed to the digit (REF_base==v421 G2,
  D1_base==oc_downshare D1, REF_S1..S5==oc_c2bybit REF_S*).
- S1 TAKER = 0.0007 + 0.0005 = 0.0012 (same as robust_v421.py / oc_c2bybit).

## Vietnamese verdict (3 lines)

- D1 hơn REF về dev4 (+0.08 tới +0.22) và đường 5 năm (+0.06 tới +0.16) ở base và mọi ma sát S1-S4 lẫn giá Bybit S5 (dev4 +0.113, 5y +0.086), full-path DD luôn ≤ 20 (tệ nhất 17.26 ở S5) và thấp hơn REF mọi hàng; nhưng năm sạch diagnostic THUA ở mọi ma sát (-0.02 tới -0.07, base -0.057) và mức tuyệt đối 4.59%/tháng dưới cổng 5%.
- D1 là tín hiệu khác hẳn C2 (Spearman |rho| ≤ 0.20, gần 0 ở 2022-2024); C2 giữ gap dương ở năm sạch mọi ma sát (+0.09 tới +0.12) còn D1 âm mọi ma sát — edge ma sát của D1 không chuyển sang năm sạch như C2.
- Kết luận: robust ma sát theo tiêu chí dev4+5y (YES) nhưng THUA năm sạch mọi hàng nên không adopt; giữ D1 làm bằng chứng độc lập rằng tilt dip giữ edge dev dưới ma sát, không đưa vào G2 lúc này.
