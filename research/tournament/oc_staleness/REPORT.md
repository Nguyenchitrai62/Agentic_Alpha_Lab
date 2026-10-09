# oc_staleness — REPORT: how fast does the book's skill decay with model age?

Method per PLAN.md (pre-registered, no changes after seeing outcomes).
Families: **A** = v92-base + TV(17) + order-level whale flow(6), label 7d vol-norm `y42`,
one pooled HGB; **D** = v103-base + Coinbase-premium CB(5), labels `y6/y18`,
two pooled HGBs, `pred = mean`. Stale cuts `C = 2021/2022/2023-09-17` (native embargo
cutoffs 17d/13d, a subset of "data before C-7d"); fresh = yearly walk-forward HGBs at
`2021..2024-09-24`, same code. Bins = 3-month age bins from each C (8 bins, 24m).
Pooled Spearman IC over 5 majors per bin; labels only where realised `< 2025-09-24`.
Diagnostic P&L (labelled, NOT executable): `w = clip(pred/0.5, -1, 1)`, `pnl = w x next-4h-bar
open return`, gross, no costs. Full numbers in `results.json` / `staleness.csv`; curves in
`staleness_ic.png`. No deployment change.

## 1. Pooled IC vs model age — family A (pred vs y42)

| cut \ age | 0-3m | 3-6m | 6-9m | 9-12m | 12-15m | 15-18m | 18-21m | 21-24m |
|---|---|---|---|---|---|---|---|---|
| stale 2021-09-17 | **0.190** | 0.056 | 0.090 | 0.025 | -0.018 | 0.234 | -0.173 | -0.052 |
| fresh same bars | 0.151 | 0.050 | 0.123 | 0.076 | -0.030 | 0.143 | -0.105 | -0.070 |
| diff F-S | -0.040 | -0.006 | +0.033 | +0.051 | -0.012 | -0.091 | +0.068 | -0.018 |
| stale 2022-09-17 | -0.082 | 0.117 | -0.107 | -0.062 | -0.126 | 0.292 | -0.059 | -0.305 |
| fresh same bars | -0.027 | 0.144 | -0.107 | -0.069 | -0.098 | 0.212 | -0.045 | -0.110 |
| diff F-S | +0.056 | +0.027 | -0.000 | -0.007 | +0.028 | -0.080 | +0.014 | +0.195 |
| stale 2023-09-17 | -0.048 | 0.200 | -0.035 | -0.101 | 0.067 | 0.030 | 0.084 | 0.023 |
| fresh same bars | -0.099 | 0.216 | -0.045 | -0.113 | 0.120 | 0.092 | 0.083 | 0.048 |
| diff F-S | -0.051 | +0.015 | -0.010 | -0.011 | +0.053 | +0.063 | -0.000 | +0.024 |

n = 2740 pooled rows/bin (2735 in the last bin). Halving: 2021-cut halves at 3-6m (0.190 -> 0.056);
2022/2023 cuts have **no positive skill at age 0** (IC0 -0.08/-0.05), so halving is undefined.

## 2. Pooled IC vs model age — family D primary (pred vs y18; secondary vs y6 in brackets)

| cut \ age | 0-3m | 3-6m | 6-9m | 9-12m | 12-15m | 15-18m | 18-21m | 21-24m |
|---|---|---|---|---|---|---|---|---|
| stale 2021 | 0.133 (0.10) | 0.020 (0.06) | 0.124 (0.13) | 0.030 (-0.02) | 0.092 (0.10) | 0.144 (0.17) | -0.148 (-0.16) | 0.039 (0.02) |
| fresh | 0.103 | 0.045 | 0.110 | -0.032 | -0.028 | 0.228 | -0.096 | 0.089 |
| diff F-S | -0.030 | +0.024 | -0.013 | -0.062 | -0.120 | +0.084 | +0.053 | +0.050 |
| stale 2022 | -0.055 (-0.02) | 0.201 (0.19) | -0.111 (-0.12) | 0.084 (0.11) | -0.085 (-0.10) | 0.122 (0.14) | 0.005 (-0.03) | 0.035 (0.07) |
| fresh | -0.030 | 0.231 | -0.091 | 0.083 | -0.116 | 0.157 | -0.092 | 0.154 |
| diff F-S | +0.025 | +0.030 | +0.019 | -0.001 | -0.031 | +0.035 | -0.097 | +0.119 |
| stale 2023 | -0.104 (-0.09) | 0.140 (0.15) | -0.098 (-0.08) | 0.156 (0.14) | 0.015 (-0.01) | -0.166 (-0.14) | 0.077 (0.05) | 0.009 (-0.01) |
| fresh | -0.117 | 0.162 | -0.097 | 0.156 | 0.011 | -0.134 | 0.064 | -0.047 |
| diff F-S | -0.013 | +0.022 | +0.001 | +0.000 | -0.003 | +0.032 | -0.013 | -0.056 |

