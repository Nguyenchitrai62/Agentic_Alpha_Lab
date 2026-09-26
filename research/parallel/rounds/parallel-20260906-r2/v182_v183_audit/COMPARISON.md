# v182 + v183 blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v182_v183_audit/replication.json
was saved before opening v182/ or v183/ (see Part A script header assumptions
B1–B12). Base: v179 re-audit (total-only cap 1/6) and v180 audit (minute f-1
gate features). Leader files were not edited.

## v182 (pooled 11-asset gate, majors-only trading)

Reported: v182/v182_result.json from v182/v182_pooled_gate.py.
Audit: v182 key in replication.json (12 features, no asset code, breadth over
five majors incl self, btc_depth at f-1, pooled HGB, v179 total-only budget).

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken / cancelled |
| --- | --- | --- | --- | --- | --- |
| v182 reported normal | 4.143 | 18.31 | 20.04 | 20.04 | 1878 / 2733 |
| audit normal | 4.165 | 18.15 | 19.39 | 19.39 | 1884 / 2716 |
| diff (audit − reported) | +0.022pp | −0.16pp | −0.65pp | −0.65pp | +6 / −17 |
| v182 reported stress | 3.741 | 18.49 | 20.51 | 20.51 | 1889 / 2722 |
| audit stress | 3.774 | 18.31 | 19.74 | 19.74 | 1898 / 2702 |
| diff | +0.033pp | −0.18pp | −0.77pp | −0.77pp | +9 / −20 |

Yearly nets normal (reported vs audit): 2021 23.83 vs 23.15 (−0.68),
2022 49.00 vs 49.81 (+0.81), 2023 115.57 vs 115.83 (+0.26),
2024 70.84 vs 72.64 (+1.80), 2025 68.11 vs 68.32 (+0.21).
Worst 1m bar matches: 2022-11-09 12:00 UTC (FTX window) both rows.

IC / kept on majors test fills per anchor (reported vs audit):

| anchor | train (pooled) | test majors | reported IC / kept | audit IC / kept |
| --- | --- | --- | --- | --- |
| 2021-09-24 | 3621 | 932 | −0.0492 / 817 | −0.0551 / 831 (+14) |
| 2022-09-24 | 5578 | 973 | 0.1623 / 855 | 0.1539 / 854 (−1) |
| 2023-09-24 | 7687 | 1250 | 0.1144 / 1111 | 0.1282 / 1101 (−10) |
| 2024-09-24 | 10375 | 946 | 0.1701 / 890 | 0.2010 / 885 (−5) |
| 2025-09-24 | 12338 | 1092 | 0.1776 / 947 | 0.1793 / 938 (−9) |

Train/test counts match exactly (pooled ladder reproduced, incl
train_alts 1867/2899/4028/5466/6485 implied by pooled−majors).
Live totals: reported 4620 kept vs audit 4609 (−11).

Why the gaps are small and explained:

1. Rung fills match. Train counts identical per anchor and majors test
   counts identical (932/973/1250/946/1092), so the 11-asset ladder
   (L=open(T)*(1−k*sigma), first low<L in 16..238, exit open(T+4h)*(1−s_out),
   funding at T+4h) is reproduced. Fill math is not the gap source.
2. Feature/model deltas (kept ±5–14 per anchor, IC ±0.006–0.031).
   Reported (v182_pooled_gate.py:100-108) leaves NaN features to HGB-native
   missing handling, vspike denominator max(mean*5, 1e-9), taker15
   denominator max(sum, 1e-9); audit (B6) falls back (r5/r15/rng/trend/r1d 0,
   vspike 1, taker15 0.5, btc_depth 0; depth-invalid candidates skipped).
   Reported funding = funding_at_bar_open with 0→NaN→ffill at t; audit =
   last non-zero raw fundingRate at or before t. Together these move a few
   dozen borderline pred>0 calls, hence +6 taken and +0.02pp monthly.
3. Vol leg (documented assumption delta). Audit B8 froze vol uses UNCAPPED
   majors sleeve shifted by 2. Reported (v182_pooled_gate.py:156-159)
   gates fk/rk before v179.run, whose unit then sums the gated rk (KEPT but
   budget-uncapped, same pattern as the v180 finding). Audit vol is thus
   slightly more conservative, explaining part of the DD gap (−0.16pp 4h,
   −0.65pp 1m) alongside the kept-count effect. Payoff timing,
   N_MAX=0.05/0.30=1/6, sort (f, rung, col), rn=s*g*0.25/4/1.657 identical.
4. 1m mark matches in shape. Same worst bar, same formula (taken rungs only
   from fill minute at close/L−1). Level gap follows from (2)–(3).

## v183 (TP exits + concurrent-open budget)

Reported: v183/v183_result.json from v183/v183_tp_exit_open_budget.py.
Audit: v183 key in replication.json (TP=L*(1+sigma), first m>f high>TP maker
both sides no funding else next-open taker exit, concurrent-open budget).

