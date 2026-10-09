# oc_kronosfeat — REPORT (diagnostic only, nothing selected)

Inputs: `oc_kronoshidden/kronos_features_4shift.parquet` (8 feats, 4 shifts, feature at
bar open T uses only 400 bars closing <= T) + `bars_4h_4shift.parquet`. Dip ledger =
exact placebo-D0 replica (RUNGS 2.5/3/3.5/4/5, live 16..238 strict trade-through, TP
1sg/close5-stop 4sg/8sg-backstop, timeout next-bar open, maker 0.0002/taker 0.00055,
v293 settle funding, B1 w=1/(1+n_fill)). Book yardstick y=(open[t+h]/open[t]-1)/sigma,
sigma=trailing-360 std of 1-bar simple returns per (sym,shift), min 120, causal.
CIs = week-block bootstrap B=500 (Monday weeks). Y0..Y3 = INSIDE Kronos pretraining
= UPPER BOUND; Y4 = 2025-09-24..2026-09-24 = CLEAN post-release year.
Fidelity gate PASSED: 4-phase-mean 5y sum 7.7183 vs ref 7.718304 (tol 0.01);
phase-0 raw sums [2.3881, 0.1829, 3.8098, 2.5793, 0.7115] match ref exactly;
feature coverage 1.0000 (22312/22312 fills); book rows Y0..Y4 =
43800/43800/43800/43800/43785; weight join 54750 rows (5x10950, shift-0 grids match).

## Table 1 — DIPS: pooled Spearman(feature, raw y10 TP1.0 net) + week CI, n fills

| year | er1 | er6 | vol1 | vol6 | rng1 | low1 | pdrop2 | pdrop3 |
|---|---|---|---|---|---|---|---|---|
| Y0 n=4171 | +0.0847 [+0.028,+0.127]* | +0.0904 [+0.001,+0.214]* | +0.0368 ns | +0.0216 ns | +0.0132 ns | +0.0609 ns | -0.0319 ns | -0.0117 ns |
| Y1 n=4059 | +0.0343 ns | +0.0540 ns | +0.0952 ns | +0.0674 ns | +0.1282 ns | +0.0063 ns | +0.0206 ns | +0.0368 ns |
| Y2 n=5352 | -0.0310 ns | -0.0518 ns | +0.0288 ns | +0.0319 ns | +0.0596 ns | -0.0564 ns | +0.0574 ns | +0.0302 ns |
| Y3 n=3958 | +0.0848 [+0.014,+0.147]* | +0.0721 ns | +0.0636 ns | +0.0439 ns | +0.0837 [+0.006,+0.163]* | +0.0249 ns | +0.0132 ns | +0.0430 ns |
| Y4 CLEAN n=4772 | +0.1083 ns | +0.1310 ns | +0.1561 [+0.060,+0.221]* | +0.1385 [+0.050,+0.223]* | +0.1533 [+0.077,+0.237]* | +0.0429 ns | +0.0380 ns | +0.0229 ns |

Y4 quintiles (that-year pooled edges, unweighted mean y10 / stop rate): vol1
Q0 +0.00100/0.004 … Q3 +0.00236/0.029, Q4 -0.00089/0.081; rng1 Q3 +0.00259/0.034,
Q4 -0.00128/0.074; vol6 Q0 +0.00123/0.002 … Q4 +0.00127/0.056. High-vol tail has
the highest stop rate. low1-by-coin is unstable (Y4 all 5 coins ns; Y3 BNB
+0.161 sig while BTC -0.079 ns; Y1 ETH -0.159 ns). Mean y10 per year:
+0.00128 / +0.00085 / +0.00145 / +0.00504 / +0.00071; stop rates
0.0446 / 0.0586 / 0.0583 / 0.0119 / 0.0289.

## Table 2 — BOOK directional: pooled Spearman(feat, y_h) + week CI (n≈43.8k)

