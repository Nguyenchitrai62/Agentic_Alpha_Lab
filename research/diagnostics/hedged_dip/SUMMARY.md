# Hedged dip limits (dev-only event study, holding bars 2021-09-24 .. 2025-09-17)
ETH / SOL / BNB / XRP dip limits (M3 rules: from minute 16, TP 1 sigma, native touch stop 8 sigma) with an equal-notional BTC short (taker both legs).
Mean net per fill (%) by dev year, k = 3: unhedged +0.47 / +0.15 / +0.47 / +0.54 (q05 -3.0 / -3.9 / -2.5 / -1.9); hedged +0.24 / +0.17 / +0.09 / +0.16
(q05 -1.95 / -2.56 / -1.69 / -1.70); corr(dip return, BTC move) 0.64 -> about half of the edge is idiosyncratic.
In the engine (v355, sleeve_hedge hook on R2): hedge 0.5 -> dev4 5.84 / DD 15.7, hedge 1.0 -> 4.71 / DD 16.8 vs R2 7.08 / 18.4 -> rejected.
