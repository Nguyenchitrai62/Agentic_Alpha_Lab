# G2 drawdown anatomy (dev 2021-09-24..2025-09-24 only)

Reference reproduced exactly: dev4 6.527 %/mo, dev DD 17.33, dev book win 0.51.
12 episodes >7% on 4h close. Two DD sources, roughly half/half:
book concentration (ep3: book -13.76, 5-coin all-long into -11% BTC;
ep9: book -13.73 net-short into +15.9% BTC squeeze) and systemic dip
flushes (ep4/ep5: sleeve -9.6/-7.6 with 18 stops each; ep10: sleeve -8.4).
10 flush bars (>=3 stopped coins) carry 51% of all stop losses (-53 of -104);
sleeve net is +216.6 on other bars vs -36.6 on flush bars. 172 TP-cluster
bars carry 68% of TP wins; flush bars also print +18.2 in TP wins.
High |net| exposure precedes episodes (pre-5d |net| 0.6-1.0 vs 0.37 outside)
but top-decile |net| days average +0.86%/d at 67% win (vs +0.22%/55% overall):
exposure pays on average; episodes are its tail. Aug-05 flush (-12.6% sleeve
in 2 bars) sits in ep9's recovery leg (see JSON post_hoc note).
Counterfactuals (same agents, dev): A vol-x0.5: dev4 4.752 (-1.78), DD 17.30
(-0.03), worst 2.81. B flush-skip-3: dev4 6.540 (+0.01), DD 17.27 (-0.06),
worst 3.60, 43 fills skipped. C budget-0.13-in-DD: dev4 6.197 (-0.33),
DD 18.92 (+1.59!), worst 2.82 -- cutting the sleeve in DD forfeits its
recovery earnings. Ranking by DD-reduction/dev4-loss: 1) B (free, tiny),
2) A (0.02 DD per point, too expensive), 3) C (harms both). No tested lever
buys material DD reduction; B is the only safe one.
