# v185 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v185_audit/replication.json
was saved before opening v185/ (see Part A script header assumptions
B1-B11). Base: v183 replication in research/parallel/rounds/parallel-20260906-r2/v182_v183_audit/replication.json.
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v185/v185_result.json
from research/parallel/rounds/parallel-20260906-r2/v185/v185_sleeve_outside_governor.py.
Audit: v185 key in research/parallel/rounds/parallel-20260906-r2/v185_audit/replication.json
(v183 ladder/TP/budget, rn = s[i]*0.25/4/1.657 with no governor on the sleeve;
governor still scales books and carry and reads total equity).

## One-line-change check

v183 source research/parallel/rounds/parallel-20260906-r2/v183/v183_tp_exit_open_budget.py
contains exactly one occurrence of rn = s[i] * g[i] * v171.SIZE / nr / v176.S_REF.
The v185 worker asserts that line is present, then execs the v183 source with
exactly that one replacement: rn = s[i] * v171.SIZE / nr / v176.S_REF
(diff is one line, 7 chars: `* g[i] ` removed). Books/carry/governor lines are
untouched, so g still scales books and carry and is still computed from total
equity including the sleeve. The single rn assignment feeds both the bar-close
sleeve payoff and the 1m mark path, so both move outside the governor together,
matching audit B9/B11. PASS.

## v185 (sleeve outside governor)

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken / cancelled / TP |
| --- | --- | --- | --- | --- | --- |
| reported normal | 4.311 | 18.71 | 18.99 | 18.99 | 2143 / 3041 / 1062 |
| audit normal | 4.311 | 18.71 | 18.99 | 18.99 | 2143 / 3041 / 1062 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 |
| reported stress | 3.910 | 18.85 | 19.13 | 19.13 | 2150 / 3034 / 1064 |
| audit stress | 3.906 | 18.85 | 19.13 | 19.13 | 2152 / 3032 / 1065 |
| diff | -0.004pp | 0.00pp | 0.00pp | 0.00pp | +2 / -2 / +1 |

Yearly nets normal exact on all 5 anchors
(26.66 / 51.96 / 123.84 / 74.84 / 67.01). Stress yearly:
2021 23.60 vs 23.59, 2022 44.55 vs 44.55, 2023 113.48 vs 113.47,
2024 65.01 vs 64.64 (-0.37), 2025 58.66 vs 58.65.
Grid fills identical (6972 fills, 4053 TP legs). Sleeve uncapped sums match
v183 audit base (normal 2.1433, stress 1.8778). Worst single live bar
2024-03-05 12:00 UTC on both rows; worst 1m bar 2022-04-21 16:00 UTC on both
rows; mean_s 1.629 normal / 1.627 stress both rows.

Why the stress delta is tiny and explained:

1. Normal row is bit-exact (monthly, DDs, yearly, taken/cancelled/TP, worst
   bars), so the ladder (first m in 16..238 with 1m low < L strict),
   TP trigger (first m>f high>TP strict, TP=L*(1+sigma)), concurrent-open
   budget ((open_taken(e>f)+1)*rn<=1/6 with rn=s*0.25/4/1.657 and no g), and
   the 1m mark/loop are reproduced.
2. Stress accounting delta (documented, same as v183): reported folds +5bps
   into s_out (exit=o2*(1-(s_out+extra))); audit deducts extra as a fee
   (exit=o2*(1-s_out), r-=extra). Per held rung the gap is extra*(o2/L-1),
   accumulating to -0.004pp monthly and the 2024 yearly -0.37pp; the 2-rung
   taken/cancelled and 1-TP shift follows from the resulting rn/vol-path
   divergence.
3. 1m lock delta (documented, non-binding): reported locks TP rungs at net
   rets (after maker fees); audit locks at gross TP/L-1. The minute minimum
   binds before TP exits, so 1m DD matches exactly (18.99 / 19.13).

## Look-ahead check

- TP only after the fill minute (first m>f with high>TP strict); TP price
  L*(1+sigma) uses decision-known L/sigma. PASS.
- Budget uses only exits already happened (open count = taken with e>f, i.e.
  a prior rung is still open at f iff no TP printed in (prior_f, f], past
  highs only). Same (f, rung, col) order; rn=s[i] known at decision i. PASS.
- Governor g[i] reads total equity at i-2 (books and sleeve both in eq), so
  removing g from rn does not remove any future information; books/carry
  still use g. PASS.
- Vol uses uncapped sleeve shifted by 2; 1m mark uses taken rungs with
  post-exit lock constants. PASS.

No forward use found.

## Verdict

- Engineering REPRODUCED (normal bit-exact; stress within -0.004pp monthly,
  DDs exact, taken within 2, explained by the documented s_out+extra vs
  extra-as-fee delta). Look-ahead PASS (TP strictly after fill,
  concurrent-open budget uses past exits only, governor still causal).
- Gate: both rows fail monthly >= 5% (4.311 normal, 3.910 stress) while
  passing DD. Manifest must stay non-live_approved.