Halving: 2021-cut halves at 3-6m (0.133 -> 0.020); 2022/2023 cuts no positive skill at age 0.

## 3. What the tables say (no smooth decay)
- **No monotonic decay with age.** Mean IC by age bin (3 cuts averaged) for A:
  0.02 / 0.12 / -0.02 / -0.05 / -0.03 / **0.19** / -0.05 / -0.11 — the peak is at 15-18m, not 0-3m.
  For D: -0.01 / 0.12 / -0.03 / 0.09 / 0.01 / 0.03 / -0.02 / 0.03. Skill is **regime-driven, not
  age-driven**: the same calendar quarter gets the same sign from a 1.5y-old and a 0.5y-old model
  (e.g. 2022-12..2023-03: A stale-2021 +0.23 AND stale-2022 +0.12/+0.14 fresh; 2023-03..06 negative
  for every model old or new).
- **Fresh yearly retraining does not systematically beat frozen models.** Mean over all bins:
  A fresh-minus-stale +0.013, D +0.002; mean |diff| 0.040/0.039 (noise level). Stale beats fresh in
  10/24 A-bins and 12/24 D-bins, sometimes by a lot (A 2021-cut 15-18m: stale 0.234 > fresh 0.143).
- **Halving age is not a useful concept here**: 4 of 6 (family, cut) curves start at IC <= 0, and the
  two that start positive (2021 cuts) "halve" immediately into a regime change, then recover to their
  highest values 15-18m later. There is no 24m half-life to report.
- Diagnostic gross P&L (clip(pred/0.5) x next-bar return, 8-bin sums): A sums +8.5/+11.9/+11.3 per cut
  (all positive); D sums -5.9/+2.3/+4.7 (2021-cut negative despite positive mean IC — direction and
  magnitude weight differently; diagnostic only, no costs, no vol target).

## 4. Recommendation (descriptive, no deployment change)
**Yearly retraining is sufficient for live; no evidence for monthly or quarterly.**
Over 24 months the frozen models track the yearly-retrained ones within ~0.04 IC (mean bias ~+0.01 for
fresh), and both are dominated by regime sign flips that retraining does not fix. Revisit only if a
prospective shadow log shows fresh beating frozen out-of-sample, or if a cheaper trigger (e.g. IC
sign flip over a trailing 3m window) is validated walk-forward. The v280 "fresher helps new regimes"
hypothesis is NOT confirmed here — in 2022-12..2023-03 the older model won.

## 5. Leakage checklist (how checked)
1. Feature timing: reused audited builders unchanged (`v231.tv_features`, `v236.flow_features` on the
   order-level archive, `v111.add_cb`); each row uses inputs <= its bar close (see sysaudit leak report).
2. Label windows: v92 `y` (H=42) / v103 `y6/y18` realised before cutoff (`t+(H+1)*4h < cutoff`); bins only
   where labels end `< 2025-09-24` (tail bars dropped, n=2735 in final bins).
3. Fit windows: native embargo cutoffs (A: C-17d, D: C-13d) are subsets of "before C-7d"; fresh models for
   year Y train only before Y-embargo. Cutoffs + train_rows logged in `results.json:fit_info`.
4. No feedback: no statistic from any scored quarter enters any fit; the 2025-09-24+ data was never read
   (`grid.t < END`, opens truncated, predictions end 2025-09-23).
5. Fill timing: diagnostic uses `open[t+1]` (>= t+1); labelled non-executable gross diagnostic — no
   limit-fill, fee, funding, vol-target or governor claim.

## Verdict (Vietnamese, 3 lines)
- GIỮ nguyên lịch retrain hàng năm: mô hình đóng băng 24 tháng không thua kém retrain hàng năm (chênh IC ~0.01, nhiễu ~0.04).
- Kỹ năng do regime quyết định chứ không decay theo tuổi: cùng một quý, model cũ 1.5 năm và model mới cho cùng dấu IC.
- Cần bằng chứng prospective trước khi chuyển sang retrain quý/tháng; không đổi deployment sau nghiên cứu này.
