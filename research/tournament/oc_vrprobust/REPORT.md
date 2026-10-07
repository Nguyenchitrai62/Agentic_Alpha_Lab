# oc_vrprobust - LEADER NOTE (the worker stopped after saving tmp/A,B,C,C4,D.json without writing a report; numbers read from those files)

A. Pricing break-even (V2, sale k x DVOL, marks unchanged at 1.05 x DVOL - inconsistent, SL fires more often -> pessimistic):
| k | standalone dev4 mean / worst / DD | overlay G2 f 0.25 dev4 mean / worst / DD / full | recent year overlay R / DD |
|---|---|---|---|
| 0.97 | 3.441 / -0.165 / 25.82 | 6.566 / 4.365 / 16.10 / 16.01 | 5.780 / 13.70 |
| 0.92 | 2.197 / -0.821 / 26.67 | 6.241 / 4.077 / 16.44 / 16.35 | 5.364 / 13.94 |
| 0.88 | 0.963 / -1.590 / 31.18 | 5.919 / 3.783 / 16.76 / 16.68 | 5.143 / 14.36 |
| 0.85 | 0.244 / -2.326 / 32.16 | 5.724 / 3.488 / 17.03 / 16.94 | 4.952 / 15.21 |
| 0.80 | -1.230 / -3.328 / 37.55 | 5.337 / 2.934 / 17.48 / 17.40 | 4.679 / 15.56 |
| G2 | - | 5.601 / 2.588 / 16.91 / 16.82 | 4.648 / 12.90 |

B. Traded 7-day ATM IV (Fridays 08:00-11:59, |K/index - 1| <= 2 %) / DVOL at 08:00, Deribit strike data available at run time (BTC 2021-04..07,
2023-03, 2025-06; ETH 2021-04..09, 2023-03, 2025-06): pooled n 61, mean 0.868, median 0.862, p10 0.786, p90 0.941. => the research sale price
(0.97 x DVOL) overstated the short-dated premium by ~11 %.

C. Bybit fee model: immaterial (overlay dev4 within 0.01). SL every 15 min: immaterial. 1m-marked combined DD at 30 target minutes: no
increase (16.01). C4 gap stress at the worst minute (2024-01-03 14:00): -10 % gap G2 alone 3.47 % vs combined 5.65 %; -15 %: 5.20 vs 8.74
(+3.5 pp); +10 %: -3.44 vs -2.46; +15 %: -5.17 vs -3.23.

D. Sizing at k = 0.97 (optimistic): G2 + f 0.10 dev4 5.99 / 3.42 / 16.58; f 0.25 6.57 / 4.37 / 16.10; f 0.50 7.48 / 5.42 / 17.59; G2 + carry
+ f 0.10 6.26 / 3.61 / 16.43; f 0.25 (see tmp/D.json). MANUAL rows in tmp/D.json.

Leader verdict: most of the +1 pp/month headline was the DVOL pricing bias. At realistic k ~0.85-0.88 the overlay adds only ~+0.1..+0.3 pp
dev4 (better worst year, slightly higher DD). Follow-up with consistent scaling of ALL sigmas: research/tournament/oc_vrpconsistent; definitive
test needs strike-priced weekly entries (Deribit strike fetch running) and the prospective Bybit paper ledger (ops_straddlepaper).
