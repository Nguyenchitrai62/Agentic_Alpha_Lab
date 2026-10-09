# oc_presampleshort REPORT — re-scoring the stored pre-sample book-member predictions at SHORT horizons

Method per PLAN.md (pre-registered; one implementation correction logged
below, definitions unchanged). Stored predictions read-only:
oc_presamplebook preds_*.csv (TV) + oc_presampleflow preds_*.csv
(FLOW/PREMIUM/stored BLEND), 7 anchors each. Target identical to
oc_bookichorizon per (t,coin,h): y = (open[t+h*4h]/open[t]-1)/sigma[t],
sigma = trailing-360-bar std of 1-bar open returns (min120, ddof1, causal).
Price histories rebuilt with each worker's own construction (verified:
rebuilt test-bar opens match the stored csv opens exactly, max rel diff
0.00e+00): TV pre-sample = spot 1m-built 4h; TV reference = perp 4h
(BTC ma_ribbon, others xs_universe); FLOW/PREMIUM/BLEND all years =
stitched spot (1m-built for t<2020-10-01 + spot_majors after). h in
{1,2,6,18,42} 4h bars (=4h,8h,1d,3d,7d). Metrics per (series,year,h):
pooled Spearman IC + 95% block bootstrap CI (L=max(h,6), B=500, seed 7),
per-coin IC, TS mean (mean of 4 coins), XS mean + CI. Test set = exactly
the stored rows of each preds file (identical across h; book 2020-03-01 is
truncated at 2020-09-23 with 1241 bars, flow 2020-03-01 runs the full 2190
bars). Full numbers in results.json (140 rows: 4 series x 7 y x 5 h).
Deployed-book context below is oc_bookichorizon FINAL (pooled TS-driven
+0.02..+0.04 at h=1..18, 4/4 dev years; h=42 flips 2022).

## 1. TV (rebuilt TV-only member): pooled IC per (year, h) [95% block CI]

| h | 2019-03 | 2019-09 | 2020-03* | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| 1 (4h) | +0.133 [+0.11,+0.16] | +0.151 [+0.13,+0.18] | +0.137 [+0.10,+0.17] | +0.142 [+0.11,+0.17] | +0.138 [+0.11,+0.16] | +0.129 [+0.10,+0.15] | +0.175 [+0.15,+0.20] |
| 2 (8h) | +0.110 [+0.08,+0.14] | +0.124 [+0.09,+0.16] | +0.088 [+0.04,+0.14] | +0.107 [+0.07,+0.14] | +0.106 [+0.07,+0.14] | +0.092 [+0.06,+0.13] | +0.132 [+0.10,+0.16] |
| 6 (1d) | +0.084 [+0.03,+0.13] | +0.102 [+0.05,+0.15] | +0.053 [-0.01,+0.12] | +0.074 [+0.02,+0.13] | +0.076 [+0.03,+0.13] | +0.059 [+0.02,+0.10] | +0.102 [+0.06,+0.15] |
| 18 (3d) | +0.034 [-0.04,+0.11] | +0.080 [+0.01,+0.15] | +0.035 [-0.06,+0.14] | +0.065 [-0.02,+0.16] | +0.093 [+0.02,+0.17] | +0.028 [-0.04,+0.10] | +0.105 [+0.04,+0.17] |
| 42 (7d) | +0.021 [-0.06,+0.10] | +0.070 [-0.03,+0.17] | +0.033 [-0.11,+0.18] | +0.042 [-0.08,+0.16] | +0.050 [-0.05,+0.16] | +0.000 [-0.10,+0.09] | +0.016 [-0.08,+0.10] |

\* 2020-03-01 TV: truncated test set (1241 bars, COVID crash inside).
TS mean ≈ pooled every year (h=1: +0.134/+0.152/+0.138/+0.141/+0.138/
+0.128/+0.174); per-coin h=1 is 4/4 positive in ALL 7 years, h=6 is 4/4
positive in ALL 7 years. XS mean at h=1: +0.079/+0.051/+0.051/+0.083/+0.071/
+0.096/+0.104 (positive all 7, ~2x smaller than TS -- same TS-driven shape
as the deployed book). h=42 pooled CIs all cross 0 (replicates the ~0
presamplebook finding on its own yardstick).

## 2. FLOW (rebuilt spot-order-flow family): pooled IC [CI]

