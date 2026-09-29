# D2 robustness (0.8 C4 + 0.2 Coinbase-premium D) vs C4 - summary
D2 base reproduces: dev4 5.864, 5y 5.725, last 5.167, gate DD 18.39, 0 losing years; dev win 0.503 (1025 trades), hidden 0.558 (310). C4 base reproduces: 6.026/5.749/4.645/18.27, win 0.523 (1042).
C4 vs D2 per row (dev4 / 5y / last / DD / lose / dev-win):
base 6.026/5.864, 5.749/5.725, 4.645/5.167, 18.27/18.39, 0/0, 0.523/0.503 | cost 5.260/5.011, 4.951/4.899, 3.725/4.453, 21.60/20.75, 0/0, 0.517/0.504.
lat15 5.906/5.699, 5.627/5.570, 4.516/5.054, 18.26/19.35, 0/0, 0.516/0.500 | lat30 5.725/5.341, 5.379/5.231, 4.008/4.793, 18.36/22.49, 0/0, 0.511/0.489.
lat60 5.056/4.724, 4.866/4.734, 4.110/4.775, 24.54/24.18, 0/0, 0.492/0.476 | band_lo 5.963/5.722, 5.615/5.527, 4.234/4.753, 18.56/18.49, 0/0, 0.513/0.498.
band_hi 5.533/5.827, 5.286/5.697, 4.304/5.178, 23.39/18.36, 0/0, 0.523/0.508 | cool3 5.865/6.014, 5.567/5.820, 4.382/5.048, 22.50/18.33, 0/0, 0.516/0.497.
cool12 5.837/5.816, 5.522/5.640, 4.271/4.936, 23.61/21.55, 0/0, 0.514/0.496 | sleeve0.16 5.925/5.952, 5.664/5.792, 4.630/5.151, 18.24/17.49, 0/0, 0.522/0.504.
sleeve0.20 6.106/5.918, 5.812/5.768, 4.645/5.167, 18.34/18.38, 0/0, 0.521/0.502 | offset0.15 5.915/5.819, 5.755/5.720, 5.121/5.329, 18.32/18.82, 0/0, 0.506/0.493.
offset0.40 6.124/5.898, 5.780/5.798, 4.412/5.401, 17.97/18.16, 0/0, 0.530/0.523 | outage_backstop_only (touch m_sleeve_sl=8.0) C4 5.664/5.365/4.175/DD 18.69/0/0.525, D2 5.344/5.292/5.087/DD 18.42/0/0.505.
close_1m (close1+back8, m_sleeve_sl 4.0) C4 5.847/5.580/4.518/DD 18.52/0/0.519, D2 5.606/5.497/5.062/DD 17.38/0/0.504. latency_close_plus5 SKIPPED for both (close-stop fill delay needs an engine edit; none made).
Every yearly net is positive in all 30 numeric rows (no losing year anywhere); dev win rate stays 0.476-0.530 (hidden 0.50-0.56).
Bootstrap (base daily, first 4y, 30d blocks, 2000 draws, seed 0): C4 monthly p5/p50/p95 = 1.40/5.62/11.60, P(>=5)=0.589, P(loss y)=0.009, DD p50/p95 = 12.33/20.93, P(DD>20)=0.072.
D2 monthly p5/p50/p95 = 1.24/5.53/11.67, P(>=5)=0.564, P(loss y)=0.013, DD p50/p95 = 12.72/21.59, P(DD>20)=0.086: return distribution a touch lower, DD tail a touch fatter (within noise).
Small account (2000 USDT, Bybit lots, most recent year): C4 book 570/574 (0.993), rungs 1057/1083 (0.976); D2 book 557/563 (0.989), rungs 1050/1083 (0.970): nearly identical.
Verdict: YES, D2 is at least as robust as C4. D2 holds DD<=20 in 11 rows vs C4 in 10 (D2 rescues band_hi 18.36 vs 23.39 and cool3 18.33 vs 22.50, flips lat30 to breach 22.49 vs 18.36); no losing year on either side; D2 lifts the most-recent-year in all 15 rows. The cost is dev4 lower in most rows and a marginally softer bootstrap, both small.
Method: C4 books 0.5(A+B)/2+0.5(Aq+Bq)/2, D2 0.8C4+0.2(D+Dq)/2, grid_policy(0.03,0.40), win_start=5, KW budget 0.18, close5/backstop-8/m_sleeve_sl-4; bootstrap/small-account per M1 template.
