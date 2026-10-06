# Scorecard prospective 2026-10-06 (~10:00 UTC, chỉ mode=prospective)

Chốt: plan v376 tới 10:00, bot tới 06:00, carry tới 06:07, scorecard 05:53Z.
Ngưỡng tối thiểu (DEPLOYMENT_PLAN_VI s2.3/s4): go-live >= 8 tuần (56 ngày),
divergence PASS/FAIL >= 14 ngày; band 12-tháng cần ~1 năm. Tất cả dưới đây đều QUÁ SỚM.
Band kỳ vọng (PLAN_VI): R2B1D17BF rolling-49 min 2,73/p10 3,25/med 4,89/p90 8,88/max 11,71 %/th;
DD med 13,5/p90 18,3/max 18,7; bootstrap med ~5,1 (p5 1,5/p95 10,3) %/th, DD med 14,5/p95 22,6.
G2-deploy 5,41 %/th DD 16,9; G2K20 5,87/17,79; MANUAL M4/M5 ~3,5 (người thật).

## 1. Advisor shadow (trade_plan curves, bootstrap cùng số ngày)

| Nguồn | Ngày | Live | Band p05/p50/p95 | Pctl | Div vs replay | Flag |
|---|---|---|---|---|---|---|
| v295 CS | 6,17 | +1,01% | -3,75/+0,59/+8,13 | 57,9 | n/a (không phải v376) | quá sớm, trong band |
| v301 G2 | 6,17 | +0,99% | -3,77/+0,64/+8,13 | 57,4 | n/a | quá sớm, trong band |
| v321 R2 | 3,17 | +0,45% | -2,20/+0,25/+5,18 | 56,6 | n/a | quá sớm, trong band |
| v315 M1 | 3,00 | -0,14% | -2,09/+0,01/+3,79 | 36,4 | n/a | quá sớm, trong band |
| v342 M3 | 2,83 | -0,10% | -1,84/+0,21/+4,34 | 31,5 | n/a | quá sớm, trong band |
| v340/v362/v367 M2/M4/M5 | 2,50 | ~-0,10% | ~-1,4/+0,13/+3,1 | ~30 | n/a | quá sớm, trong band |
| v376 R2-4P (plan) | 2,04 | -0,17% | -1,61/+0,16/+2,97 | 29,3 | gốc so sánh | quá sớm, trong band |
| v266/v269 C5/M1-old | 5,17 | +0,60% | -2,9/+0,5/+7,2 | ~52 | n/a | DỪNG 10-03, trong band |
| v285 D2 | 3,50 | +0,73% | -2,74/+0,31/+6,19 | 60,5 | n/a | DỪNG 10-03, trong band |
| v233/v236/v240 | 2,33 | +0,25/+0,36/+0,37% | ~-1,7/+0,16/+3,3 | 54-60 | n/a | DỪNG 09-30, trong band |

Shadow log (prospective 1822 dòng): chỉ v240_O1 (42) + v285_CB (1266) tới 10-06 03:59;
còn lại dừng 09-30. Dip-sleeve forward tới 09-30: 0 event cả 4 legs. forward_score.json 09-26 đã cũ.
DD/win của trade_plan không có trong curve (chỉ live% + band) -> không kết luận.

## 2. Paper runners (giá Bybit thật, fills entry/book; 0 exit -> win n/a)

| Bot (config, start) | Ngày | Fill dip/book | Net | DD | Div vs plan v376 | Band cùng ngày | Flag |
|---|---|---|---|---|---|---|---|
| paper R2-4P `--mode paper --equity 5000` 10-05 04:00 | 1,08 | 0/6 | -0,03% | 0,09% | +0,33pp (~+9,3pp/th, nhiễu) | -1,21/+0,07/+1,87: trong | quá sớm (<14d) |
| paper_d17bf v411 `--corr-size --dip-mult 1.7 --bear-book` 10-05 13:00 | 0,71 | 0/4 | -0,01% | 0,02% | +0,24pp (~+10,1pp/th, nhiễu) | trong | quá sớm, closest-plan |
| paper_d17bfg2 v421 `+--dip-gross-cap 2.0` 10-05 17:51 | 0,54 | 0/4 | -0,01% | 0,02% | +0,14pp (~+7,9pp/th, nhiễu) | trong | quá sớm, closest-plan |
| paper_g2k20 v422 `--dip-mult 2.0 --dip-gross-cap 2.0` 10-05 17:38 | 0,54 | 0/4 | -0,01% | 0,02% | +0,14pp (~+7,9pp/th, nhiễu) | trong | quá sớm, closest-plan |
| paper_d13bf 10-06 02:00 | 0,17 | 0/3 | -0,01% | 0,01% | +0,13pp (~+24pp/th, nhiễu) | trong | quá sớm |

Chỉ `paper` cùng config v376; còn lại so với "closest v376 R2-4P" (paper_divergence).
Quy đổi pp/tháng trên <1 ngày chỉ là nhiễu mẫu, verdict đúng là `too early`. 0 cycle_error>1h mới.

## 3. Carry ledger (paper_carry, start 10-06 06:05Z, f=0,5)

| Vị thế | Ngày | Net MtM | DD/win | Kỳ vọng | Flag |
|---|---|---|---|---|---|
| BTC BTCUSDT-25DEC26 entered (basis +5,42%/yr>=4%); ETH skip (3,7%<4%) | ~0,04 | alloc -0,15% (-3,68 USDT) | n/a (0 closed) | oc_cashcarry +0,21%/th (f=0,25); worst alloc -2,65% | quá sớm, cần giữ tới Dec ~80d |

## Kết luận

Không nguồn nào ngoài band; không nguồn nào đủ ngày (cần 14d cho divergence, 56d cho go-live).
Tiếp tục log, không kết luận go-live/stop hôm nay.
