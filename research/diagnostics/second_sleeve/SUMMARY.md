# Study B verdict: NO second sleeve (dev 2021-09-24..2025-09-24 only)

12h (P=720, 1903 majors rungs, skip 17.0%, stopped 78 vs 92 base):
baseline year nets +11.8/-0.6/+8.3/+23.5%, dev4 0.83%/mo, DD 26.3%.
policy year nets +26.6/+8.3/+14.2/+33.6% (positive every year), dev4 1.55%/mo,
DD 32.8% (yearly DDs 11.1/15.0/32.8/14.5); win 67-76%, mean +0.3..+88 bps/rung net.
1d (P=1440, 891 rungs, skip 10.8%, stopped 39 vs 40):
baseline +23.9/-15.6/+40.8/+17.4%, dev4 1.15%/mo, DD 24.1%.
policy +11.4/-14.6/+46.3/+20.5% (still a losing year), dev4 1.08%/mo, DD 21.9%.
E3: G2 reproduced dev4 6.527 (ref 6.527), devDD 17.15 (ref 17.33; diff = own
dev-only DD def without eq_max highs). Daily corr policy vs G2: 0.113 (12h),
0.162 (1d) - independent but weak. Blends (monthly rebalance, indicative):
12h x=0.15/0.25/0.35 dev4 5.85/5.39/4.91, DD 15.98/16.28/16.65;
1d x=0.15/0.25/0.35 dev4 5.77/5.26/4.74, DD 14.88/14.14/14.32 -
all below G2 alone (6.527) at similar DD. Verdict: neither stream is worth
adding; close the direction. Leakage: END=2025-09-24 excl, sigma closed-only,
state at f-1, fills min5 trade-through, fits on t_exit<anchor-7d, stop-first,
no stat on >=2025-09-24 (asserted). No post-hoc changes.
