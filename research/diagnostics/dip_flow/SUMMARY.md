# Order-level flow before a dip fill (dev-only event study, majors, fills 2021-09-24 .. 2025-09-17; BOT idea)
R2 rules replica; flow from the kept 1m order-level store over the 15 minutes before the fill. Spearman(feature, rung outcome) by dev year:
- big_share (share of >= 100k orders in the sell notional): -0.13 / -0.20 / -0.14 / -0.03, but tercile mean outcomes do not separate
  (top vs bottom %: 0.21/0.20, -0.04/-0.01, 0.41/0.41, 0.48/0.31)
- big_imb15: -0.03 / -0.10 / -0.05 / -0.10 (terciles mixed); imb15 and exhaust flip sign across years
Reading: no feature separates the mean dip outcome consistently -> no sizing signal; direction closed, not registered.
