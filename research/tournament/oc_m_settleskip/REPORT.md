# oc_m_settleskip REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #6 (MANUAL product): Settlement-clock placement skip, no-threshold
funding clock. Pre-registered rows only: M5_human (deployed MANUAL
reference), V1_SETTLE (skip NEW book+dip brackets on bars whose holding
bar (idx+4h, idx+8h] contains a 00/08/16 UTC settlement), V2_SETTLE_NEXT
(V1 + skip the bar after: settle[i] OR settle[i-1]). Clock-only, no fit,
no threshold. Holds/exits unchanged (resting TP/SL stay).

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Phase cross-nets match oc_m_btceth's M5 exactly.
- Harness: MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 /
  sleeve_start=16, night bar skipped, agents ON); gate costs maker
  0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts nothing; limits fill
  only on 1m trade-through, no fill minutes 0..15, stop-first.
- Gate stats (non-night bars, all phases/years): V1 skips ~40.0% of bars
  (2 of 5 non-night bars; the night bar itself is a settle bar);
  V2 skips 100.0% (settle bars alternate, so settle[i] OR settle[i-1] is
  always True after the first bar) -> V2 places nothing, as pre-registered.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | V1_SETTLE R | V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 (dev) | 0.847 | -0.302 | 0.000 | 16.54 | 16.64 | 0.00 |
| 2022-09-24 (dev) | 1.585 | 1.157 | 0.000 | 17.94 | 15.79 | 0.00 |
| 2023-09-24 (dev) | 4.413 | 1.494 | 0.000 | 17.36 | 17.71 | 0.00 |
| 2024-09-24 (dev) | 7.948 | 4.896 | 0.000 | 8.24 | 9.90 | 0.00 |
| 2025-09-24 (POST-RELEASE, scored once) | 3.994 | 2.926* | 0.000 | 11.69 | 10.54* | 0.00 |

*V1 last-year row from the same single pass, shown for completeness only,
never used for any decision and not re-scored (oc_m_top2 precedent).

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | lose | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 0 | 3.994 |
| V1_SETTLE | 2.019 | -0.302 | 17.71 | 20.59 | 1.794 | -0.302 | 17.71 | 1 | 2.926* |
| V2_SETTLE_NEXT (PICK) | 0.000 | 0.000 | 0.00 | 0.00 | 0.000 | 0.000 | 0.00 | 0 | 0.000 |

Trades/wins (pooled 5y, 4 phases): book M5 3744 @.6482, V1 3365 @.6351,
V2 0 (no trades); rung M5 6417 @.7013, V1 3430 @.7023, V2 0;
all-trade win M5 .6817 / V1 .6690 / V2 n/a. Per-year book win: M5
.6429/.6264/.6395/.6402/.6837; V1 .6166/.5961/.6403/.6239/.6820.
MANUAL gate (R5>=5, fullDD<20, book win>=55%): all rows fail R5
(V1 also fails fullDD 20.59 > 20 on the full path).

## Selection (dev4 ONLY, robust criterion)

Eligible (DDdev4 <= 20 and no losing dev year): M5_human True, V1_SETTLE
False (2021 -0.302, one losing dev year), V2_SETTLE_NEXT True (flat 0.0,
no losing year). No variant has dev4 mean >= 5; among the eligible pool
{V2} the pick is V2_SETTLE_NEXT by default (highest WORST 0.000, only
candidate). PICK_dev4 = V2_SETTLE_NEXT. The most recent year was scored
ONCE, for the pick (0.000) and M5_human (3.994) only, labelled
POST-RELEASE above. 5y numbers are context only.

## Why it failed

V1 deletes ~40% of placements including winners: Rdev4 falls 1.867pp vs
M5 (1.794 vs 3.661), the worst dev year turns losing (-0.302 vs 0.847),
book win drops 1.3pp (.6351 vs .6482), and full-path DD rises to 20.59
(above the 20 gate) even though max yearly DD is flat. The settlement
clock carries no entry edge; it just cuts exposure ~40% and keeps the
losers' shape. V2 is degenerate by construction (100% skip -> flat 0.0):
technically "eligible" but economically empty, R5 0.0. Neither variant
closes any of the 1.272pp MANUAL gap to 5 %/month: V1 R5 2.019
(-1.709pp vs M5, gap 2.981pp); the pick V2 R5 0.000 (-3.728pp vs M5,
gap 5.000pp).

## Leakage audit

- feature timing: skip keys only on the bar timestamp via the fixed UTC
  clock (settle_flags on idx+4h/idx+8h; V2 also uses settle[i-1],
  strictly past); R2 size/TP tables keyed by holding-bar time T
  (bar-open lookup only); no 1m/minute/fill data enters any decision
  (causality test in tests/test_oc_m_settleskip.py bans fill-minute and
  premium/funding markers; V2's previous-bar use is past-only).
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; settlements are
  the fixed public UTC schedule; human night schedule identical both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; dip
  timeout at next 4h open; gate costs inside the engine.

## Verdict

V1 loses 1.709pp vs M5 (R5 2.019, 2021 losing, fullDD 20.59 breach) and
V2 is flat-by-construction (R5 0.0, no trades): the settlement clock has
no entry edge, it only deletes exposure. Close direction #6.
MANUAL gap verdict: the dev4 pick (V2, R5 0.000) closes 0.000pp of the
1.272pp MANUAL gap to 5 %/month (gap stays 5.000pp; V1 closes -1.709pp).

Bo lich settlement khong co edge vao lenh: V1 mat 1,71 diem %/thang va thua nam 2021, V2 khong giao dich: loai.
MANUAL van thieu ~1,27 diem %/thang (pick chi dat R5 0,0): khong dua clock skip vao san xuat, dong huong #6.
Can edge vao lenh chu khong phai lich skip: giu M5_human, can bang chung prospective cho moi y tuong tiep theo.
