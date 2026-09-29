# O1 B18 robustness (deployed pipeline) - summary
Base (B18, budget 0.18) reproduces: dev4 5.777, 5y 5.436, last year 4.082, gate DD 19.65, no losing year; dev win rate 0.516 (1052 trades), hidden 0.543 (304).
| row | dev4 | 5y | last | DD | lose | win |
| base 5.777 5.436 4.082 19.65 0 0.516 | cost 4.995 4.673 3.396 20.75 0 0.518 | lat15 5.526 5.215 3.980 19.84 0 0.517 |
| lat30 5.316 4.951 3.507 21.08 0 0.500 | lat60 4.843 4.585 3.556 23.18 0 0.499 | band_lo 5.699 5.341 3.921 20.43 0 0.515 |
| band_hi 5.363 5.036 3.736 21.03 0 0.530 | cool3 5.577 5.275 4.075 19.91 0 0.513 | cool12 5.518 5.181 3.846 22.73 0 0.514 |
| sleeve0.16 5.696 5.375 4.099 19.89 0 0.512 | sleeve0.20 5.662 5.327 3.996 19.49 0 0.512 |
| offset0.15 5.663 5.440 4.554 19.74 0 0.500 | offset0.40 5.614 5.255 3.830 19.14 0 0.526 |
Yearly nets stay positive in every row (no losing year anywhere); win rate stays 0.50-0.53 (above 50% after fees) in all rows.
Bootstrap (base daily, first 4y, 30d blocks, 2000 draws, seed 0): monthly p5/p50/p95 = 1.04/5.35/11.56; P(>=5%/mo)=0.548; P(loss year)=0.014; DD p50/p95 = 12.33/20.95; P(DD>20%)=0.068.
Small account (2000 USDT, Bybit lots, most recent year): book orders 570/574 placeable (0.993); dip-rung orders 1056/1082 (0.976).
Verdict: FRAGILE on drawdown, robust on sign. Base DD 19.65 sits 0.35pp under the 20% gate; cost stress (20.75), latency>=30 (21.08/23.18), either band (20.43/21.03) and cool_12 (22.73) all breach DD<=20. Only latency_15, cool_3, both sleeves and both offsets hold the gate. No knob produces a losing year. Latency is the sharpest cliff: minute-30 already breaks the gate and minute-60 also cuts dev4 to 4.84.
Method: O1 books 0.5(A+B)/2+0.5(Aq+Bq)/2, trade=dict(v216.GRID,policy=grid_policy(0.03,0.40)), win_start=5, KW budget 0.18; bootstrap exactly per template.
