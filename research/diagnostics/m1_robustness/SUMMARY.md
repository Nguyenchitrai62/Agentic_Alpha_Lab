# M1 robustness (4-sigma candle-close dip stops + 8-sigma native backstop) - summary
M1 base reproduces: dev4 6.026, 5y 5.749, last 4.645, gate DD 18.27, 0 losing years; dev win 0.523 (1042 trades), hidden 0.546 (304). O1 base reproduces: 5.777/5.436/4.082/19.65, win 0.516 (1052).
O1 vs M1 per row (dev4 / 5y / last / DD / lose / dev-win):
base 5.777/6.026, 5.436/5.749, 4.082/4.645, 19.65/18.27, 0/0, 0.516/0.523 | cost 4.995/5.260, 4.673/4.951, 3.396/3.725, 20.75/21.60, 0/0, 0.518/0.517.
lat15 5.526/5.906, 5.215/5.627, 3.980/4.516, 19.84/18.26, 0/0, 0.517/0.516 | lat30 5.316/5.725, 4.951/5.379, 3.507/4.008, 21.08/18.36, 0/0, 0.500/0.511.
lat60 4.843/5.056, 4.585/4.866, 3.556/4.110, 23.18/24.54, 0/0, 0.499/0.492 | band_lo 5.699/5.963, 5.341/5.615, 3.921/4.234, 20.43/18.56, 0/0, 0.515/0.513.
band_hi 5.363/5.533, 5.036/5.286, 3.736/4.304, 21.03/23.39, 0/0, 0.530/0.523 | cool3 5.577/5.865, 5.275/5.567, 4.075/4.382, 19.91/22.50, 0/0, 0.513/0.516.
cool12 5.518/5.837, 5.181/5.522, 3.846/4.271, 22.73/23.61, 0/0, 0.514/0.514 | sleeve0.16 5.696/5.925, 5.375/5.664, 4.099/4.630, 19.89/18.24, 0/0, 0.512/0.522.
sleeve0.20 5.662/6.106, 5.327/5.812, 3.996/4.645, 19.49/18.34, 0/0, 0.512/0.521 | offset0.15 5.663/5.915, 5.440/5.755, 4.554/5.121, 19.74/18.32, 0/0, 0.500/0.506.
offset0.40 5.614/6.124, 5.255/5.780, 3.830/4.412, 19.14/17.97, 0/0, 0.526/0.530 | M1-only outage_backstop_only (touch m_sleeve_sl=8.0) 5.664/5.365/4.175/DD 18.69/0 lose/win 0.525.
M1-only close_1m (close1+back8, m_sleeve_sl 4.0) 5.847/5.580/4.518/DD 18.52/0 lose/win 0.519. M1_latency_close_plus5 SKIPPED (close-stop fill delay needs an engine edit; none made).
Every yearly net is positive in all 28 numeric rows (no losing year anywhere); dev win rate stays 0.492-0.530 (hidden 0.52-0.57).
Bootstrap (base daily, first 4y, 30d blocks, 2000 draws, seed 0): O1 monthly p5/p50/p95 = 1.04/5.35/11.56, P(>=5)=0.548, P(loss y)=0.014, DD p50/p95 = 12.33/20.95, P(DD>20)=0.068.
M1 monthly p5/p50/p95 = 1.40/5.62/11.60, P(>=5)=0.589, P(loss y)=0.009, DD p50/p95 = 12.33/20.93, P(DD>20)=0.072: return distribution shifts up, DD tail about flat.
Small account (2000 USDT, Bybit lots, most recent year): O1 book 570/574 (0.993), rungs 1056/1082 (0.976); M1 book 570/574 (0.993), rungs 1057/1083 (0.976): identical.
Verdict: YES, M1 is at least as robust as O1. M1 lifts dev4 in all 13 paired rows (+0.17-0.51pp) and holds DD<=20 in 8 paired rows vs O1 in 7 (M1 rescues lat30 18.36 vs 21.08 and band_lo 18.56 vs 20.43, flips cool3 to breach 22.50 vs 19.91). M1 DD is better in 8/13 rows; both M1-only extras pass (outage 18.69, close_1m 18.52).
Method: O1 books 0.5(A+B)/2+0.5(Aq+Bq)/2, grid_policy(0.03,0.40), win_start=5, KW budget 0.18; M1 adds sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0; bootstrap/small-account per B1 template.
