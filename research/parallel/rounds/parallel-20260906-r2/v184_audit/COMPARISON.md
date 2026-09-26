# v184 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v184_audit/replication.json
was saved before opening v184/ (see Part A script header assumptions
C1–C11). Base: v183 audit in research/parallel/rounds/parallel-20260906-r2/v182_v183_audit.
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v184/v184_result.json
from research/parallel/rounds/parallel-20260906-r2/v184/v184_hourly_ladder.py.
Audit: v184 key in research/parallel/rounds/parallel-20260906-r2/v184_audit/replication.json
(v183 4h ladder plus hourly ladder, shared concurrent-open budget).

## v184 (v183 4h ladder + hourly ladder, shared budget)

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken 4h / hourly | cancelled |
| --- | --- | --- | --- | --- | --- | --- |
| reported normal | 3.893 | 17.89 | 18.20 | 18.20 | 1578 / 6900 | 15139 |
| audit normal | 3.893 | 17.89 | 18.20 | 18.20 | 1578 / 6900 | 15139 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 | 0 |
| reported stress | 3.191 | 18.15 | 18.99 | 18.99 | 1619 / 7052 | 14946 |
| audit stress | 3.189 | 18.15 | 19.00 | 19.00 | 1619 / 7055 | 14943 |
| diff | -0.002pp | 0.00pp | +0.01pp | +0.01pp | 0 / +3 | -3 |

Yearly nets normal exact on all 5 anchors
(21.09 / 48.42 / 128.35 / 53.73 / 56.75, DDs
17.89/10.23/14.52/12.95/11.39, fills
2033/2179/2190/2190/2183, mean_g
0.907/0.985/0.969/0.990/0.997). Worst 1m bar
2022-11-09 04:00 UTC on both rows; audit worst live bar
2024-03-05 12:00 UTC (same as v183).
Stress yearly reported vs audit: 2021 14.49 vs 14.43 (-0.06),
2022 39.73 vs 39.69 (-0.04), 2023 106.52 vs 106.51 (-0.01),
2024 40.62 vs 40.62 (0.00), 2025 41.74 vs 41.72 (-0.02).
Grid fills: 4h 6972 / TP 4053 both (matches v183 audit);
hourly 24374 fills / 13295 TP in audit.

Why the stress delta is tiny and explained:

1. Normal row is bit-exact (monthly, DDs, yearly, taken 4h/hourly,
cancelled, worst 1m bar), so the hourly ladder (base = 1m open 60h,
L = base*(1-k*sigma_1h), live 16..57 h0 else 60h+4..60h+57,
TP = L*(1+sigma_1h) first m>fill <60(h+1) high>TP else next hour open),
the shared budget ((minute, 4h before hourly, rung, asset) order,
(open(e>f)+1)*rn<=1/6), vol (unbudgeted sum both ladders shift 2),
and the 1m mark are reproduced.
2. Stress accounting delta (documented): reported
(v184_hourly_ladder.py:80,92, also v183 rung_table_tp) folds +5bps into
s_out (exit = xo*(1-(s_out+extra))); audit (C3/C6) deducts extra as a fee
(exit = xo*(1-s_out), r -= extra, v179 style). Per held rung the gap is
extra*(xo/L-1), accumulating to -0.002pp monthly and the small yearly
gaps above; the 3-rung taken/cancelled shift follows from the resulting
rn/vol-path divergence. Same delta as v178/v179 and v182/v183 audits.
3. 1m lock delta (documented, non-binding): reported
(v184_hourly_ladder.py:168-173) locks exited rungs at net rets
(after fees) for m>=x; audit (C10) locks 4h TP at gross TP/L-1 and hourly
timeout at gross exit_open/L-1. The minute minimum binds before exits on
crash legs, so 1m DD matches to 0.01pp (18.99 vs 19.00 stress).

## Look-ahead check

v184_hourly_ladder.py:49-97,143-161,165-175:

- sigma_1h uses only hours before T: h_open = 1m opens at 0/60/120/180 of
each holding bar flattened in time order; ret = pct_change; sig_h =
rolling 1440 min 480 std; sig_t[1:] = sig_h[:-1,3,:], i.e. the rolling std
at hourly index (i-1)*4+3 (last hour of the PREVIOUS holding bar) for
holding bar i. Both opens feeding the last return are at or before that
hour, strictly before T. PASS. Audit C4 implements the same window
(rolling 1440 min 480 at (i-1)*4+3).
- base = 1m open of minute 60h of T, known at the hour start before live
minutes 16..57 (h0) or 60h+4..60h+57 (h>0). PASS.
- Fill first low<L strict inside the live window; TP first m>fill with
m<60(h+1) and high>TP strict, both past-only within the bar. Timeout at
the next hour open (h3: next 4h open + funding at T+4h). PASS.
- 4h leg calls v183 rung_table_tp unchanged (TP strictly after fill,
concurrent-open budget uses past exits only). PASS.
- Shared budget order (minute, 4h first, rung, asset) counts taken with
x>f as still open at f, i.e. a prior rung is open iff no TP/timeout
printed in (prior_f, f] (past minutes only); rn = s*g known at bar close.
Same mask both cost rows; vol shift(2). PASS.
- 1m mark over taken rungs only, f..min(x,240) at close/L-1 then locked
(reported at net rets, audit at gross) — both post-exit constants, no
future price. PASS.

No forward use found in the worker.

## Verdict

- v184: engineering REPRODUCED (normal bit-exact; stress within -0.002pp
monthly, DDs within 0.01pp, taken within 3, explained by the documented
s_out+extra vs extra-as-fee and gross-vs-net lock deltas). Look-ahead
PASS (sigma_1h strictly before T, hourly base/fill/TP/timeout and shared
budget use past minutes only). Gate: both rows fail monthly >= 5%
(3.893 normal, 3.191 stress) while passing DD <= 20%.
Manifest must stay non-live_approved.
