# Whale-burst reversal study: summary
Universe: BTC/ETH/SOL/BNB/XRP 1m, dev 2021-09-24..2025-09-23; thresholds fit pre-2021-09-24. Costs: maker 2bps/taker 5.5bps (round trip ~4-8bps+).
Grid: 108 real + 108 random-baseline rows (2 sides x q{99.5,99.9,99.97} x d{0,10,30}bps x tp{0.3,0.6,1.0}% x H{60,240}); SL 1.5%, stop-first ties.
Stable rows (mean net >0 in ALL 4 years): 0 of 108. Every real row is negative: means -20.2..-7.1bps/trade, t-stats down to -9.6.
Best real: SELL-burst LONG q99.5 d30 tp0.3% H240: n=8031 ev, 4491 fills (fill 0.56), mean -7.1bps, med +26.0bps, win 0.80, yearly means [-15.2,-20.1,-5.3,-5.8] (all <0).
Best SHORT (BUY-burst q99.5 d30 tp0.3% H60): n=7104 ev, 3854 fills (0.54), mean -9.8bps, med +26.1bps, win 0.69, yearly all <0.
Random baseline is also negative (means -15.1..-1.8bps) but beats real everywhere: same best-row rules score -5.0bps (long) / -3.4bps (short) at lower fill rates (0.35-0.56) - bursts add no edge over random entries.
Profile: high win rate + positive median but negative mean = short-vol payoff; the 1.5% stop tail dominates the small TP/timed gains.
Dip-ladder overlap (long fills <= 4h-open*(1-2.5*sigma)): only 4.6% of best-row fills (7.1% at q99.97); non-overlapping subset mean -6.6bps (n=4283) - still negative, so no hidden edge outside the pipeline zone.
Per-symbol best-row means all <0 (SOL -4.2, BTC -6.9, ETH -6.8, XRP -16.9bps; BNB ~no bursts at q99.5); d=30 fills most (0.54-0.63) yet loses most per trade.
Fill rates overall 0.54-0.91 (deeper d fills more); no (side,q,d,t,H) survives costs in any single year consistently, let alone four.
Verdict: NO TRADABLE EDGE. Whale bursts do not predict tradeable reversals under executable limit/SL/TP rules; do not build a sleeve on this. Close the direction.
