# oc_spotlongs REPORT: book longs on spot-margin instead of perp (IDEAS10 #3)

Idea: gate funding taxes every long 0.01%/8h; oc_bookfunding CUT longs when
crowded and lost 5y -8.8% (hot funding marks strength). Routing longs to spot
keeps the exposure while paying ~0 funding. V1 = all book longs spot (borrow
APR 10%, stress 15%); V2 = spot only when the coin's trailing-7d avg settled
funding exceeds its pre-anchor median (per coin, [2020-01-01, A-7d)); shorts
stay perp; dip sleeve untouched (perp). Mechanism = oc_c2bybit base pipe
(v321, corr-aware 1/(1+n)*1.7, bear books, budget 0.26*1*1.7, G=2.0,
win_start=5, gate costs) through the spot-patched simulate (spot_patch.py:
verbatim engine_user + P0-P4, asserted; V0 = bit-identical gate).

## Reproduction gate: PASS

V0 dev years 0..3 == v421 R2B1D17BFG2 to the digit
([2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27]); V1 last-stage run
matches the dev run on years 0..3 bit-exact. All engine work via heavy_slot,
one job at a time, heartbeat 600 s, logs under tmp/.

## Per-year %/mo (geometric, reset metric) / DD — dev 2021-2024

| row | 21-22 | 22-23 | 23-24 | 24-25 | dev4 mean / WORST | dev DDmax |
|---|---|---|---|---|---|---|
| REF (stored v421) | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 5.601 / 2.588 | 16.91 |
| V0 gate | same | same | same | same | 5.601 / 2.588 | 16.91 |
| V1 all-spot APR10 | 2.664 / 10.58 | 3.515 / 16.68 | 6.401 / 15.81 | 11.055 / 8.26 | 5.859 / 2.664 | 16.68 |
| V2 gated APR10 | 2.594 / 10.86 | 3.365 / 16.97 | 6.140 / 15.82 | 10.875 / 8.26 | 5.694 / 2.594 | 16.97 |
| V1_CTRL (same fills + funding back, no borrow) | 2.586 / 10.86 | 3.285 / 17.17 | 6.165 / 15.81 | 10.669 / 8.27 | 5.629 / 2.586 | 17.17 |
| V1_APR15 (same fills, borrow x1.5) | 2.664 / 10.58 | 3.514 / 16.68 | 6.400 / 15.81 | 11.051 / 8.26 | 5.857 / 2.664 | 16.68 |

Dev4 robust pick (DD<=20, no losing year, prefer mean>=5, highest WORST,
ties mean): both eligible, both mean>=5 → highest WORST → **V1**
(5.859 / 2.664 vs V2 5.694 / 2.594). Funding saved (fraction-of-equity sum
over 4 shifts, 4y): V1 0.4118 vs V2 0.1977 (gated routes ~half the funding);
borrow paid: V1 0.0056, V2 0.0033 (book long leg almost never exceeds equity,
so borrow is ~zero and APR15-APR10 = -0.002 pp/mo). Net funding save V1-CTRL
= +0.230 pp/mo dev4 (+0.228 on 5y). CTRL-V0 residue +0.028 dev4 (+0.023 on 5y)
is the overlay second order (governor/min-notional feedback; fills differ by
~5/900 trades).

## Frozen finalist V1, scored ONCE on the post-release year + 5y (REF = stored row, labelled)

| row | 21-22 | 22-23 | 23-24 | 24-25 | Y4 25-26 (once) | 5y mean / WORST | no losing | full-path DD |
|---|---|---|---|---|---|---|---|---|
| REF stored | 2.588 | 3.282 | 6.045 | 10.677 | 4.648 / 12.90 | 5.410 / 2.588 | yes | 16.82 |
| V1_full | 2.664 | 3.515 | 6.401 | 11.055 | 4.876 / 12.76 | 5.661 / 2.664 | yes | 16.62 |
| V1_CTRL_full | 2.586 | 3.285 | 6.165 | 10.669 | 4.651 / 12.91 | 5.433 / 2.586 | yes | 17.12 |

Gate: (a) 5y 5.661 >= 5 PASS; (b) most recent year 4.876 >= 5 FAIL (-0.124);
(c) no losing year PASS; DD 16.68 <= 20 PASS. **Fails the gate on leg (b).**

