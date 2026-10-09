# oc_mvrvmech REPORT — WHY does halving book longs (MVRV-z > 2) raise G2's return?

Method (PLAN pre-registered; frozen G2/M1, no new variants): FULL G2/M1 re-ran
bit-exact vs `oc_mvrvrobust/engine_runs.pkl` (eq AND eq_min equal on all 4
shifts, asserted in code), plus BOOKONLY (sleeve=False, as
`oc_bookattrib/run_bookonly.py`) and DIPONLY (books=0, sleeve=True) with
events/attrib/bars capture (`compute_mech.py` via heavy_slot, Pool(2);
`analyze_mech.py` for tables/tape/budgets; `tests/test_oc_mvrvmech.py` passes).
Cross-check: G2_book 5y 2.531 reproduces oc_bookattrib's book-only net
(2.531) to the digit. Gate costs: maker 0.0002, taker 0.00055, longs
0.0001/8h, win_start=5, 1m trade-through, stop-first.

## 1. Book-only / dip-only engine runs, 4 phases (Task 1)

Per-year reset R (%/mo) / DD (%):

| year | G2_book | M1_book | Dip_only |
|---|---|---|---|
| 2021-09-24 | 0.585 / 9.76 | 0.585 / 9.76 | 0.709 / 11.61 |
| 2022-09-24 | 1.992 / 10.59 | 2.056 / 9.93 | 0.761 / 10.60 |
| 2023-09-24 | 2.818 / 14.60 | 2.360 / 14.59 | 2.480 / 7.99 |
| 2024-09-24 | 3.854 / 9.42 | 3.900 / 9.43 | 3.380 / 3.46 |
| 2025-09-24 (labelled) | 3.438 / 10.24 | 3.438 / 10.24 | 0.578 / 7.69 |
| 5y mean / full-path DD | 2.531 / 18.96 | 2.461 / 18.97 | 1.575 / 11.61 |

**Isolated, the MVRV gate HURTS the book: M1_book 5y 2.461 < G2_book 2.531**
(-0.07 pp/mo; 2023 alone -0.458 pp). Yet M1_full 5y 5.881 > G2_full 5.41.
The gain is an interaction, not book timing.

Per-episode 4-phase-mean equity window returns (exact):

| ep | G2_full | M1_full | gap | G2_book | M1_book | book gap | Dip_only |
|---|---|---|---|---|---|---|---|
| E2 2023-11-02..2024-01-13 (BTC +22.6%) | 0.2272 | 0.3090 | +0.0818 | 0.0637 | 0.0790 | +0.0153 | 0.1113 |
| E3 2024-02-10..2024-04-10 (BTC +48.1%) | 0.3411 | 0.5821 | +0.2410 | 0.2776 | 0.1824 | -0.0952 | 0.1228 |
| E4 2024-11-12..2024-12-01 (BTC +10.6%) | 0.2984 | 0.3060 | +0.0076 | 0.1643 | 0.1442 | -0.0201 | 0.0625 |

Dip-only identity: one zero-book run serves both labels — the gate is a
provable no-op on all-zero books (`is_long` all-False, so no weight is ever
touched) and Dip_only mean governor is 0.999-1.0 in every episode. With no book
there is no coupling by construction. But the dip sleeve inside the FULL runs
is NOT the dip-only sleeve (fewer but much bigger rungs, bigger legs — see §3),
so the book↔dip coupling is real and is where the gain lives.

## 2. Book long trades inside E2/E3/E4, per coin, G2 vs M1 (Task 2)

Tape from BOOKONLY events (no dip events), paired entry→stop/tp/close per
asset; net = equity-fraction approx (gate fees; adverse long funding stays in
engine equity, not split per trade — engine window gaps in §1 are exact).
Sums over 4 shifts; entries attributed by entry time in window.

