# v186 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v186_audit/replication.json
was saved before opening v186/ (see Part A script header assumptions
B1-B11). Base: v183 replication in research/parallel/rounds/parallel-20260906-r2/v182_v183_audit
and alt-data handling in research/parallel/rounds/parallel-20260906-r2/v181_audit.
Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v186/v186_result.json
from research/parallel/rounds/parallel-20260906-r2/v186/v186_sleeve_eleven_assets.py.
Audit: v186 key in replication.json (v183 rules on 11 sleeve assets in column
order BNB BTC ETH SOL XRP DOGE ADA LINK LTC AVAX TRX, books majors-only, one
shared open-notional cap 1/6 ordered by minute rung asset-column, uncapped
11-asset vol leg shifted 2 bars, 1m mark of books on majors plus all taken
sleeve rungs).

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken / cancelled / TP |
| --- | --- | --- | --- | --- | --- |
| v186 reported normal | 4.29 | 17.56 | 17.67 | 17.67 | 3317 / 7574 / 1592 |
| audit normal | 4.29 | 17.56 | 17.67 | 17.67 | 3317 / 7574 / 1592 |
| diff (audit − reported) | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 |
| v186 reported stress | 3.879 | 17.75 | 17.84 | 17.84 | 3343 / 7548 / 1603 |
| audit stress | 3.878 | 17.75 | 17.83 | 17.83 | 3343 / 7548 / 1603 |
| diff | −0.001pp | 0.00pp | −0.01pp | −0.01pp | 0 / 0 / 0 |

Yearly nets normal exact on all 5 anchors
(23.88 / 51.00 / 127.24 / 77.37 / 64.87, DDs
17.56/10.59/13.19/8.72/11.67). Stress yearly:
2021 20.44 vs 20.43, 2022 44.93 vs 44.91, 2023 114.81 vs 114.80,
2024 68.60 vs 68.59, 2025 55.15 vs 55.14.
Worst single live bar 2024-03-05 12:00 UTC on both rows; worst 1m bar
2022-04-21 16:00 UTC on both rows; mean scale 1.447 normal / 1.443 stress.
Grid ladder: 14593 fills / 8296 TP, of which majors 6972 (as v183:
BNB 1511 BTC 1429 ETH 1449 SOL 1041 XRP 1542) plus alts 7621.

Why the stress delta is tiny and explained:

1. Normal row is bit-exact (monthly, DDs, yearly, taken/cancelled/TP, worst
   bars), so the 11-asset ladder (L=open(T)*(1−k*sigma), first low<L in
   16..238, TP=L*(1+sigma) at first m>f high>TP strict), the shared
   concurrent-open budget ((open_taken(e>f)+1)*rn<=1/6 over asset columns
   0..10), the uncapped 11-asset vol leg, and the 1m mark (books on majors
   only plus all open alt rungs) are reproduced.
2. Stress accounting delta (documented): reported folds +5bps into s_out
   (exit=o2*(1−(s_out+extra))); audit (B4/B7) deducts extra as a fee
   (exit=o2*(1−s_out), r−=extra, v179 style). Per held rung the gap is
   extra*(o2/L−1), accumulating to −0.001pp monthly and −0.01pp on the 1m
   mark. Same delta as the v183 audit; taken/cancelled/TP are unaffected.
3. The two-line patch claim checks out. The leader builds v186 by exec of
   the v183 source with exactly two replacements, each asserted count==1:
   budget fill collection for a in range(len(cols)) becomes
   for a in range(fmins.shape[2]) (loops over all 11 sleeve assets), and the
   books mark path = ((Cm / o1[i] − 1) * w).sum(axis=1) becomes
   path = ((Cm[:, :len(cols)] / o1[i] − 1) * w).sum(axis=1) (books leg on
   the majors only). rung_table_tp is then called with the 11-column
   universe (majors cubes plus v182 alt cubes with the same within-bar
   forward-fill), so vol (sum over rets), budget, and sleeve marks all cover
   11 assets while books, execution, governor, and funding stay majors-only.
   Nothing else in the v183 source is touched.

Look-ahead check (v186_sleeve_eleven_assets.py plus execd v183 logic):

- TP only after the fill minute (first m>f high>TP strict); TP price uses
  decision-known L/sigma. PASS.
- Budget uses only exits already happened (open count is taken rungs with
  exit minute > current fill minute, i.e. past highs only); same
  (minute, rung, asset-column) order; rn=s*g known at decision. PASS.
- Alt 1m/4h/funding aligned as-of each bar close with within-bar
  forward-fill only; vol shifted 2 bars. PASS.
- 1m mark locks TP rungs at a post-exit constant and books on majors only;
  no future price enters. PASS.

No forward use found in the worker.

Verdict:

- v186: engineering REPRODUCED (normal bit-exact; stress within −0.001pp
  monthly and −0.01pp 1m DD, taken/cancelled/TP exact, explained by the
  documented s_out+extra vs extra-as-fee delta). Look-ahead PASS (TP
  strictly after fill, shared budget uses past exits only, alt data as-of
  close). Gate: both rows fail monthly ≥ 5% (4.29 normal, 3.879 stress)
  while passing DD ≤ 20% (17.67 / 17.84). Manifest status rejected with
  live_approved false matches this audit and must stay non-live_approved.
