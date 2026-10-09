# oc_fmbookic — REPORT (diagnostic only, nothing selected)

Inputs: `oc_chronos/chronos_features_4shift.parquet` (ch_q10/q50/q90),
`oc_toto/toto_features_4shift.parquet` + `oc_timesfm/timesfm_features_4shift.parquet`
(f_q10/q50/q90) + `oc_kronoshidden/bars_4h_4shift.parquet`. Features (6, fixed):
ch_q50, ch_spr=q90-q10, toto_q50, toto_spr, tfm_q50, tfm_spr. Book yardstick
y=(open[t+h]/open[t]-1)/sigma, sigma=trailing-360 std of 1-bar simple returns
per (sym,shift), min 120, causal (= oc_kronosfeat template, same timing: label
starts at the bar open T where the feature is known). CIs = week-block
bootstrap B=500 (Monday weeks), seeds (11,y,h,k). Y0..Y3 = dev (Chronos
possibly-contaminated; Toto nearly-clean small caveat; TimesFM
possibly-contaminated upper bound); Y4 = 2025-09-24..2026-09-24 = CLEAN for all
three (after Chronos-Bolt 2024-11, Toto ~May-2025, TimesFM-2.5 Sept-2025).
Fidelity: FM join 258085/258085 rows (all three grids align fully); book rows
Y0..Y4 = 43800/43800/43800/43800/43785 (= template counts); weight join 54750
rows (5x10950, shift-0 grids match).

## Table A — BOOK directional: pooled Spearman(feat, y_h) + week CI (n≈43.8k)

| year | h=1 ch/toto/tfm q50 | h=1 spreads ch/toto/tfm | h=2 medians | h=2 spreads |
|---|---|---|---|---|
| Y0 dev | +0.015/-0.014/+0.006, all ns | +0.012/+0.007/+0.012, all ns | +0.011/-0.033*/-0.002 | +0.017/+0.010/+0.019, ns |
| Y1 dev | -0.012/-0.010/+0.011, ns | +0.019*/+0.022*/+0.024* | -0.027/-0.015/-0.005, ns | +0.018/+0.024/+0.028, ns(Y2-like cells sig) |
| Y2 dev | +0.000/-0.016*/-0.005 | +0.038*/+0.030*/+0.036* | +0.002/-0.028*/-0.024* | +0.049*/+0.039*/+0.044* |
| Y3 dev | -0.008/-0.003/-0.005, ns | +0.031*/+0.029*/+0.045* | -0.012/-0.002/-0.003, ns | +0.035*/+0.035*/+0.058* |
| Y4 CLEAN | +0.010/-0.004/+0.020, ALL ns | +0.007/-0.017/-0.007, ALL ns | +0.007/-0.004/+0.007, ALL ns | -0.001/-0.022/-0.015, ALL ns |

h=6 Y4 pooled: -0.006/-0.013/-0.026 (medians) and -0.010/-0.047/-0.032
(spreads), ALL ns. h=18 Y4 pooled: +0.059/-0.020/+0.006 and
-0.010/-0.047/-0.040, ALL ns (max|IC| over 24 Y4 pooled cells = 0.059).
Per-coin Y4: h=1 medians 14/15 ns (only XRP-tfm_q50 +0.050*); h=2 medians
0/15 sig (|IC|<=0.031); h=18 medians 0/15 sig. Spreads h=1 per-coin Y4: 13/15
ns (ETH-toto_spr -0.034*, XRP-tfm_spr -0.039* — negative, opposite sign to the
dev pooled positives: noise). Dev spread positives at h=1/2 do NOT transfer
to the clean year (Y4 ≈ 0 or negative).

## Table B — vol forecasting: pooled Spearman(feat, |y_h|), Y4 (all years same pattern)

