# audit_carryborrow — blind replication vs oc_carryborrow REPORT

Blind: built from oc_carrycompound code + oc_cashcarry/results.json (33 trades)
+ v421/v421_audit G2 runs via v388.hourly; REPORT/results read ONLY AFTER
replication.json saved. Grid 2021-09-24 04:00..2026-09-23 12:00 hourly, causal
last-CLOSED-hourly marks, N=f*A entry, B=0.25*A entry @APR/8760 strictly inside
tc..ts, reset 1.0/yr, v421 full-path DD.

| combo | repl R5 / REPORT | dR | repl fullDD / REPORT | dDD |
|---|---|---|---|---|
| base f0.5@10% | 5.569 / 5.569 | 0.000 | 16.84 / 16.84 | 0.00 |
| base f0.5@15% | 5.424 / 5.424 | 0.000 | 17.01 / 17.01 | 0.00 |
| S1 f0.5@10% | 4.696 / 4.696 | 0.000 | 17.39 / 17.39 | 0.00 |
| S1 f0.5@15% | 4.550 / 4.550 | 0.000 | 17.56 / 17.56 | 0.00 |

Per-year R/DD also exact every year; borrow paid base@10%
[0.042,0.026461,0.083695,0.11149,0.02071] matches REPORT. Tolerance
0.01 %/mo, 0.05 pp DD: max |dR|=0.000, max |dDD|=0.00.
Leakage: marks strictly-before-t, tc=entry+4h, borrow strictly inside,
settled=locked ret_alloc, cap 2026-09-24, no fit/tune, no test stat feedback.
Verdict: PASS.