| row | monthly % | 4h DD % | 1m DD % | gate DD | taken / cancelled / TP |
| --- | --- | --- | --- | --- | --- |
| v183 reported normal | 4.284 | 18.75 | 19.01 | 19.01 | 2185 / 2999 / 1077 |
| audit normal | 4.284 | 18.75 | 19.01 | 19.01 | 2185 / 2999 / 1077 |
| diff | 0.000pp | 0.00pp | 0.00pp | 0.00pp | 0 / 0 / 0 |
| v183 reported stress | 3.882 | 18.87 | 19.13 | 19.13 | 2201 / 2983 / 1084 |
| audit stress | 3.877 | 18.87 | 19.13 | 19.13 | 2203 / 2981 / 1085 |
| diff | −0.005pp | 0.00pp | 0.00pp | 0.00pp | +2 / −2 / +1 |

Yearly nets normal exact on all 5 anchors
(26.45 / 50.58 / 123.08 / 74.69 / 67.01, DDs
18.75/12.97/14.18/10.87/11.56). Stress yearly:
2021 23.53 vs 23.52, 2022 43.09 vs 43.07, 2023 112.59 vs 112.58,
2024 64.78 vs 64.40 (−0.38), 2025 58.66 vs 58.65.
Worst single live bar 2024-03-05 12:00 UTC on both rows; worst 1m bar
2022-04-21 16:00 UTC on both rows.

Why the stress delta is tiny and explained:

1. Normal row is bit-exact (monthly, DDs, yearly, taken/cancelled/TP, worst
   bars), so TP trigger (first m>f high>TP strict), TP=L*(1+sigma),
   concurrent-open budget ((open_taken(e>f)+1)*rn<=1/6), and the 1m
   mark/loop are reproduced.
2. Stress accounting delta (documented): reported
   (v183_tp_exit_open_budget.py:60,74) folds +5bps into s_out
   (exit=o2*(1−(s_out+extra))); audit (B4/B7) deducts extra as a fee
   (exit=o2*(1−s_out), r−=extra, v179 style). Per held rung the gap is
   extra*(o2/L−1) ≈ 0.5–4 bps, accumulating to −0.005pp monthly and the
   2024 yearly −0.38pp; the 2-rung taken/cancelled and 1-TP shift follows
   from the resulting rn/vol-path divergence. Same delta as v178/v179.
3. 1m lock delta (documented, non-binding): reported
   (v183_tp_exit_open_budget.py:143-145) locks TP rungs at net rets
   (after maker fees); audit (B11) locks at gross TP/L−1. The minute minimum
   binds before TP exits (crash legs), so 1m DD matches exactly (19.01 /
   19.13) regardless.

## Look-ahead check

v182 (v182_pooled_gate.py:91-108,143-149):

- depth/r5/r15/rng/breadth/btc_depth: 1m close/high/low at p=f−1 (and p−5 /
  p−15 for r5/r15; breadth over five majors at same p; btc_depth BTC at same
  p). All indices ≤ f−1 of holding bar T. PASS.
- vspike: volume(f−5..f−1)/5*mean(volume(0..f−6)). PASS.
- taker15: taker_buy(f−15..f−1)/volume(f−15..f−1). PASS.
- trend: open(T)/mean(last 42 4h opens incl open(T))−1 (shift(−1)).
  open(T) is the holding-bar open, known at decision before minute 16. PASS.
- r1d: open(T)/open(T−24h)−1 over sigma (shifts −1/5). PASS.
- funding: funding_at_bar_open ffilled at t (last non-zero settlement at or
  before t). PASS.
- k: rung constant; no asset code (pooled mechanism). PASS.
- Training T+4h<anchor−1d and T≥START+30d (=2020-03-02); test majors t in
  [anchor, anchor+365d). One-day embargo. PASS.
- Gate pred>0 at fill f; budget order (fill minute, shallower rung,
  BNB,BTC,ETH,SOL,XRP) uses only fills known at their minute; same mask
  both cost rows; vol shift(2). PASS.

v183 (v183_tp_exit_open_budget.py:64-77,123-132,139-147):

- TP only after the fill minute: after=(minute>f)&(Hf>tp)&filled strict;
  x=first such minute else 240 (next-open code). TP price L*(1+sigma) uses
  decision-known L/sigma. PASS.
- Budget uses only exits already happened: open_now counts taken with
  xmins>f, i.e. a prior rung is still open at f iff no TP printed in
  (prior_f, f] (past highs only). Same (f, rung, col) order; rn=s*g known
  at decision i. PASS.
- 1m mark: rung marked f..min(x,240) at close/L−1, locked after (reported at
  net rets, audit at gross TP — both post-exit constants, no future price).
  PASS.

No forward use found in either worker.

## Verdict

- v182: engineering REPRODUCED (fills/train/test exact, kept within ±14 per
  anchor, monthly within +0.02–0.03pp, DD within ~0.2–0.8pp, explained by
  the documented NaN-fallback/funding-window and vol-gated-vs-ungated
  deltas). Look-ahead PASS. Gate: reported rows fail DD ≤ 20% on gate DD
  (20.04 normal, 20.51 stress) while passing monthly; audit gate
  (19.39/19.74) is not binding — the reported gate is. Manifest must stay
  non-live_approved.
- v183: engineering REPRODUCED (normal bit-exact; stress within −0.005pp
  monthly, DDs exact, taken within 2, explained by the documented
  s_out+extra vs extra-as-fee and gross-vs-net lock deltas). Look-ahead
  PASS (TP strictly after fill, concurrent-open budget uses past exits
  only). Gate: both rows fail monthly ≥ 5% (4.284 normal, 3.882 stress)
  while passing DD. Manifest must stay non-live_approved.
