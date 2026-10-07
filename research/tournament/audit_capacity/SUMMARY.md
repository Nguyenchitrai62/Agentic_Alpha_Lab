# audit_capacity: blind replication of oc_capacity (2026-10-07)

Blind: `replication.json` written before opening `oc_capacity/REPORT.md`/`results.json`.
Independent code: `replicate.py` (header rule only; book profit = gross FIFO, no base fees).

- Coverage identical: 44,122 window orders; 41,981 matched; 1,618 bad-print.
  (Orig `n_unmatched_lag=2141` = our pure-lag 523 + bad-print 1618; labels only.)
- Shares exact (diff 0.00pp, tol 1pp): all 5 symbols x 6 cells at 10k/50k/100k.
  Binding venue BNB then XRP; BTC never binds below 500k. Confirmed.
- Drag (tol 0.05pp): 10k 0.2249 vs 0.2249; 50k 0.3432 vs 0.3428; 100k 1.0811 vs 1.0748.
  Haircut counts exact (26 / 50+4 / 135+14). Residual = gross-vs-net book basis (<=0.6%).
- Materiality calls confirmed: <=50k not material (adj 5.07), 100k material (adj ~4.33).
- Rule judgement: CONSERVATIVE net for resting maker limits (D02=D/5 upper bound,
  single-print vs replenishing depth, punitive p; optimistic no-adverse-selection leg
  is smaller and stop leg ~0). 50k call has limited buffer under adverse selection.

Verdict: PASS.
