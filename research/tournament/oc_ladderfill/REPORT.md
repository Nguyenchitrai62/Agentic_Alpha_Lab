# oc_ladderfill REPORT — dip-rung fill timing and fast-TP edge share (R2B1D17BF)

DIAGNOSTIC (no rule, no verdict). Source: `research/tournament/oc_kpi/
events_s{0..3}.parquet` rung_fill -> rung_tp/sl/timeout pairs, FIFO per
(shift, symbol), pooled over shifts s=0..3 (n = 21,389 paired rungs, 0 unpaired
exits, 0 left open; counts match oc_kpi's 21,389 and win 0.6869 vs 0.687).
Fill minute f uses the rung's own shifted 4h grid (bars open at hours = s mod
4); f spans exactly 16..238 on every shift (0 outsiders). dt = exit-fill in
min (max 224 = 240-16, timeout at next 4h open). P&L = engine net `ret` per
rung (fees in); bps = ret*1e4; edge shares use sum(weight*ret) (main) and
sum(ret) (secondary). Repro: `research/tournament/oc_ladderfill/{PLAN.md,
analyze_ladderfill.py,results.json}`; test `tests/test_oc_ladderfill.py`.
All five years are research data; findings need prospective validation.

## A. Fill-minute distribution (f, min from the rung's bar open)

| group | n (share) | p25 / median / p75 |
|---|---|---|
| all | 21389 | 86 / 142 / 191 |
| depth 2.5 | 8649 (0.404) | 84 / 139 / 189 |
| depth 3.0 | 5437 (0.254) | 87 / 143 / 192 |
| depth 3.5 | 3592 (0.168) | 88 / 143 / 192 |
| depth 4.0 | 2454 (0.115) | 90 / 145 / 193 |
| depth 5.0 | 1257 (0.059) | 87 / 144 / 192 |
| BTC | 4206 (0.197) | 89 / 145 / 193 |
| ETH | 4397 (0.206) | 88 / 142 / 190 |
| SOL | 3805 (0.178) | 90 / 143 / 192 |
| BNB | 4558 (0.213) | 86 / 141 / 190 |
| XRP | 4423 (0.207) | 81 / 138 / 189 |

Bucket histogram (all): 16-60: 3047 (14.2%), 61-120: 5355 (25.0%),
121-180: 6286 (29.4%), 181-238: 6701 (31.3%). Fills skew late; depth/coin
medians differ by <= 7 min — no depth or coin fills in a distinct window.

## B. Time to exit by exit kind (dt, minutes)

| group | TP median (p25/p75, n) | SL median (n) | timeout median (n) |
|---|---|---|---|
| all | 14 (4/36, 10761) | 15 (924) | 60 (28/109, 9704) |
| depth 2.5 | 13 (4/33, 5368) | 17 (137) | 55 (3144) |
| depth 3.0 | 15 (5/37, 2752) | 17 (189) | 59 (2496) |
| depth 3.5 | 15 (4/42, 1507) | 16 (208) | 64 (1877) |
| depth 4.0 | 15 (4/42, 830) | 14 (207) | 69 (1417) |
| depth 5.0 | 20 (5/52, 304) | 13 (183) | 69 (770) |
| BTC | 16 (1981) | 20 (120) | 62 (2105) |
| ETH | 14 (2056) | 17 (149) | 64 (2192) |
| SOL | 13 (2003) | 14 (158) | 56 (1644) |
| BNB | 19 (2230) | 18 (247) | 60 (2081) |
| XRP | 12 (2491) | 11 (250) | 57 (1682) |

Exit mix overall: TP 10761 (50.3%), timeout 9704 (45.4%), SL 924 (4.3%).
TP is fast (median 14 min, p25 4 min); deeper rungs TP slightly slower
(median 13 -> 20 min from 2.5 to 5.0) and time out more often.

## C. P&L by fill-minute bucket (pooled; ret net, bps)

