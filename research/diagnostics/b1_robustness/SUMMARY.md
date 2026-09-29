# B1 robustness (5m-close dip stops + 8-sigma native backstop) - summary
B1 base reproduces: dev4 6.130, 5y 5.795, last 4.464, gate DD 19.70, 0 losing years; dev win 0.518 (1053 trades), hidden 0.541 (303). O1 base reproduces: 5.777/5.436/4.082/19.65, win 0.516 (1052).
O1 vs B1 per row (dev4 / 5y / last / DD / lose / dev-win):
base 5.777/6.130, 5.436/5.795, 4.082/4.464, 19.65/19.70, 0/0, 0.516/0.518 | cost 4.995/5.265, 4.673/4.891, 3.396/3.407, 20.75/22.84, 0/0, 0.518/0.523.
lat15 5.526/5.914, 5.215/5.538, 3.980/4.047, 19.84/21.87, 0/0, 0.517/0.517 | lat30 5.316/5.759, 4.951/5.334, 3.507/3.656, 21.08/21.57, 0/0, 0.500/0.502.
lat60 4.843/5.112, 4.585/4.885, 3.556/3.983, 23.18/24.46, 0/0, 0.499/0.496 | band_lo 5.699/5.990, 5.341/5.593, 3.921/4.022, 20.43/20.55, 0/0, 0.515/0.507.
band_hi 5.363/5.595, 5.036/5.282, 3.736/4.041, 21.03/22.41, 0/0, 0.530/0.525 | cool3 5.577/5.847, 5.275/5.501, 4.075/4.129, 19.91/22.41, 0/0, 0.513/0.521.
cool12 5.518/5.790, 5.181/5.461, 3.846/4.156, 22.73/22.89, 0/0, 0.514/0.509 | sleeve0.16 5.696/6.049, 5.375/5.707, 4.099/4.349, 19.89/19.86, 0/0, 0.512/0.514.
sleeve0.20 5.662/6.149, 5.327/5.813, 3.996/4.479, 19.49/19.70, 0/0, 0.512/0.517 | offset0.15 5.663/5.985, 5.440/5.788, 4.554/5.006, 19.74/21.42, 0/0, 0.500/0.499.
offset0.40 5.614/5.988, 5.255/5.596, 3.830/4.044, 19.14/21.03, 0/0, 0.526/0.523 | B1-only outage_backstop_only (touch m_sleeve_sl=8.0) 5.664/5.365/4.175/DD 18.69/0 lose/win 0.525.
B1-only close_1m (close1+back8) 5.860/5.583/4.485/DD 21.79/0 lose/win 0.515. B1_latency_close_plus5 SKIPPED (close-stop fill delay needs an engine edit; none made).
Every yearly net is positive in all 28 numeric rows (no losing year anywhere); dev win rate stays 0.496-0.530 (hidden 0.52-0.56).
Bootstrap (base daily, first 4y, 30d blocks, 2000 draws, seed 0): O1 monthly p5/p50/p95 = 1.04/5.35/11.56, P(>=5)=0.548, P(loss y)=0.014, DD p50/p95 = 12.33/20.95, P(DD>20)=0.068.
B1 monthly p5/p50/p95 = 1.45/5.75/11.86, P(>=5)=0.603, P(loss y)=0.010, DD p50/p95 = 12.43/21.35, P(DD>20)=0.081: return distribution shifts up, DD tail slightly worse.
Small account (2000 USDT, Bybit lots, most recent year): O1 book 570/574 (0.993), rungs 1056/1082 (0.976); B1 book 569/573 (0.993), rungs 1056/1082 (0.976): identical.
Verdict: NO, B1 is not at least as robust as O1. B1 lifts the mean everywhere (+0.27-0.39pp dev4) but its DD is equal or worse in 12/13 paired rows; O1 holds DD<=20 in 7 rows (base/lat15/cool3/both sleeves/both offsets) vs B1 in only 3 (base/both sleeves). Cost stress (22.84 vs 20.75), lat15 (21.87 vs 19.84), cool3 (22.41 vs 19.91) and both offsets flip from pass to breach. The bot-outage backstop alone is safe (DD 18.69, dev4 5.664), but it does not rescue B1's stress drawdowns.
Method: O1 books 0.5(A+B)/2+0.5(Aq+Bq)/2, grid_policy(0.03,0.40), win_start=5, KW budget 0.18; B1 adds sleeve_stop_mode="close5", sleeve_backstop=8.0; bootstrap/small-account per O1 template.