| year | h=1 er1/er6/low1/pdrop2/vol1 | h=2 | h=6 | h=18 |
|---|---|---|---|---|
| Y0 | +0.019*/+0.016/+0.016*/-0.008/+0.003 | +0.012/+0.015/+0.008/-0.007/+0.009 | +0.014/+0.012/-0.002/+0.012/+0.015 | +0.004/-0.017/+0.015/-0.009/+0.003 |
| Y1 | +0.030*/+0.037*/+0.014/-0.000/+0.022* | +0.029*/+0.045*/+0.017/-0.005/+0.020 | +0.038*/+0.066*/+0.028/-0.014/+0.029 | +0.000/+0.039/+0.004/-0.001/+0.039 |
| Y2 | +0.022*/+0.009/+0.001/+0.010/+0.027* | +0.008/+0.001/-0.010/+0.017/+0.035* | -0.012/-0.018/-0.029/+0.026/+0.042 | -0.053/-0.053/-0.069*/+0.053/+0.065 |
| Y3 | +0.017*/+0.013/-0.004/+0.012/+0.032* | +0.008/+0.008/-0.015/+0.016/+0.037* | +0.013/+0.006/-0.013/+0.018/+0.038 | -0.009/-0.007/-0.052/+0.057/+0.066 |
| Y4 CLEAN | +0.010/+0.013/+0.011/-0.005/+0.009, ALL ns | +0.007/+0.010/+0.015/-0.004/+0.011, ALL ns | +0.002/-0.001/+0.027/-0.018/-0.000, ALL ns | -0.002/-0.012/+0.040/-0.012/+0.029, ALL ns |

Per-coin Y4 h=1: only BTC-low1 +0.034 [+0.009,+0.059] excludes 0; all other 24
cells ns (|IC|<=0.028). Per-coin Y4 h=2 er1/er6: all 10 cells ns.
Volatility channel (|y_h|) pooled — strong in EVERY year incl Y4:
Y4 h=1 vol1 +0.182*, pdrop2 +0.119*, low1 -0.072* (higher low1 -> smaller |move|);
same pattern h=2/6/18 (vol1 +0.12..+0.16*, pdrop2 +0.07..+0.10*, low1 negative*).
Dev directional |IC| is tiny (max pooled 0.066) and does not transfer to Y4.

## Table 3 — novelty vs G2 (correlational only)

FINAL-weight corr (shift-0, pooled): Y4 er1 -0.130* [-0.212,-0.047], er6
-0.205* [-0.337,-0.060], low1 -0.108* [-0.197,-0.022], vol/rng/pdrop ns; |w|
channel Y4: er6 -0.167*, vol1 +0.109*, vol6 +0.128*, rng1 +0.124*, low1 -0.117*,
pdrop2 +0.099*. B1 flush_bar corr (mean n_fill, pooled): Y4 er1 +0.205*
[+0.100,+0.282], er6 +0.257* [+0.127,+0.339], low1 +0.213* [+0.134,+0.269],
pdrop2 -0.172* [-0.235,-0.105], pdrop3 -0.145* (shift-0-only: er6 +0.277*,
low1 +0.217*, pdrop2/3 negative*). So Kronos er/low1 information overlaps the
dip-flush mechanism, while G2 book weights lean the other way.

## Leakage / timing checks

Feature at T uses bars closing <= T (kronoshidden build, 400-bar window on the
same shift grid). Dip labels use 1m minutes f+1..240 strictly after T (fill
minute f excluded; live window starts minute 16, never minute 0). Book labels
use opens t+h > t on the same shift grid; sigma uses only trailing returns
ending at t (first 119 rows NaN by min120 — asserted in test). No fit in this
study: quintile edges are descriptive per-year summaries, never traded. Y4 was
reported, nothing was chosen (diagnostic only). No fills claimed for book ICs;
dip costs are baked into the replica ledger only.

## **Key question: on the clean year, which features carry dip and book information, and is any book IC positive at short horizons?**

**On the CLEAN year (Y4): dip information is carried by vol1/vol6/rng1
(Spearman +0.14..+0.16, CIs exclude 0); er1/er6/low1/pdrop2/pdrop3 carry no dip
information (CIs cross 0). NO book directional IC is positive at short horizons
— pooled h=1/h=2 ICs are +0.007..+0.015 with CIs crossing 0 for all five
features, and per-coin only BTC-low1-h1 is significant (+0.034). Volatility
information IS present (vol1/pdrop2 vs |y| up to +0.18, significant at all
horizons). Kronos information is not new vs the dip-flush channel (flush corr
up to +0.26) but is anti-correlated with G2 book weights.**

Kết luận (3 dòng): KHÔNG chọn bất kỳ feature Kronos nào cho book hướng vì IC
có hướng trên năm sạch đều ~0 ở mọi horizon ngắn. Chỉ vol1/vol6/rng1 mang thông
tin dip trên năm sạch, nhưng dạng quintile không đơn điệu và stop-rate cao ở
đuôi nên cần bằng chứng prospective trước khi dùng. Đây là nghiên cứu mô tả,
không thay đổi G2, cần log prospective để xác nhận.
