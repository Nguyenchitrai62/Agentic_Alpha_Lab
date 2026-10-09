# oc_vrpgate REPORT — ex-ante vol-premium gate on the r=0.87 weekly straddle

**POST-HOC INFORMED — every row.** Gate idea + thresholds (gap>=0.05,
ratio>=1.15) were picked AFTER seeing V2's yearly IV-RV gaps (+0.10/+0.10 in
2021/2022 vs +0.01/+0.01 in 2023/2024). Frozen rule in PLAN.md (pre-registered
2026-10-07, before any outcome here). Repro: `run_gate.py dev|recent|collect`
(via heavy_slot) + `tests/test_oc_vrpgate.py`. Engine copied from
oc_vrpconsistent/oc_vrpstraddle; originals never edited.

Validations (asserted in-script): G2 baseline reproduces v421_result to the
digit (yearly R/DD, 5y 5.41/W 2.588/DD 16.91); f=0 overlay reproduces G2;
R087 reproduces oc_vrpconsistent R087 standalone + overlay f=0.25 dev4 to the
digit (standalone 0.28/-2.261/30.97; overlay 5.74/3.578/17.22).

## Standalone sleeve dev4 (R %/mo / DD %; f=1.0, fresh E=1.0/anchor)

| year | R087 ungated | G1 gap>=0.05 | G2 ratio>=1.15 |
|---|---|---|---|
| 2021-09-24 | 3.596 / 26.70 (104 tr, win .654, TP23/SL14/Ex67) | 3.092 / 15.14 (45, .689, 9/1/35) | 2.093 / 6.08 (14, .786, 4/0/10) |
| 2022-09-24 | 1.406 / 23.24 (102, .667, 30/20/52) | -0.706 / 29.52 (41, .585, 11/12/18) | -0.327 / 16.70 (15, .600, 5/6/4) |
| 2023-09-24 | -2.261 / 30.97 (102, .539, 17/31/54) | -1.261 / 16.79 (20, .500, 2/8/10) | 0.071 / 2.26 (1, 1.0, 0/0/1) |
| 2024-09-24 | -1.514 / 30.78 (102, .598, 30/29/43) | -0.691 / 12.48 (22, .500, 5/6/11) | -0.046 / 3.96 (3, .667, 1/1/1) |
| dev4 mean / worst / maxDD / losing | 0.28 / -2.261 / 30.97 / 2 | 0.094 / -1.261 / 29.52 / 3 | 0.443 / -0.327 / 16.70 / 2 |

No standalone row is adoptable (all have losing years; R087/G1 fail DD<=20).

## Gate selectivity dev4 (sold / universe; mean gap7 sold vs skipped)

| row | share dev4 | 2021 | 2022 | 2023 | 2024 | gap sold vs skipped (dev4 yrs) |
|---|---|---|---|---|---|---|
| G1 | 128/410 = 31.2% | 43.3% | 40.2% | 19.6% | 21.6% | +0.125/+0.127/+0.088/+0.088 vs -0.125/-0.063/-0.098/-0.110 |
| G2 | 33/410 = 8.0% | 13.5% | 14.7% | 1.0% (1 trade) | 2.9% (3) | ratio sold 1.23-1.31 vs skipped 0.88-0.92 |

The gates separate ex-ante premium as designed (sold weeks have ~+0.09-0.13
gap and ~1.25 ratio vs ~-0.10 gap / ~0.90 skipped), but 2023/2024 offer almost
nothing to sell (G2: 4 coin-weeks in 2 years).

## Overlay on G2 dev4, f=0.25 (yearly-reset R/DD; full-path DD continuous)

| year | G2 | +R087 | +G1 | +G2gate |
|---|---|---|---|---|
| 2021 | 2.588 / 10.86 | 3.578 / 11.23 | 3.386 / 10.38 | 3.129 / 10.38 |
| 2022 | 3.282 / 16.91 | 3.665 / 17.22 | 3.115 / 17.92 | 3.203 / 16.91 |
| 2023 | 6.045 / 15.81 | 5.488 / 15.59 | 5.730 / 15.59 | 6.063 / 15.58 |
| 2024 | 10.677 / 8.27 | 10.372 / 8.21 | 10.506 / 8.27 | 10.667 / 8.27 |
| dev4 mean / worst / maxDD / losing | 5.601 / 2.588 / 16.91 / 0 | 5.740 / 3.578 / 17.22 / 0 | 5.643 / 3.115 / 17.92 / 0 | 5.722 / 3.129 / 16.91 / 0 |
| full-path DD | 16.82 | 17.14 | 17.83 | 16.82 |

Robust choice (pre-registered, overlay dev4 only): all three overlays have
DD<=20, no losing year, mean>=5% — highest dev4 WORST year wins: R087
(3.578 > 3.129 > 3.115). **Winner = R087 ungated.** Vs the assignment bar
(dev4 mean AND worst above G2, DD <= G2+0.5 = 17.41): G1 fails DD (17.92);
G2-gate passes vs G2 (5.722>5.601, 3.129>2.588, 16.91 OK) but trails ungated
R087 on BOTH mean (5.722<5.740) and worst (3.129<3.578) — the gate adds no
value over selling every week. Skipped weeks were mildly diversifying at
overlay scale, so selectivity hurts the worst year.

## Most-recent year 2025-09-24..2026-09-23, scored ONCE (winner R087 + G2 ref)

R087 overlay f=0.25: 4.946 / 15.20 vs G2 4.648 / 12.90 (+0.30 pp, labelled).
R087 standalone: 0.975 / 28.29, 102 trades, win .618, TP31/SL20/Ex51, worst
week 2025-11-27 -11.52%, gap -0.063 (IV 46.5, RV 0.528). Losers were
deliberately NOT scored here (that would be variant comparison on the locked
year).

## Leakage statement

Feature timing: DVOL_0800 = last hourly close <= Friday 08:00; RV7/RV30 use
only 1m bars with open_time < 08:00 Friday (test: truncation + post-gate
spike invariance; short history => NaN => gate skips); S at 08:04 known at
08:05 entry; marks use latest closed hourly DVOL; settlement 07:30..07:59
known at 08:00. Label windows: payoff uses only post-entry minutes. Fit
windows: r=0.87 from pre-existing B.json (not refit); gate thresholds picked
on dev years only — POST-HOC, labelled; recent year scored once for the
frozen winner. Fill timing: options at model marks (no book); first event
09:00, nothing fills in the first 5 min by construction. inexact 1m lookups
dev4: 0.

## Verdict

Negative for the gate idea: neither ex-ante screen beats the ungated sleeve
as a G2 overlay (G1 fails the DD bar and both trail R087 on mean and worst
year), and no standalone row survives losing years/DD. The realistic-priced
sleeve itself overlays G2 fine, but the gate is not the reason.

Tiếng Việt:
Bộ lọc premium không tạo thêm giá trị so với bán mọi tuần (G1 rớt DD, G2 kém R087 cả mean lẫn worst).
Hàng độc lập vẫn có năm lỗ và DD vượt ngưỡng nên không dùng được.
Bác bỏ hướng gate này, không cần kiểm chứng prospective thêm.
