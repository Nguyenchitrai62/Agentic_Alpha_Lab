# v187 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v187_audit/replication.json
was saved before opening v187/ (see Part A script header assumptions
B1-B11/C1-C6). Base: v183 replication in
research/parallel/rounds/parallel-20260906-r2/v182_v183_audit/replication.json.
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v187/v187_result.json
from research/parallel/rounds/parallel-20260906-r2/v187/v187_confidence_leverage.py.
Audit: rows key in
research/parallel/rounds/parallel-20260906-r2/v187_audit/replication.json
(confidence cap 2/3/4 from member agreement, 10x margin, diagnostic
liquidation count; flat cap 4 and cap 2 reference rows).

## Three-line-change check

v183 source research/parallel/rounds/parallel-20260906-r2/v183/v183_tp_exit_open_budget.py
contains exactly one occurrence of
np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP)
and exactly one occurrence of the eq_min 1m-mark line. The v187 worker
research/parallel/rounds/parallel-20260906-r2/v187/v187_confidence_leverage.py:76-92
asserts both single occurrences, then execs the v183 source with exactly
those replacements: the scale cap becomes CAPV (confidence array) / 4.0 /
v99.CAP per row, and the eq_min line gains the 4-line liquidation block
(fut_eq, gross_n, breach test, LIQ append). Margin is set at runtime via
er.MARGIN = 10.0 (10x leverage setting) with MMR = 0.01; no other source
text is touched (exec of the patched v183 module). Ladder, TP, budget
order, vol leg, governor, 1m mark and cost legs are therefore identical
to v183. PASS.

W_j check: v187_confidence_leverage.py:64-73 uses W = books (the cached
v154 ensemble, i.e. (A+B+D)/3) for |W| weights, signs from members A/B/D
reindexed to the books index, agree 0 when sum|W| == 0, cap 2/3/4 at
0.6/0.8. Audit C2 uses W_j = ensemble books on the union index with the
same thresholds; cap shares match (reported 0.065/0.045/0.89 vs audit
714/495/9735 bars = 0.0652/0.0452/0.8895, mean agree 0.9142). The
liquidation formula matches audit C5 exactly (CARRY_CAPITAL = 1.2,
fut_eq = eq_min - prev*c*expo/1.2, maintenance 0.01 on books + carry
notional + rn*taken). PASS.

## v187 (confidence leverage, 10x margin, liquidation diagnostic)

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken / cancelled / TP | liq |
| --- | --- | --- | --- | --- | --- | --- |
| reported conf normal | 4.331 | 18.69 | 18.96 | 18.96 | 2124 / 3060 / 1052 | 0 |
| audit conf normal | 4.331 | 18.69 | 18.96 | 18.96 | 2124 / 3060 / 1052 | 0 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 | 0 |
| reported conf stress | 3.929 | 18.76 | 19.03 | 19.03 | 2141 / 3043 / 1058 | 0 |
| audit conf stress | 3.925 | 18.76 | 19.03 | 19.03 | 2143 / 3041 / 1059 | 0 |
| diff | -0.004pp | 0.00pp | 0.00pp | 0.00pp | +2 / -2 / +1 | 0 |
| reported flat4 normal | 4.307 | 18.69 | 18.96 | 18.96 | 2094 / 3090 / 1035 | 0 |
| audit flat4 normal | 4.307 | 18.69 | 18.96 | 18.96 | 2094 / 3090 / 1035 | 0 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 | 0 |
| reported flat4 stress | 3.911 | 18.76 | 19.03 | 19.03 | 2110 / 3074 / 1041 | 0 |
| audit flat4 stress | 3.907 | 18.76 | 19.03 | 19.03 | 2112 / 3072 / 1042 | 0 |
| diff | -0.004pp | 0.00pp | 0.00pp | 0.00pp | +2 / -2 / +1 | 0 |
| reported cap2 normal | 4.293 | 18.75 | 19.01 | 19.01 | 2185 / 2999 / 1077 | 0 |
| audit flat2 normal | 4.293 | 18.75 | 19.01 | 19.01 | 2185 / 2999 / 1077 | 0 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 | 0 |
| reported cap2 stress | 3.890 | 18.87 | 19.13 | 19.13 | 2201 / 2983 / 1084 | 0 |
| audit flat2 stress | 3.885 | 18.87 | 19.13 | 19.13 | 2203 / 2981 / 1085 | 0 |
| diff | -0.005pp | 0.00pp | 0.00pp | 0.00pp | +2 / -2 / +1 | 0 |