| h | 2019-03 | 2019-09 | 2020-03 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| 1 | +0.018 [-0.00,+0.04] | -0.006 [-0.02,+0.01] | +0.015 [-0.01,+0.03] | +0.042 [+0.02,+0.06] | +0.009 [-0.01,+0.03] | +0.030 [+0.01,+0.05] | +0.036 [+0.02,+0.06] |
| 2 | +0.021 [-0.00,+0.05] | -0.014 [-0.04,+0.01] | +0.010 [-0.02,+0.04] | +0.037 [+0.01,+0.06] | -0.002 [-0.02,+0.02] | +0.010 [-0.01,+0.04] | +0.024 [+0.00,+0.05] |
| 6 | +0.025 [-0.01,+0.06] | -0.020 [-0.05,+0.01] | +0.009 [-0.03,+0.05] | +0.019 [-0.01,+0.05] | -0.021 [-0.05,+0.01] | +0.005 [-0.03,+0.04] | +0.008 [-0.02,+0.04] |
| 18 | +0.052 [+0.01,+0.10] | -0.009 [-0.06,+0.04] | +0.023 [-0.04,+0.08] | +0.026 [-0.02,+0.07] | +0.001 [-0.05,+0.05] | +0.031 [-0.01,+0.08] | -0.011 [-0.06,+0.03] |
| 42 | +0.066 [-0.03,+0.15] | -0.006 [-0.09,+0.07] | +0.007 [-0.08,+0.09] | +0.017 [-0.06,+0.10] | +0.006 [-0.06,+0.07] | +0.020 [-0.03,+0.07] | +0.010 [-0.04,+0.05] |

Pre-sample: all CIs cross 0 except 2019-03 h=18 (marginal, no neighbour
corroboration); signs flip year to year (2019-09 negative at h=1/2/6).
Reference: weak h=1 trace (2021/2023/2024 CIs exclude 0, size +0.03..+0.04)
that vanishes by h=6. XS mean is ~0 in all 28 cells (|XS| <= 0.035).
Verdict per family: NO stable pre-sample short-horizon skill; nothing with
the deployed book's 4/4-year +0.02..+0.04 stability.

## 3. PREMIUM (rebuilt Coinbase-premium family): pooled IC [CI]

| h | 2019-03 | 2019-09 | 2020-03 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| 1 | +0.031 [-0.00,+0.07] | +0.024 [-0.01,+0.06] | -0.005 [-0.04,+0.03] | -0.014 [-0.05,+0.02] | +0.008 [-0.03,+0.04] | +0.018 [-0.02,+0.05] | +0.011 [-0.03,+0.05] |
| 2 | +0.032 [-0.02,+0.09] | +0.009 [-0.04,+0.05] | -0.003 [-0.05,+0.04] | -0.022 [-0.07,+0.03] | +0.007 [-0.04,+0.06] | +0.038 [-0.01,+0.08] | -0.010 [-0.06,+0.04] |
| 6 | +0.020 [-0.05,+0.09] | -0.004 [-0.07,+0.06] | -0.027 [-0.08,+0.02] | -0.028 [-0.09,+0.03] | -0.014 [-0.08,+0.05] | +0.059 [-0.00,+0.12] | -0.039 [-0.10,+0.03] |
| 18 | +0.004 [-0.12,+0.13] | +0.055 [-0.05,+0.15] | -0.002 [-0.08,+0.07] | -0.093 [-0.20,+0.01] | -0.041 [-0.14,+0.06] | +0.040 [-0.05,+0.14] | -0.087 [-0.18,+0.02] |
| 42 | -0.034 [-0.20,+0.15] | +0.078 [-0.05,+0.20] | +0.073 [-0.02,+0.16] | -0.168 [-0.28,-0.04] | -0.018 [-0.14,+0.11] | +0.072 [-0.04,+0.18] | -0.051 [-0.16,+0.06] |

All 35 pooled CIs cross 0 except the known 2021-h42 negative outlier
(already reported in oc_presampleflow; does not persist). Structural note:
XS is VOID for PREMIUM in all 35 cells (xs_n = 0) -- the 5 premium features
are market-wide (same values joined to every coin by t, exactly as the
deployed add_cb does), so the fitted pred is near-identical across the 4
coins each bar and no cross-sectional rank exists. There is no XS dimension
to judge this family on; its TS/pooled is ~0 at every horizon in pre-sample
AND reference alike. Verdict: NO.

## 4. BLEND (stored 0.8*FLOW + 0.2*PREM): pooled IC [CI]

| h | 2019-03 | 2019-09 | 2020-03 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| 1 | +0.026 [+0.01,+0.05] | +0.003 [-0.02,+0.02] | +0.015 [-0.00,+0.04] | +0.038 [+0.02,+0.06] | +0.011 [-0.01,+0.03] | +0.034 [+0.01,+0.06] | +0.039 [+0.02,+0.06] |
| 6 | +0.032 [-0.00,+0.07] | -0.016 [-0.05,+0.02] | +0.006 [-0.04,+0.04] | +0.012 [-0.03,+0.05] | -0.020 [-0.05,+0.02] | +0.023 [-0.02,+0.06] | +0.004 [-0.04,+0.05] |
| 42 | +0.048 [-0.04,+0.14] | +0.014 [-0.07,+0.10] | +0.016 [-0.08,+0.10] | -0.022 [-0.11,+0.06] | +0.012 [-0.06,+0.09] | +0.039 [-0.02,+0.10] | -0.004 [-0.07,+0.05] |