## Bybit-price row S5, dev window, pick only (2021 = short window from 2021-11-15, labelled)

| row | 21-22* | 22-23 | 23-24 | 24-25 | dev4 mean / WORST | DDmax |
|---|---|---|---|---|---|---|
| REF_S5 (oc_c2bybit, read-only) | 2.129 | 2.735 | 4.932 | 10.377 | 4.994 / 2.129 | 18.11 |
| V1_S5 | 2.191 | 2.933 | 5.139 | 10.776 | 5.207 / 2.191 | 18.05 |

Gap V1-REF preserved on the unseen price path: +0.258 Binance dev4,
+0.213 Bybit dev4 (+0.228 Y4, +0.251 5y).

## Win rates (pooled 4 shifts; spot keeps fills, costs only)

V1_full book_win / rung_win / all_win per year:
21-22 0.503/0.638/0.613 (926/4077), 22-23 0.514/0.689/0.658 (860/3930),
23-24 0.525/0.732/0.698 (976/4979), 24-25 0.510/0.720/0.671 (1162/3857),
Y4 0.537/0.648/0.627 (1096/4671) — book fills differ from REF by ~5/900
(min-notional/governor second order from the higher equity path).

## Leakage checklist (how each was checked)

- Feature timing: books known at close of T, held [T,T+1); F7 uses only
  settlements with c < T (millisecond-exact, searchsorted side='left'; a
  settlement stamped exactly at T is excluded); route uses only (coin,
  holding-bar T) F7 vs frozen med_k. Truncation test in pytest recomputes
  F7/med from a truncated panel — identical on the kept prefix.
- Label windows: no label fit anywhere; the engine consumes the realised 1m
  path only.
- Fit windows: med_k per (anchor, coin) from bar times in [2020-01-01, A_k-7d)
  only (7-day embargo); year y uses anchor-y medians on all four shifts; borrow
  APR fixed ex-ante (10/15% grid, no fit); no test-year statistic feeds any
  choice. `tmp/funding_meds.json` frozen before the engine ran.
- Fill timing: win_start=5 asserted (no fill minutes 0-4); limits fill only on
  1m trade-through strictly through the price; stop-first inherited from the
  audited engine (untouched code path); spot-perp fill basis 0 is a labelled
  assumption (same 1m cube, no close-sample); SL market taker / TP limit maker
  attached as now.
- Contamination: dev years were available when IDEAS10 was written (post-hoc
  direction); Y4 was scored once for the frozen pick only; S5 is an unseen
  price path on the same years (diagnostic, never a selection input).

## Post-hoc log

- 2026-10-08, before outcomes: PLAN frozen (V0/V1/V2 + CTRL/APR15 overlays + S5).
- 2026-10-08, after dev outcomes, before writing REPORT: fixed two analyze-only
  bugs, no engine rerun, original rows kept: (1) APR15 overlay deducted 0.5x
  instead of charging 1.5x borrow (sign error, caught by APR15>APR10 absurdity);
  (2) wins all-zero from `y in wins-list` membership test (engine data was
  correct; rescored from the same caches).

## Verdict

NOT ADOPTED: V1 adds +0.23-0.26 pp/mo with DD flat-to-better (16.6-16.7 vs
16.8-16.9) and the edge survives Bybit prices (+0.21), but the scored-once
most recent year is 4.876 < 5 so the gate fails on leg (b); borrow is
immaterial (book leverage ~never binds) and V2's gate keeps only half the save.
Needs prospective paper evidence before any real money; do not rerun Y4.

## Vietnamese verdict (3 lines)

- KHÔNG deploy: V1 5 năm 5.661%/tháng, DD 16.68, không năm lỗ, nhưng năm mới nhất
  4.876 < 5 nên rớt gate ở nhánh (b) — dù hơn REF (+0.228) và Bybit xác nhận (+0.213).
- Vay USDT không đáng kể (APR15-APR10 chỉ -0.002) vì book hầu như không bao giờ
  vượt vốn; V2 giữ lại có một nửa khoản tiết kiệm funding nên thua V1.
- Cần log paper prospective trước khi xem xét lại; cấm dùng năm mới nhất để chọn
  tiếp (đã ghi điểm một lần cho V1).
