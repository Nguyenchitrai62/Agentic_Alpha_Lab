# oc_b7thresh — REPORT (2026-10-08; PLAN frozen before any outcome — REPORT ONLY, B7 stays 4 sigma / 7 days)

Robustness surface of the cascade boost B7 (dip x1.5 for W days after a > k sigma 4h move,
cascadedelay definition verbatim, only k x W vary). Grid k in {3.5,4.0,4.5} x W in {3,5,7,10}d
= 12 cells, mult 1.5. NOT a selection: nothing here changes B7; no pick is made on any year.

STATUS: DONE — grids built (main 53,877 rows; pre 27,383 rows; nesting k35>k40>k45 and
W10>W07>W05>W03 asserted), replica surface on both ledgers complete (12 cells x timing+block
1000 perms), engine for REF + 4 corners complete (dev + last-once), tests 7 pass.
Reproduction gates pass: k40_W07/W03 == B7/B3 replica rows exactly (main dSum +2.946/+2.018;
pre gains identical to cboostpre); REF reproduces v421 G2 dev years, Y4, 5y and full-path DD
to the digit; stage-last dev segments equal stage-dev.

CONTAMINATION LABELS (pre-registered): main 2021-2026 replica and every Y4 engine number are
CONTAMINATED (idea formed after seeing the delay replica incl. post-release year) — labelled
diagnostics, never selection inputs. Pre-sample 2017-2020 is the clean unseen-years leg.

## Triggers (frozen, causal, verbatim cascadedelay except k)

- Main union triggers/shift (2021-09-24..): k3.5 507/492/499/501, k4.0 338/341/344/328
  (per-year k4.0 s0: 40/50/69/53/52 = 264 total, IDENTICAL to cascadeboost), k4.5 226/238/233/228.
- Pre union triggers/shift: k3.5 204/217/212/209, k4.0 142/154/143/156, k4.5 107/98/99/114
  (per-leg tables in results.json). Early NaN-SIG bars never fire (inert, counted).
- Boosted fill share rises with looser k and longer W (main B7-cell 52-72%, corners 31-87%;
  pre 29-83%); fills cluster in post-cascade downdrafts on every cell (time-bar share < fill share).

## Replica heat A — main 2021-2026 (CONTAMINATED; gain = norm - base per year; timing pct)

| cell | 2021 gain/timing | 2022 | 2023 | 2024 | 2025 screen | dSum5y | helps |
|---|---|---|---|---|---|---|---|
| k35_W03 | +0.094/91.0 | -0.209/9.5 | +0.022/93.8 | +0.104/100 | -0.005/82.9 | +2.19 | 3/5 |
| k35_W05 | +0.170/98.0 | -0.095/32.6 | +0.094/97.7 | +0.108/100 | +0.008/84.5 | +2.98 | 4/5 |
| k35_W07 | +0.186/97.6 | -0.118/26.1 | +0.023/92.0 | +0.087/100 | -0.017/67.6 | +3.14 | 3/5 |
| k35_W10 | +0.048/72.1 | -0.089/28.9 | -0.012/79.3 | +0.076/100 | -0.031/55.6 | +3.13 | 2/5 |
| k40_W03 | +0.022/77.7 | -0.071/42.5 | +0.064/98.9 | +0.083/100 | +0.117/100 | +2.02 | 4/5 |
| k40_W05 | +0.147/96.5 | +0.001/66.3 | +0.173/99.7 | +0.116/100 | +0.123/99.9 | +2.88 | 5/5 |
| k40_W07 =B7 | +0.161/96.6 | +0.011/67.7 | -0.024/85.4 | +0.128/100 | +0.086/98.1 | +2.95 | 4/5 |
| k40_W10 | -0.054/44.7 | +0.045/76.0 | -0.023/80.0 | +0.086/100 | +0.051/94.4 | +2.88 | 3/5 |
| k45_W03 | +0.006/73.8 | -0.056/49.5 | +0.126/99.6 | +0.084/100 | +0.133/100 | +1.70 | 4/5 |
| k45_W05 | +0.138/97.9 | -0.062/49.5 | +0.332/100 | +0.119/100 | +0.133/100 | +2.57 | 4/5 |
| k45_W07 | +0.131/96.1 | -0.008/66.7 | +0.244/99.9 | +0.108/100 | +0.097/99.6 | +2.82 | 4/5 |
| k45_W10 | -0.074/39.9 | -0.012/64.0 | +0.156/99.1 | +0.060/100 | +0.061/97.0 | +2.60 | 3/5 |

