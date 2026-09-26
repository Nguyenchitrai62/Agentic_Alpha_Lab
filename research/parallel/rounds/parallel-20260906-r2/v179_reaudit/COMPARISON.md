# v179 budget re-audit — comparison

Re-audit: `research/parallel/rounds/parallel-20260906-r2/v179_reaudit/re_audit.json`
from `replicate_v179_budget_fix.py`, which reuses the `v178_v179_audit/`
replication logic exactly (ladder C1–C8/C10–C11, vol shift-2, W=60 execution,
engine_real FULL loop) with ONE change: frozen C9 fixed to the leader rule —
ONE total-only cap N_MAX = 0.05/0.30 = 1/6 of equity on the bar's total open
sleeve notional, NO per-asset cap; rn = s*g*0.0625/1.657; fills sorted by
(fill minute, rung 0..3 for k 2.5/3/3.5/4, asset BNB,BTC,ETH,SOL,XRP), taken
while used + rn <= N_MAX + 1e-12 (first rejection ends the bar).
Leader: `v179/v179_result.json` (4.141 / 18.24 / 19.81, 2055 taken / 3129
cancelled; stress 3.729 / 18.43 / 20.72, 2074 / 3110).

| row | monthly % (audit vs leader) | 4h DD % | 1m DD % @ worst bar | taken / cancelled |
| --- | --- | --- | --- | --- |
| normal | 4.141 vs 4.141 (0.000) | 18.24 vs 18.24 | 19.81 vs 19.81 @ 2022-11-09 12:00 | 2055 / 3129 vs 2055 / 3129 |
| stress | 3.729 vs 3.729 (0.000) | 18.43 vs 18.43 | 20.72 vs 20.72 @ 2022-11-09 12:00 | 2074 / 3110 vs 2074 / 3110 |

Yearly nets normal exact on all 5 anchors
(23.83 / 45.63 / 119.46 / 71.20 / 68.41, DDs 18.24/12.61/13.64/10.88/11.56).
Stress yearly within +0.00..+0.01pp
(21.00 vs 20.99, 38.20 vs 38.20, 108.38 vs 108.37, 61.61 vs 61.61,
59.77 vs 59.76) — the documented s_out+extra vs extra-as-fee accounting
delta already known from v178 (leader adds +5bps into s_out; audit deducts
5bps as exit fee). Fill universe identical: 2055+3129 = 5184 live rungs both
rows (stress 2074+3110 = 5184). Vol scale unchanged (mean_s 1.486 / 1.484).
Worst single live bar 2024-03-05 12:00 UTC on both rows.

## Verdict

- v179: REPRODUCED under the leader total-only N_MAX = 1/6 rule — monthly,
  4h DD, 1m DD, worst bar, yearly, and taken/cancelled match (stress yearly
  within the known 0.01pp fee-accounting delta).
- The prior 891-vs-2055 gap is fully explained: frozen C9 applied per-asset
  0.05 + total 0.30; the leader applies total-only 1/6 with no per-asset leg.
- Causality: budget order uses only (fill minute, rung, column) + s*g known
  at decision i; vol leg uncapped shift-2; 1m mark uses fill-minute-known L
  and contemporaneous closes. PASS.
- Economics/gate: budgeted row fails monthly >= 5% (4.141 normal, 3.729
  stress); gate DD max(18.24,19.81) = 19.81 normal, max(18.43,20.72) = 20.72
  stress (stress 1m DD exceeds 20%). Manifest `rejected` stands.
