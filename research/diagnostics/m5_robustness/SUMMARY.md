# M5 (v367 LT = M4 + loss_act tighten) robustness (kpack inputs; engine globals patched for fees; no losing year in any row)
row: 5y / most recent year / gate DD / book win 5y / book win last year
- base            5.855 / 5.220 / 18.62 / 0.657 / 0.686
- cost stress     5.180 / 4.637 / 19.54 / 0.652 / 0.686   (maker 0.0004, taker 0.0012)
- latency 30 min  5.141 / 5.095 / 18.39 / 0.645 / 0.683
- skip 03:00 VN   5.252 / 5.142 / 18.09 / 0.655 / 0.700   (15-min latency elsewhere)
Reading: every goal-1 metric holds in base, latency 30 and night-skip rows; cost stress keeps 5y >= 5 but the most recent year drops to 4.64.