- Every cell helps on dSum5y (+1.70..+3.14); no cliff: B7 neighbours all positive on dSum and
  2024 timing is 100.0 in ALL 12 cells. B7 is NOT the argmax (k35_W07 +3.14 > B7 +2.95) and not the
  helps-count leader (k40_W05 5/5 vs B7 4/5, 2023 -0.024 the miss). 2022 is the soft spot for loose
  k (k35_* negative), 2023 the soft spot for B7/W10 at k40.

## Replica heat B — pre-sample 2017-2020 (CLEAN; gain; timing pct; boosted stop delta pp)

| cell | Y2017 gain/t/stopd | Y2018 | Y2019 | Y2020p | helps |
|---|---|---|---|---|---|
| k35_W03 | +0.049/100/-1.78 | +0.075/100/+0.15 | +0.406/100/-3.50 | -0.331/1.1/+5.15 | 3/4 |
| k35_W05 | +0.024/100/-1.35 | +0.015/100/+0.08 | +0.289/99.9/-1.34 | -0.165/14.8/+2.99 | 3/4 |
| k35_W07 | +0.038/100/-1.33 | +0.072/100/+0.12 | +0.090/90.1/+1.21 | -0.093/34.2/+2.02 | 3/4 |
| k35_W10 | +0.072/100/-1.45 | +0.065/100/+0.02 | +0.123/94.4/+0.87 | -0.023/55.5/+1.35 | 3/4 |
| k40_W03 | +0.026/100/-1.50 | +0.049/100/+0.06 | +0.298/100/-3.11 | -0.137/20.4/+3.27 | 3/4 |
| k40_W05 | +0.042/100/-1.55 | -0.027/100/+0.11 | +0.282/100/-2.16 | -0.154/19.5/+2.84 | 2/4 |
| k40_W07 =B7 | +0.046/100/-1.61 | +0.078/100/+0.26 | +0.111/92.3/+0.78 | -0.069/45.4/+1.55 | 3/4 |
| k40_W10 | +0.112/100/-1.83 | +0.073/100/+0.15 | +0.150/96.4/+0.31 | +0.005/69.4/+0.91 | 4/4 |
| k45_W03 | +0.041/99.9/-2.16 | +0.082/100/-0.34 | +0.230/100/-2.60 | -0.210/6.5/+5.19 | 3/4 |
| k45_W05 | +0.059/100/-2.14 | +0.022/100/-0.23 | +0.240/100/-2.29 | -0.137/23.5/+2.79 | 3/4 |
| k45_W07 | +0.085/100/-2.33 | +0.094/100/+0.28 | +0.112/92.0/+0.44 | +0.009/70.0/+0.97 | 4/4 |
| k45_W10 | +0.173/100/-2.54 | +0.115/100/+0.45 | +0.158/95.0/-0.14 | +0.109/91.6/+0.08 | 4/4 |

- Clean-set argmax is k45_W10 (4/4 helps, biggest gains, timing 100/100/95/92, stop deltas flat:
  -2.5/+0.5/-0.1/+0.1pp), NOT B7. B7 is interior: 3/4 helps (Y2020p -0.069), timing 100/100/92/45.
  Longer W fixes Y2020p at every k (W10 gains: -0.023/+0.005/+0.109); shorter W breaks it
  (-0.33/-0.14/-0.21). Tighter k lowers boosted-stop elevation in Y2020p (k45_W10 +0.1pp vs
  k35_W03 +5.2pp). Pooled crash risk stays flat (reported in cboostpre), year-level risk
  concentrates in the COVID leg for short/loose cells.

## Engine — 4 corners + REF (dev4 selection basis; last/Y4 scored ONCE, contaminated diagnostic)