| bucket | n | win | mean bps | sum(ret) | sum(w*ret) | edge share (w / eq) |
|---|---|---|---|---|---|---|
| 16-60 | 3047 | 0.822 | +36.58 | +11.15 | +2.511 | 24.9% / 29.3% |
| 61-120 | 5355 | 0.756 | +31.57 | +16.91 | +3.428 | 34.0% / 44.5% |
| 121-180 | 6286 | 0.690 | +19.93 | +12.53 | +2.944 | 29.2% / 33.0% |
| 181-238 | 6701 | 0.567 | -3.86 | -2.59 | +1.191 | 11.8% / -6.8% |

Win rate and mean fall monotonically with f. The late bucket (31% of fills)
is negative equal-weighted (-3.86 bps mean, win 0.567) but still positive
capital-weighted (+11.8% of edge) — composition effect: shallow profitable
rungs carry larger weights (per-depth table: late-bucket mean bps =
2.5:+49.8, 3.0:+12.9, 3.5:-39.0, 4.0:-77.7, 5.0:-166.8). Total dip edge
sum(w*ret) = +10.075, sum(ret) = +37.989, overall mean +17.76 bps, win 0.687.

## D. Fast-TP P&L (TP exits with dt <= h; nested)

| set | n | % of rungs / % of TP | mean bps | sum(w*ret) | share of dip edge (w) | share of TP edge (w) |
|---|---|---|---|---|---|---|
| TP <= 5 min | 3140 | 14.7% / 29.2% | +136.9 | +5.370 | 53.3% | 29.4% |
| TP <= 15 min | 5615 | 26.3% / 52.2% | +139.6 | +9.401 | 93.3% | 51.5% |
| TP <= 60 min | 9405 | 44.0% / 87.4% | +141.0 | +15.679 | 155.6% | 86.0% |
| all TP | 10761 | 50.3% / 100% | +141.9 | +18.238 | 181.0% | 100% |
| TP > 60 min | 1356 | 6.3% / 12.6% | +148.1 | +2.559 | 25.4% | 14.0% |

(Shares > 100% because timeouts+SLs are a net drag: total edge +10.075 < TP
edge +18.238.) The first 15 minutes after a fill decide the sleeve: 26% of
rungs (≈half of all TPs) deliver 93% of the capital-weighted dip edge; TPs
within 5 min alone (15% of rungs) deliver 53%.

## E. Paper bots (`artifacts/bot/paper_d17bf/`, 2026-10-05 13:39 -> 17:36 UTC)

actions.jsonl: bear_state 3, place 125, cancel 125, stale_plan ~195 (log still
growing; counts at analysis time) — zero fill ops of any kind; exchange.json:
execs 0, equity flat 5000.0 (5 hourly points); state.json holds resting
dip-order links only. => Zero dip/book fills so far; research-engine
comparison is counts-only (too few to compare rates or minutes).

## One-line summary

Dip fills skew late (median minute 142, 31% in 181-238 where equal-weight mean
turns -3.9 bps), TP exits are fast (median 14 min), and the edge is
front-loaded: TPs within 15 min of the fill (26% of rungs) carry 93% of the
capital-weighted dip edge; the paper bot has zero fills so far (counts only).

## Caveats / post-hoc log

1. PLAN v1 defined f on the unshifted 00/04/... grid; first run gave 0..239
   with 1564 outsiders on s=1..3. Fixed to the per-shift grid (bars open at
   hours = s mod 4) before writing this report; re-run gives exactly 16..238
   everywhere. Grid-independent numbers (n, win, mean) unchanged.
2. Pairing is FIFO per (shift, symbol) copied from oc_kpi; cross-symbol
   mis-pairing is impossible by construction (exits carry no rung id).
3. Equal- vs capital-weighted shares disagree in the late bucket (composition,
   §C) — sizing conclusions must use the weighted column.
4. Paper log covers ~4h with no fills; §E will change as the bot runs.