E3 (the big one): longs EARNED everywhere — G2 nets BTC +0.128, ETH +0.095,
SOL +0.142, BNB +0.168, XRP +0.010 (sum +0.544); M1 sum +0.419 on all-positive
coins. Halving profitable longs cost ~-0.095 of book window — (a) is dead.
E4 is an XRP story: G2 XRP +0.522 (31 longs: 15 stops + 16 TPs), M1 XRP +0.386
(27 longs: 9 stops + 12 TPs); halving the winners cost -0.020. E2: SOL carries
both (G2 +0.199 / 48 longs, M1 +0.189 / 40 longs); XRP loses both
(G2 -0.082, M1 -0.032 — smaller size also shrinks the loser, the gate's only
book-level merit here, worth +0.015 in E2's book gap).

Which trades differ and why: counts differ even though the signal is identical,
because halved tg crosses the hysteresis bands differently — E3 M1 issues 554
orders vs G2 455 (+22%) for 206 vs 169 fills; E4 236 vs 170 issues for 68 vs 63
fills (more min-notional skips/cancels = small churn cost). M1 exits relatively
more via signal closes, G2 more via stops (E2: M1 35 stops vs G2 67; M1 SOL 0
stops vs G2 13 — same rally, smaller size, tighter signal-loss exits). Mean
entry weight is NOT halved (E3 BTC 0.073 vs 0.098) because M1's higher governor
scales targets back up — the interaction already visible at order size.

## 3. Capital / budget utilisation in FULL runs (Task 2)

Per episode, 4-shift means (legs = linear per-bar attrib means; exact window
gaps in §1):

| ep | | mean_g | book gross | dip rungs | mean rung w | book leg | sleeve leg |
|---|---|---|---|---|---|---|---|
| E2 | G2 | 0.9234 | 0.422 | 1420 | 0.13951 | 0.0721 | 0.1515 |
| E2 | M1 | 0.9575 | 0.327 | 1369 | 0.16977 | 0.0830 | 0.2101 |
| E2 | DIP | 0.999 | 0.0 | 1471 | 0.08582 | 0.0 | 0.1169 |
| E3 | G2 | 0.7473 | 0.391 | 891 | 0.13024 | 0.1310 | 0.1502 |
| E3 | M1 | 0.9475 | 0.366 | 989 | 0.21303 | 0.1458 | 0.3179 |
| E3 | DIP | 1.000 | 0.0 | 1144 | 0.07222 | 0.0 | 0.1163 |
| E4 | G2 | 0.9965 | 0.485 | 520 | 0.14484 | 0.1516 | 0.1074 |
| E4 | M1 | 0.9948 | 0.372 | 513 | 0.16650 | 0.1358 | 0.1275 |
| E4 | DIP | 1.000 | 0.0 | 525 | 0.07117 | 0.0 | 0.0583 |

The named "spot cash + perp gross / leverage <= 95%" cap does NOT exist in this
engine path (inspected `engine_user.simulate`: only vol-target scale s,
drawdown governor g, dip risk budget 0.255, dip gross cap 2.0, min-notional,
1%-MMR liquidation check). liq=0 in all 20 runs; book gross peaks at 1.14 of
equity at 1x — no margin channel. The coupling runs through two shared knobs:

1. **Size (governor × vol scale).** M1's smaller book → lower realized vol →
   vol-scale s at cap 2.0 (E3 M1 s≈2.0 vs G2 ≈1.4) and shallower DD → higher g
   (E3 0.9475 vs 0.7473; E2 0.9575 vs 0.9234) → dip rungs +22%/+64%/+15% bigger.
   Per-shift E3 full gaps (+0.057/+0.135/+0.292/+0.481) all positive with book
   gaps all negative (-0.08..-0.12): the dip leg carries every phase path.
2. **Shutdown avoidance (E3 shift 3, the smoking gun).** G2's governor sat at 0
   for 46% of E3 bars (DD ≥ 20%; mean g 0.18, 100 rungs, window -0.019) while
   M1 stayed alive (g 0.79, 279 rungs, +0.462). Shift 3 alone is ~half the E3
   mean gap. (On shifts 0-2 M1 actually takes FEWER rungs — bigger size binds
   the risk budget sooner, as expected.)

## 4. Conclusion

**(b): the M1 gain is a book→dip risk interaction, mostly the shared drawdown
governor (plus vol-scale), not book timing and not an artefact.** Numbers:
book-only 5y M1 2.461 < G2 2.531; full-run sleeve-leg gaps (per-shift-mean
linear) +0.059/+0.168/+0.020 vs exact full gaps +0.082/+0.241/+0.008, while
book legs are ~0/±0.016. (a) rejected — longs were profitable in all three
windows (E3 G2 tape +0.544, E4 XRP +0.522; book-only windows all positive), so
there was no SL/TP whipsaw loss for the gate to avoid. (c) rejected — FULL
bit-exact vs the oc_mvrvrobust cache on all shifts, G2_book reproduces
oc_bookattrib to the digit, identical harness/fills, liq=0; no reproduction
needed because no artefact was found. Honest caveats: E3 leans on one phase
path's shutdown (shift-3 gap +0.48 of the +0.24 mean); a per-sleeve governor
would erase most of this (untested — no new variants per assignment); M1's own
book leg is worse, so MVRV-z has no timing skill here — it is a size damper
whose value flows through the governor. Live it counts (same engine would run
it), but it is fragile to governor design and rally path, not a timing edge.

Leakage / execution statement: gate code is the verbatim frozen-M1 copy
(as-of D+1 02:00, searchsorted right-1; truncation/boundary tests pass); no
labels fitted (realised 1m path); no fits (threshold/window/mult frozen from
oc_mvrvrobust); fills win_start=5 + 1m trade-through + stop-first with G2/M1
bit-exact re-runs. Post-hoc log: analysis-only addition after outcomes
(yearly/pershift/gov-shutdown sections from the same frozen runs; no variant,
threshold or definition changed).

## Vietnamese verdict (3 lines)

- M1 thắng không phải nhờ bắt đỉnh/sửa whipsaw: book riêng của M1 thua G2 (5 năm 2,46 so với 2,53; E3 thua 9,5 điểm) vì long trong E2/E3/E4 đều lãi (E3 tape G2 +0,54, XRP E4 +0,52) nên bóp một nửa long chỉ làm mất lãi — toàn bộ chênh lệch full (+0,08/+0,24/+0,01) nằm ở chân dip nhờ governor chung và vol-scale (rung to hơn 22/64/15%, E3-shift3 G2 tắt governor 46% số bar còn M1 vẫn chạy).
- Điểm trừ phải ghi rõ: E3 dựa một nửa vào đúng một phase-path bị shutdown, không có margin-cap nào bị chạm (liq = 0, gross ≤ 1,14 ở 1x) nên đây là tương tác governor-dùng-chung chứ không phải MVRV biết chọn thời điểm — governor tính riêng từng sleeve (chưa test) có thể xóa gần hết hiệu quả này.
- Kết luận: hiệu quả là thật trong engine (b), đáng giữ cho bản live vì cùng engine sẽ chạy y vậy, nhưng đừng ghi công timing cho MVRV-z và đừng tune thêm quanh nó — muốn bền thì đăng ký hướng mới (governor riêng, paper-log prospective) thay vì chỉnh gate trên các năm này.