Dev4 (R %/mo / DD): REF 2.588/3.282/6.045/10.677 mean 5.601 W 2.588 DDmax 16.91;
k35_W03 2.818/3.220/8.084/12.443 mean 6.569 W 2.818 DDmax 18.20;
k35_W10 3.198/3.330/8.596/12.788 mean 6.904 W 3.198 DDmax 17.90;
k45_W03 2.613/3.206/7.749/11.834 mean 6.285 W 2.613 DDmax 17.48;
k45_W10 2.831/3.071/8.925/12.352 mean 6.719 W 2.831 DDmax 18.61.
(B7 cited read-only: mean 6.738 W 2.955 DDmax 17.92.)
5y + full-path DD (last, once): REF 5.410 W 2.588 full 16.82 Y4 4.648/12.90;
k35_W03 5y 6.174 full 18.11 Y4 4.606/15.49; k35_W10 5y 6.424 full 17.65 Y4 4.526/15.58;
k45_W03 5y 6.004 full 17.38 Y4 4.887/13.69; k45_W10 5y 6.339 full 18.52 Y4 4.831/13.79
(B7 cited: 5y 6.364 full 17.75 Y4 4.88/13.81). No losing year anywhere; all DD <= 20.
Worst 1m-marked episode every row: peak 2023-04-17 -> trough 2023-06-14 (same crash leg as G2,
deepened 0.9-1.7pp). Sized mean mult: k35_W03 1.277, k35_W10 1.405, k45_W03 1.182, k45_W10 1.309
(B7 1.319). All-trade win rates dev4 0.61-0.70 (sizing only, book win ~0.51-0.54 — below any
manual floor; this study sizes the BOT sleeve).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG excludes the tested bar;
  window strictly after tc; truncation-tested on real bars for k=3.5/4.0/4.5.
- Label windows: none fit anywhere. Fit windows: no fits; grid frozen ex-ante; no statistic from
  any test year feeds any choice; pre-sample years never used for any fit.
- Fill timing: replica live 16..238 strict trade-through + stop-first inherited; engine win_start=5
  + trade-through + stop-first; perms within (year,shift) only, seeds 20261007+y/20261008+y.
- Coverage: no skipped year; all fills joined exactly (0 misses); pre stop rates over known kinds
  only (15 unknown of 9731, inherited). Main replica DD-half not scored from the ledger (no daily
  path) — binding DD check is the engine (all corners <= 20). Gate costs inside replica/engine.
- Spot-vs-perp caveat on every presample number (SPOT fills/exits, perp gate costs, inherited).

## What worked and what did not

- Worked: the boost direction is robust — all 12 cells help on main dSum5y, 10/12 help in 3+ of 4
  clean years, 2024 timing is 100.0 everywhere, corners beat G2 on dev4 mean by +0.68..+1.30pp and
  on 5y by +0.59..+1.01pp with DD <= 20. No knife-edge: B7's neighbours all help.
- Did not: B7 is not the peak on either surface (main dSum leader k35_W07 +3.14; clean leader
  k45_W10 4/4 with the only clean Y2020p gain +0.109). Short/loose cells break the COVID leg badly
  (pre gains to -0.33, boosted stops +5.2pp) while long/tight cells survive it. Y4 diagnostics all
  sit below 5 (4.53-4.89 incl. B7 4.88) — contaminated by construction, proving nothing.
- Plateau answer: B7 (4.0/7) sits INSIDE a broad helpful plateau (not an isolated peak), but off its
  ridge on both sets — longer windows and (clean-set) tighter thresholds do better, at the cost of
  +0.5..+1.7pp DD on the same 2023 crash leg. Tuning to the ridge would be selection on seen years;
  B7 stays frozen.

## Vietnamese verdict

B7 (4,0/7) nằm trong vùng plateau rộng giúp mọi ô (main dSum đều dương, timing 2024 = 100 mọi ô,
4 góc engine đều hơn G2 +0,7-1,3pp mean với DD <= 20), KHÔNG phải đỉnh knife-edge cô lập —
nhưng cũng không phải argmax (main thua k35_W07, clean thua k45_W10 4/4, Y2020p chỉ W dài mới sống).
Giá của boost là đào sâu cùng đoạn drawdown 2023 thêm ~1pp và stop tăng ở chân COVID với ô ngắn/lỏng.
Kết luận: REPORT ONLY — giữ nguyên B7 4 sigma/7 ngày, không chỉnh ngưỡng/cửa sổ theo surface này,
chờ log paper prospective xác nhận.