| h | ch_q50 | ch_spr | toto_q50 | toto_spr | tfm_q50 | tfm_spr |
|---|---|---|---|---|---|---|
| h=1 | +0.061* | +0.225* | -0.009 ns | +0.201* | +0.031 ns | +0.205* |
| h=2 | +0.066* | +0.214* | -0.022 ns | +0.181* | +0.026 ns | +0.200* |
| h=6 | +0.068 ns | +0.203* | -0.004 ns | +0.158* | +0.037 ns | +0.204* |
| h=18 | +0.060 ns | +0.174* | +0.003 ns | +0.168* | +0.034 ns | +0.171* |

Spreads carry VOLATILITY info in EVERY year incl Y4 (+0.16..+0.28, CIs exclude
0 at all horizons — same role as Kronos vol1/pdrop2 in oc_kronosfeat Table 2);
medians carry no vol info (toto/tfm q50 |IC|<=0.03 ns; ch_q50 +0.06 weakly sig
only at h=1/2).

## Table C — novelty vs G2: Spearman(feat, FINAL weight) pooled, shift-0

| year | ch_q50 | toto_q50 | tfm_q50 | spreads vs w (ch/toto/tfm, Y4) |
|---|---|---|---|---|
| Y0..Y3 | +0.29*/+0.26*/+0.36*/+0.24* (stable +) | -0.09*/-0.09*/-0.09*/-0.04ns | +0.03/+0.04/-0.00/-0.04, ns | dev: ch_spr up to +0.39* (Y2); toto/tfm spr +0.20..+0.22* (Y2) |
| Y4 CLEAN | +0.277* [+0.167,+0.375] | -0.046 ns | -0.041 ns | -0.054/+0.010/-0.044, all ns |

|w| channel Y4 pooled: ch_spr +0.176*, toto_spr +0.120*, tfm_spr +0.126*
(all sig); ch_q50 +0.122*; toto/tfm q50 ns. So Chronos' median points the same
way as the deployed book (stable +0.24..+0.36 in all 5 years) but has no
forward-return IC itself — overlapping positioning, no incremental direction.
Spread magnitude tracks book size; toto/tfm medians are orthogonal to G2.

## Leakage / timing checks

Feature at T uses closes of bars closing <= T (inherited from the three frozen
parquet builds, truncation-tested in tests/test_oc_chronos.py,
test_oc_toto.py, test_oc_timesfm.py). Book labels use opens t+h > t on the
same shift grid; sigma uses only trailing returns ending at t (first 119 rows
NaN by min120 — asserted in test). No fit in this study; Y4 reported, nothing
chosen (diagnostic only). No fills claimed; ICs are rank diagnostics. Resume
checkpoints (tmp/parts/) added after a 10-min timeout killed the first run —
same seeds/math, no outcome seen before the change.

## **Key question: does any FM median carry book direction information on the clean year?**

**NO — on the CLEAN year (Y4) no FM median carries book direction: pooled
h=1/h=2 ICs are +0.010/-0.004/+0.020 and +0.007/-0.004/+0.007 (all CIs cross
0), h=6/h=18 likewise all ns, per-coin 29/30 cells ns at h=1/2 (the single
XRP-tfm_q50 +0.050 is noise among 30). Spreads' dev directional positives
(+0.02..+0.06 sig at h=1/2) vanish on Y4. What DOES transfer is volatility:
all three spreads predict |y_h| at +0.16..+0.23 on Y4 (as in every dev year).
Chronos' median correlates +0.28 with deployed FINAL weights but has no
forward IC — same-side positioning, no new direction.**

Kết luận (3 dòng): Không có median nào của Chronos/Toto/TimesFM mang thông tin
hướng book trên năm sạch (mọi IC có hướng ≈ 0 ở mọi horizon ngắn, gộp và từng coin).
Chỉ spread (q90-q10) mang thông tin biến động (|y|) ổn định qua cả 5 năm, không phải hướng.
Đây là nghiên cứu mô tả, không thay đổi G2; median FM không dùng được cho book hướng.
