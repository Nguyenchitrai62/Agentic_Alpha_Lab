# Dip refills after take-profit (dev-only event study, holding bars 2021-09-24 .. 2025-09-17; BOT idea)
R2 rules replica (rungs 2.5 .. 5 sigma, TP 1 sigma, close5 4 sigma + 8-sigma backstop). Mean net per fill (%) by dev year:
- majors, first fills  +0.38 / +0.04 / +0.40 / +0.40 (win 0.69 / 0.70 / 0.77 / 0.70)
- majors, refills      -0.05 / -0.52 / -0.08 / +0.37 (win 0.67 / 0.67 / 0.75 / 0.72)
- alts, first fills    +0.35 / -0.10 / +0.12 / +0.23;  alts, refills +0.18 / +0.07 / -0.40 / -0.08
Reading: a second flush in the same bar is continuation more often than reversal; refills have no stable edge -> closed, not registered.
