# oc_quietmonth REPORT — what follows a quiet start? (2026-10-06)

DIAGNOSTIC only: no trading rule, no variant selection. G2 = R2B1D17BFG2.
Sources (read-only, no engine reruns, one process): hourly_ext majors
(market), oc_edgedecay/results.json (G2 monthly total + book/dip parts,
exit-time attribution; totals match oc_kpi_g2 to 0.00). All five years are
research data; findings need prospective validation.
Repro: research/diagnostics/oc_quietmonth/{run_quietmonth.py,results.json};
test tests/test_oc_quietmonth.py.

## Setup
Flush = verbatim oc_edgedecay/regime_now: 4h log return <= -2.5 * trailing
180-bar std strictly before the bar, per major; TOTAL = 5-coin sum. Prior-30d
for month M = TOTAL on bars in [month_start-30d, month_start): fully known
at the month start (causal; asserted per month). Buckets use the FROZEN
history thresholds from the assignment/regime_now (p10/p25/p50/p75/p90 =
4/7/15/20/29): low = prior < 7, normal = 7..20, high = prior > 20.
Empirical quantiles of the 60 prior-30d readings: 4.9/8.0/15.0/20.0/30.1
(near-identical; frozen 7/20 used, fixed before seeing outcomes).
Partition: low 12, normal 34, high 14 months (= 60).

## Next-month G2 return (%) by prior-30d bucket
| bucket | n | mean | median | p10 | p90 | >=5% | losing |
|---|---|---|---|---|---|---|---|
| low (<7) | 12 | 4.87 | 0.67 | -4.46 | 22.44 | 25.0% (3/12) | 33.3% (4/12) |
| normal (7..20) | 34 | 7.55 | 4.82 | -2.36 | 18.58 | 47.1% (16/34) | 29.4% (10/34) |
| high (>20) | 14 | 3.64 | 4.17 | -4.57 | 9.11 | 42.9% (6/14) | 28.6% (4/14) |
| all 60 | 60 | 6.10 | 3.65 | -3.01 | 17.86 | 41.7% | 30.0% |

## Same, book part (pp) / dip part (pp)
| bucket | book mean | book >=5% | book losing | dip mean | dip median | dip >=5% | dip losing |
|---|---|---|---|---|---|---|---|
| low (n=12) | 1.21 | 16.7% (2/12) | 41.7% (5/12) | 4.49 | 3.62 | 50.0% (6/12) | 33.3% (4/12) |
| normal (n=34) | 2.31 | 23.5% (8/34) | 50.0% (17/34) | 5.69 | 3.67 | 38.2% (13/34) | 5.9% (2/34) |
| high (n=14) | 1.88 | 21.4% (3/14) | 35.7% (5/14) | 2.89 | 2.76 | 28.6% (4/14) | 14.3% (2/14) |

Low-bucket months: 2021-11, 2022-04, 2022-08, 2022-11, 2023-06, 2023-10,
2024-01, 2024-03 (+22.97), 2024-06, 2024-10, 2026-04, 2026-08 (+23.52).
The low mean (+4.87) rests on two monsters (+23% each); without them it is
~+1.2. Typical (median) quiet-start month is soft (+0.67) vs +4.82 normal,
but the p10-p90 bands overlap almost fully and the low-vs-normal mean gap
(-2.7pp) is under one standard error of the low mean (std ~10.5, SE ~3.0,
n=12). Dip medians are near-identical (low 3.62 vs normal 3.67); dip loses
more often after quiet starts (4/12 vs 2/34) but again n=12. High-start
months average less (+3.64) with a capped upside (p90 9.11) — same H8 story
as edgedecay (many flushes, weaker per-trade), also on small n=14.

## Ket luan (tieng Viet, binh dan)
Thang toi bat dau yen tinh: 6 flush/30 ngay roi vao nhom thap (< 7). Lich su
12 thang yen tinh: trung binh +4.9%/thang nhung thang dien hinh (trung vi)
chi +0.7%, 3/12 thang dat >= 5%, 4/12 thang lo, bien do rat rong (-4.5 ..
+22.4). Hai thang lai lon nhat (+23%) lai roi vao nhom yen tinh, va chenh
lech so voi thang binh thuong nam trong sai so cua mau nho (n=12) — nen
khoi dau yen tinh KHONG phai tin hieu xau dang tin. Yen tinh = it co hoi
dip hon (dung nhu nua H7 trong edgedecay: it trade, edge con nguyen), chu
khong phai edge hong. Khong doi gi: giu ky vong theo trung binh chung va
nguong canh bao edgedecay (6 thang < 1.61%/thang, TP rate dip < 0.434).

VERDICT: A quiet start (6 flushes/30d = low) is uninformative, not bearish:
n=12, overlapping bands, mean gap within one SE, and the two biggest months
came from quiet starts. Expect fewer dip opportunities, not a broken edge.
