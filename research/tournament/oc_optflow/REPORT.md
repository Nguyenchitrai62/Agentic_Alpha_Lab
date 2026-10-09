# oc_optflow REPORT (2026-10-07) — informed option flow vs the majors (descriptive)

## Setup
Informed universe: Deribit strike-level hours, DTE 1..9d, OTM |m| in [0.03,0.15]
(puts K<index, calls K>index; index=vwap_index/row; notional=amount×index).
NPB/NCB = taker-buy-minus-sell USD of OTM puts/calls; BLK = block USD puts−calls.
F1 = 24h Σ(NCB−NPB)/D, F2 = 24h ΣBLK/D, F3 = 4h Σ(NCB−NPB)/D,
D = trailing-30d mean(|NCB|+|NPB|), shared normaliser (disclosed).
F(T) uses only full hours ending at T. BTC coin←BTC flow, ETH←ETH,
SOL/BNB/XRP←BTC (market-wide; disclosed). Dev years only: opens in
[2021-09-24,2025-09-24), Y0..Y3 = [A_k,A_{k+1}). No trading rule scored.

## (a) BOOK IC (Spearman F vs vol-normalised open-to-open z1=1-bar, z6=6-bar; pooled n≈10950/yr)
| feat | hor | Y0 | Y1 | Y2 | Y3 | 4y-pooled | sign 4/4? |
|---|---|---|---|---|---|---|---|
| F1 | z1 | -0.001 | -0.004 | -0.007 | -0.007 | -0.004 | yes(-) but \|IC\|<<0.02 |
| F1 | z6 | +0.035 | -0.014 | -0.000 | -0.018 | +0.006 | no (1+/3-) |
| F2 | z1 | -0.010 | +0.004 | -0.002 | -0.010 | -0.007 | no (1+/3-) |
| F2 | z6 | -0.018 | +0.058 | -0.003 | +0.016 | +0.009 | no (2/2) |
| F3 | z1 | +0.004 | -0.029 | -0.017 | -0.007 | -0.009 | no (1+/3-) |
| F3 | z6 | +0.016 | -0.015 | -0.014 | -0.009 | -0.003 | no (1+/3-) |
Block-42 bootstrap 95% CIs (n_boot=1000) are ±0.2..0.6 (F highly persistent;
effective dof tiny) — every CI covers 0 comfortably. Per-coin max |IC| = 0.075
(ETH F1/z6 2022); per-coin signs flip year to year (full table ic_book.csv).
Vs ~4-8 bps round-trip cost: pooled |IC| ≤ 0.009 overall ⇒ no exploitable edge visible.

## (b) DIPS join (replica base 7.718304 / phase0 [2.388,0.183,3.810,2.579,0.712] /
n=22312 / checksum 902c5bbfe8fed3c0 — reproduced EXACTLY; fills Y0..Y3 n=17540)
| feat vs y10 | Y0 | Y1 | Y2 | Y3 | pooled | sign 4/4? |
|---|---|---|---|---|---|---|
| F1 | +0.017 | +0.038 | +0.051 | -0.016 | +0.017 | no (3+/1-) |
| F3 | +0.007 | -0.093 | -0.065 | -0.048 | -0.048 | no (1+/3-) |
Tercile mean-y10 / loss-rate P(y10<0): no monotonic pattern (e.g. F3-2022 T1 +0.0052
vs T3 −0.0018, but F3-2024 flat +0.0047/+0.0052/+0.0053; loss rates bounce 0.22-0.36;
full table dips_terciles.csv). DEVIATION (pre-registered in PLAN): exit-type stop flag
is not stored by the replica, so loss rate P(y10<0) is reported instead of stop rate.

## Candidates: NONE (0/3 features). F1/z1 is 4/4 same-sign but pooled |IC|=0.004 < 0.02;
every other (a) cell and both (b) series fail sign consistency. No follow-up rule proposed.

## Leakage / timing check
Hourly buckets use only within-hour trades; F(T) reads hours [T−720h,T−1h] only
(causality unit-tested: nuking hours ≥T leaves F(T) bit-identical; pre-warmup T→NaN).
Labels (r1/r6/y10) use strictly post-T prices. No fits/thresholds (year-terciles are
descriptive summaries, disclosed). All rows with open ≥2025-09-24 excluded before every
statistic. G2 overlay vacuous here (no trading rule); the audited gate was dip base 7.718.

## Verdict
Kết luận: LOẠI — informed option flow (F1/F2/F3) không dự báo được các majors, không ứng viên nào đạt quy tắc 4/4 năm với |IC| gộp ≥ 0.02.
Lý do: |IC| gộp ≤ 0.009 ở BOOK và đổi dấu ở 5/6 ô BOOK cùng cả hai chuỗi DIPS, mọi khoảng tin cậy đều bao số 0.
Tiếp theo: đóng hướng này lại, không đề xuất rule giao dịch nào thêm.
