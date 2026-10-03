# Rip-fade bracket SELL limits (dev-only event study, holding bars 2021-09-24 .. 2025-09-17)
Mirror of the M3 dip limit (short limit k sigma_4h above the 4h open from minute 16, TP 1 sigma, native touch stop 8 sigma, exit at the next open,
shorts earn no funding). Mean net per fill (%) by dev year, majors / 30 U2020 alts, split by the trend regime at the bar:
- majors, uptrend: k3 -0.52 / -0.38 / -0.11 / -0.13; k4 -0.33 / -0.70 / +0.06 / +0.18
- majors, downtrend: k3 +0.29 / -0.13 / -0.03 / -0.99; k4 +0.19 / 0.00 / +0.52 / -0.40
- alts, uptrend: all negative (-0.17 .. -0.33); alts, downtrend: k3 +0.05 / +0.01 / -0.19 / -0.59, k4 +0.16 / +0.19 / -0.46 / -0.55
Reading: no cell is positive in every dev year; rips do not revert reliably even in downtrends (confirms v174) -> direction closed, not registered.