Inherits FLOW (0.8 weight): one marginal pre-sample cell (2019-03 h=1, CI
barely excludes 0, no corroboration at h=2/6 or in the other pre-sample
years), otherwise ~0. Verdict: NO stable pre-sample short-horizon skill.

## Key question

**In the pre-sample years 2019-2020, are the short-horizon (h=1..18) ICs
positive like the deployed book's 2021-2025 ICs, for which member families?
YES for TV only -- and emphatically so: the rebuilt TV-only member has
h=1 pooled IC +0.13..+0.15 in all three pre-sample years (every CI excludes
0, per-coin 4/4 positive, TS≈pooled, XS positive), decaying to +0.09..+0.12
at h=2 and +0.05..+0.10 at h=6 -- the same sign as the deployed book but
~5x the size (deployed FINAL h=1 is +0.018..+0.024). NO for the other three:
rebuilt spot-FLOW, Coinbase-PREMIUM and their BLEND are ~0 at every short
horizon in pre-sample (all CIs cross 0 bar one marginal BLEND cell; signs
flip; XS ~0 or structurally void). What the presample studies measured as
"~0 skill" was the 7-day label (h=42) -- this study replicates that ~0 at
h=42 for all four families -- but the TV family was never ~0 at short
horizons, in ANY year 2019-2024. Stated plainly: these are REBUILT members
(TV-only pooled HGBR; SPOT order-flow; market-wide premium), not the
deployed perp-flow blend -- the TV result generalises the FEATURE family
(TV indicators carry short-horizon time-series rank skill on both spot and
perp, 2019-2024), not any deployed weight.**

## What failed / limits (honest)

- TV's +0.13..+0.17 at h=1 is ~5x the deployed book's +0.02..+0.04 and needs
  a sober reading: it is a rank IC on a vol-normalised target, not a PnL;
  the presamplebook diagnostic book (sized on the 7d label, next-bar fills)
  earned drift x exposure, not this IC. Whether the TV short-horizon rank
  survives costs/SL-TP/engine sizing is NOT shown here (IC diagnostic only).
- FLOW's reference-year h=1 trace (+0.03..+0.04, 3/4 CIs exclude 0) does not
  extend to pre-sample and dies by h=6; with 140 pooled cells, isolated
  marginal CIs (2019-03 FLOW h=18, 2019-03 BLEND h=1) are expected noise.
- PREMIUM XS is structurally void (xs_n=0 all cells); the family can only be
  judged TS/pooled, both ~0.
- Test sets differ slightly across families (book vs flow row sets; 2020-03
  TV truncated, flow full) -- per PLAN each series is scored on exactly its
  stored rows, so cross-family n differs in 2019-2020. Within-family
  year-to-year comparison is exact.
- Vol-normalisation (trailing-360 sigma) is the one pre-registered choice;
  raw forwards were not scored. Early-2019 sigma still warms up from 2017-18
  regimes (min120 guards the worst of it).

## Post-hoc disclosure

First compute run scored the flow family on the book file's bar list,
truncating flow 2020-03-01 to the book's 1241 bars (pooled_n=4964) against
PLAN's "exactly the stored rows of each preds file". Corrected before any
REPORT was written (per-series bar sets; flow 2020-03-01 now 2190 bars);
cached parts were deleted and the run repeated. No definition changed; the
corrected numbers above are the only reported rows.

## Leakage / execution statement

Stored preds are frozen fits (workers' PLANs: training rows obey label end
< anchor - 7d; read-only here). sigma[t] uses only opens <= t (full
per-study history, trailing 360, min120). Forward returns are scoring
labels only, never features. No test-year statistic entered any choice
(horizons/B/L/seed/weights fixed in PLAN; blend is the stored column; no
most-recent year exists in this study). Feature timing: stored pred at bar t
is known at t's close; target uses opens at t (known) and t+h (future
label). Fill timing: N/A (IC diagnostic, no fills claimed). No fits in this
study. Tests: causality/truncation + hand-checked synthetic
(tests/test_oc_presampleshort.py).

## Verdict (tiếng Việt, kết luận chính)

- Chỉ họ TV có skill chân trời ngắn (+0.13..+0.15 ở h=1, dương cả 3 năm pre-sample lẫn 4 năm reference, TS≈pooled, XS dương) — cùng dấu với book G2 nhưng lớn gấp ~5 lần; FLOW/PREMIUM/BLEND rebuilt đều ~0 ở mọi h ngắn trong pre-sample (CI phủ 0, đổi dấu, XS ~0 hoặc void cấu trúc).
- Kết quả presample "~0" trước đây chỉ đúng ở nhãn 7 ngày (h=42 tái lập ~0 cho cả 4 họ); ai dùng TV features cho horizon ngắn (4h–1d) thì có cơ sở đăng ký hướng mới, còn alpha 7-ngày từ các họ này thì đóng lại.
- Đây là thành viên rebuilt (TV-only, spot-flow), KHÔNG phải blend perp-flow đang deploy — không đổi deployment sau nghiên cứu này.
