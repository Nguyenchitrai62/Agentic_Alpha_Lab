# M2 MANUAL robustness - summary
M2 base reproduces: dev4 3.011, 5y 3.160, last 3.759, gate DD 20.57, 0 losing years; dev win 0.524 (995 trades), hidden 0.550 (278). G2-manual base reproduces: 2.502/2.772/3.859/19.61, 1 losing year (2021 -3.63%); dev win 0.503 (1032).
M2 vs G2-manual per row (dev4 / 5y / last / DD / lose / dev-win):
base 3.011/2.502, 3.160/2.772, 3.759/3.859, 20.57/19.61, 0/1, 0.524/0.503 | cost 2.892/2.425, 3.029/2.682, 3.581/3.714, 20.54/19.63, 0/1, 0.523/0.506.
lat15 2.776/2.472, 2.972/2.734, 3.759/3.788, 20.58/19.24, 0/1, 0.524/0.501 | lat30 2.650/2.130, 2.833/2.404, 3.567/3.506, 21.10/20.70, 0/1, 0.510/0.491.
lat60 2.139/1.646, 2.387/1.948, 3.385/3.164, 23.02/20.63, 0/1, 0.503/0.485 | lat120 1.500/1.066, 1.703/1.395, 2.520/2.724, 26.08/22.25, 0/1, 0.488/0.449.
missed_k6 2.634/2.725, 2.706/2.921, 2.996/3.712, 22.32/17.38, 0/1, 0.516/0.518 | band_lo 3.019/2.668, 3.267/2.878, 4.263/3.723, 21.50/18.62, 0/0, 0.503/0.503.
band_hi 2.720/2.455, 2.889/2.756, 3.568/3.967, 21.68/20.35, 0/1, 0.524/0.514 | cool3 2.696/2.911, 2.927/3.074, 3.852/3.729, 21.66/19.43, 0/1, 0.509/0.498.
cool12 2.647/2.705, 3.069/2.899, 4.775/3.679, 20.61/20.01, 0/1, 0.522/0.505.
No row reaches the MANUAL win floor (M2 0.488-0.524, G2 0.449-0.518, all < 0.55); M2 has 0 losing years in all 11 rows, G2 loses 2021 in 9/11 (passes only band_lo, cool rows except cool_3/12 still lose); M2 DD<=20 in 0/11 (base already 20.57), G2 in 4/11.
Bootstrap (base daily, first 4y, 30d blocks, 2000 draws, seed 0): M2 monthly p5/p50/p95 = -0.34/2.93/7.05, P(>=5)=0.186, P(loss y)=0.075, DD p50/p95 = 13.11/22.13, P(DD>20)=0.090.
G2 monthly p5/p50/p95 = -0.71/2.30/6.58, P(>=5)=0.136, P(loss y)=0.121, DD p50/p95 = 13.66/23.27, P(DD>20)=0.114: M2 shifts return up and thins the DD tail.
Small account (Bybit lots, most recent year book placeable): 500 USDT M2 497/584 (0.851) vs G2 446/564 (0.791); 1000 USDT 554/584 (0.949) vs 507/564 (0.899); 2000 USDT 582/584 (0.997) vs 558/564 (0.989): M2 slightly more placeable, both fine at 2000.
Verdict: a human may be ~15 min late (M2 lat15 2.776, keeps the 0.27pp edge over G2 base 2.502) and up to ~30 min before the edge is lost (lat30 2.650 still above G2 base, lat60 2.139 below it); missing one 4h decision a day flips the edge to G2 (2.634 vs 2.725, DD 22.32 vs 17.38); latency never fixes the base DD breach (20.57) or the <55% win rate.
Method: books (2A+2PT+D)/5 vs (2A+2B+D)/5 reindexed/ffill/0, engine_user trade mode sleeve OFF target 0.25 cap 2, M2 pullback {"open":0.75} n_valid 3 vs G2 plain open n_valid 2, grid (0.03,0.40) cool 6, SL4/TP8, win_start 5; missed = i%6==0 wait/hold; bootstrap/small-account per B1 template.