Yearly nets normal exact on all 5 anchors for all three caps
(conf 33.04 / 50.57 / 118.32 / 79.57 / 62.13;
flat4 31.03 / 49.83 / 118.17 / 79.63 / 63.16;
cap2 26.50 / 50.58 / 123.96 / 74.73 / 67.04).
Stress yearly: 2024 gaps dominate (conf 67.31 vs 66.89, flat4 67.41 vs
66.97, cap2 64.81 vs 64.44) with 2021/2022/2025 within 0.02pp; worst
single live bar 2024-03-05 12:00 UTC and worst 1m bar 2022-04-21 16:00 UTC
match on every row. Grid fills identical (6972 fills, 4053 TP legs).
Mean_s conf 1.724 / flat4 1.737 / flat2 1.629 (normal); liquidations empty
on all reported rows and 0 on all audit rows.

Why the stress delta is tiny and explained:

1. All three normal rows are bit-exact (monthly, DDs, yearly,
taken/cancelled/TP, worst bars, cap distribution), so the member
agreement (weighted by |ensemble books|), cap_t mapping, 10x budget
(perp gross / 10), concurrent-open budget, TP trigger and 1m mark are
reproduced.
2. Stress accounting delta (documented, same as v183/v185): reported folds
+5bps into s_out (exit = o2*(1-(s_out+extra))); audit deducts extra as a
fee (exit = o2*(1-s_out), r -= extra). Per held rung the gap is
extra*(o2/L-1), accumulating to -0.004/-0.005pp monthly and the 2024
yearly gaps above; the 2-rung taken/cancelled and 1-TP shift follows from
the resulting rn/vol-path divergence.
3. 1m lock delta (documented, non-binding): reported locks TP rungs at net
rets (after maker fees); audit locks at gross TP/L-1. The minute minimum
binds before TP exits, so 1m DD matches exactly on every row.

## Look-ahead check

v187_confidence_leverage.py:64-73,76-92 plus patched v183 run:

- Agreement uses member books A/B/D and ensemble W at the holding-bar
index (reindexed, missing -> 0.0); member books are causal by
construction and the cap array is indexed per bar, so cap_t is known at
decision i. Vol uses the uncapped sleeve shifted by 2. PASS.
- TP only after the fill minute (first m>f with high>TP strict); TP price
L*(1+sigma) uses decision-known L/sigma. PASS.
- Budget uses only exits already happened (open count = taken with e>f,
past highs only); same (f, rung, col) order; rn = s[i]*g[i]*SIZE/nr/S_REF
with s[i] decision-known. PASS.
- Governor g[i] reads total equity at i-2; budget/min-notional use current
bar weights only; 10x margin changes the divisor, not timing. PASS.
- Liquidation is diagnostic only (LIQ list append, no equity change);
fut_eq derives from the 1m-marked eq_min of the same bar minus carry spot
cash, compared against maintenance on same-bar notionals. No future
prices. PASS.

No forward use found in the worker.

## Verdict

- Engineering REPRODUCED (all normals bit-exact; stresses within
-0.004/-0.005pp monthly, DDs exact, taken within 2, explained by the
documented s_out+extra vs extra-as-fee and gross-vs-net lock deltas).
Look-ahead PASS (agreement/cap causal, TP strictly after fill,
concurrent-open budget uses past exits only, liquidation diagnostic uses
same-bar 1m marks).
- Gate: all rows fail monthly >= 5% (conf 4.331/3.929, flat4 4.307/3.911,
cap2 4.293/3.890) while passing DD <= 20% with zero liquidations.
Manifest must stay non-live_approved.
