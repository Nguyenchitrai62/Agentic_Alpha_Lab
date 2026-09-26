# v188 + engine_user blind audit — Part B comparison

Blind: research/parallel/rounds/parallel-20260906-r2/v188_audit/replication.json
was saved before opening v188/ or engine_user/ (see Part A script header
assumptions A1-A12). Leader files were not edited.

Reported: research/parallel/rounds/parallel-20260906-r2/v188/v188_result.json
from research/parallel/rounds/parallel-20260906-r2/v188/v188_user_engine_sl_tp.py
using research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py.
Audit: rows in research/parallel/rounds/parallel-20260906-r2/v188_audit/replication.json
(m = 2, 3, 4 with sleeve; m4 without sleeve as selected reference).

## v188 (user-rule engine, limit + SL/TP, adverse funding)

| row | monthly % rep / aud / diff | dev4 rep / aud | gate DD rep / aud | fills rep / aud | stops rep / aud | TP rep/aud | rungs rep/aud |
| --- | --- | --- | --- | --- | --- | --- | --- |
| m2 | 3.083 / 3.042 / -0.041 | 3.117 / 3.108 | 20.25 / 21.14 | 35593 / 36447 (+854) | 561 / 582 (+21) | 241 / 242 (+1) | 2547 / 2549 (+2) |
| m3 | 3.441 / 3.383 / -0.058 | 3.325 / 3.295 | 19.51 / 19.78 | 35635 / 36549 (+914) | 192 / 202 (+10) | 104 / 104 (0) | 2557 / 2559 (+2) |
| m4 | 3.533 / 3.486 / -0.047 | 3.529 / 3.513 | 19.03 / 19.30 | 35882 / 36838 (+956) | 83 / 85 (+2) | 54 / 54 (0) | 2545 / 2550 (+5) |
| m4 no sleeve | 3.377 / 3.332 / -0.045 | 3.318 / 3.305 | 18.66 / 18.93 | 35760 / 36703 (+943) | 83 / 86 (+3) | 54 / 54 (0) | 0 / 0 |

Yearly nets (rep / aud):
m2 17.38/17.33, 37.22/37.20, 92.14/91.27 (-0.87), 41.02/41.15 (+0.13), 41.72/38.92 (-2.80).
m3 20.10/20.05, 34.28/34.29, 96.72/96.03 (-0.69), 51.53/49.99 (-1.54), 58.34/55.33 (-3.01).
m4 22.92/22.87, 45.81/45.87, 86.04/84.95 (-1.09), 58.48/58.23 (-0.25), 51.96/49.01 (-2.95).
no-sleeve 18.33/18.28, 45.93/45.98, 74.50/73.70 (-0.80), 59.01/58.79 (-0.22), 53.06/50.04 (-3.02).
4h DD exact on m2 (20.12) and m3 (19.25); m4 18.94 vs 18.93 (-0.01). 1m DD
rep/aud: m2 20.25/21.14, m3 19.51/19.78, m4 19.03/19.30, nosleeve 18.66/18.93.
Selection identical: m4 (best dev4 with DD<=20, no losing first-four years);
m2 fails DD in both (20.25 / 21.14). No losing years in both.

Why the deltas are small and explained:
1. Quantity base: reported dq = dw / o1 (4h open T); audit A5 dq = dw*equity/limit
   (limit 10bps better). 0.1% size gap drifts w, crossing min-notional
   (BTC100/ETH20/else5) on ~1k bars -> +850-950 fills, +2-21 stops, -0.04/-0.06pp
   monthly. Entry-weighted SL/TP then shifts marginally.
2. Fill-vs-stop tie at the fill minute: reported checks held 0..f-1 (fill wins ties);
   audit A7 checks held 0..f inclusive (stop wins ties, cancelling pending).
   Same-minute ties are rare (stops 83-582) so +2-21 stops, negligible monthly.
3. 1m DD peak: reported peak over 4h closes only, eq_min = prev*(1+min(0,path.min()));
   audit A11 peaks over the full minute path (upside creates higher peaks).
   Hence audit gate DD +0.27/+0.89pp; 4h DD matches. Worst-minute bar may shift
   by one 4h bar (e.g. m2 1m worst 2022-11-15 audit vs implied reported window).
4. Yearly windowing: reported yearly = idx in [anchor, anchor+365d); audit A12 =
   books searchsorted slices (2190 bars, one 28h gap in books). 2023/2025 gaps
   dominate the -0.7/-3.0pp last-year deltas; first-two-year nets within 0.06pp.
   Full monthly (eq_end^(1/60)) vs reported prod-yearly^(1/60) identical in theory.
5. Sleeve identical (ladder 2.5/3/3.5/4, TP L(1+s), SL L(1-2s), budget 1/6,
   rn = s*g*0.25/4/1.657): rungs within 5, rung TP/SL within 1.

## Look-ahead check

engine_user.py prepare/simulate plus v188_user_engine_sl_tp.py:
- Vol/sigma causal: sig4 = opens.pct_change().rolling(360,min120).std() at t;
  realized = 0.8*books[t-2]*ret[t]; vol rolling 360*sqrt(2190); s = min(0.25/vol,2).
  PASS (matches A2-A3).
- Governor reads eq[t-2]/max 540 ending t-2; target = 0.8*s*books[t]*g. PASS.
- Orders: limit from minute-0 1m open of T, live minutes 2..59 (2:60 slice strict),
  fill only on trade-through; unfilled expires; min-notional with must-flatten
  exception. Signal t fills in T = t+4h, never same bar. PASS.
- SL/TP levels from decision-known entry and sigma_d(t)*sqrt(6); held checked from
  minute 0 of T, new from fill minute; SL-first; flat rest of bar, pending cancelled.
  Entry update new/flip->fill, add->weighted, reduce->unchanged. PASS.
- Sleeve L from open(T) and sigma_4h(t); fills 16..238, exits strictly after fill;
  budget counts only taken with exit>f (past fills, no future highs). PASS.
- Funding only longs at settlement (T+4h hour 0/8/16), shorts zero; no carry. PASS.
- Selection uses yearly[:4] dev4 with DD<=20 and no losing year in first four;
  most-recent year reported only. PASS.
- No statistic from test/last year feeds back (books v154 frozen, thresholds fixed
  m = 2/3/4 pre-registered). PASS.

tests/test_engine_user.py: limit-fill+TP, gap-stop at open, unfilled expiry,
long funding — all pass (4 tests). Reviewed; arithmetic matches the gate cost model
(maker 0.0002, taker 0.00055, funding 0.0001 longs).

No forward use found in the worker or engine.

## Verdict

- Engineering REPRODUCED with documented deltas (monthly -0.04/-0.06pp, dev4
  -0.01/-0.03pp, gate DD +0.27/+0.89pp from peak definition, fills +2.4% from
  o1-vs-limit sizing and fill-wins vs stop-wins ties, yearly within 0.06pp except
  gap-windowed 2023/2025). Selection (m4), no-losing-year and DD pass/fail pattern
  identical. Look-ahead PASS (causal features, t+4h fills, first-four selection,
  correct fees/funding).
- Gate: all rows fail monthly >= 5% (rep 3.083/3.441/3.533, aud 3.042/3.383/3.486;
  last year rep 2.948/3.904/3.549, aud 2.777/3.738/3.379) while m3/m4 pass DD<=20
  (m2 fails both). Manifest correctly stays rejected / non-live_approved.
