# oc_partialtp REPORT — Stop-funded partial TP (IDEAS6 #2)

PLAN.md frozen BEFORE any outcome; implemented EXACTLY as pre-registered there.
Replica = oc_dipexit/oc_placebo_dip-exact D0 (TP 1.0sg, sl 4sg close5, bl 8sg, timeout next-bar
open; maker 0.0002 / taker 0.00055; v293 settle funding longs-pay-0.0001) + B1 sizes w=1/(1+n);
4 clock phases (4h grid 2020-08-01 +0/1/2/3h); majors x R2 rungs 2.5..5.0; live 16..238 STRICT
trade-through; bars open [2021-09-24, 2026-09-24). Paired fills kept iff BASE+V1+V2 all finite:
n = 22,312 (drop_nf = 0; split_any = 17,329 = 77.7% of fills touch the early half).
Repro: `research/tournament/oc_partialtp/{PLAN.md,partialtp.py,run.py,results.json,tmp/ledger.npz}`
+ `tests/test_oc_partialtp.py`. One process, one-coin H/L at a time, float32 1m, via heavy_slot
(~55 s compute after slot grant; log `tmp/run.log`).

## Fidelity (disclosed, not a gate)

- Phase-0 raw sums got [2.388, 0.183, 3.810, 2.579, 0.712] vs oc_dipexit ref
  [2.388, 0.183, 3.810, 2.579, 0.712] — exact to 3 digits.
- Base 4-phase-mean sums got [0.911, 0.833, 2.100, 3.197, 0.677] vs oc_placebo_dip
  [0.911, 0.833, 2.100, 3.197, 0.677] — exact to 3 digits.

## Per-year 4-phase-mean sums S (w*y units) and DD

| year | BASE S / DD | V1 (half@0.5sg) S / DD | V2 (half@0.75sg) S / DD |
|---|---|---|---|
| 2021-09-24 | 0.911 / 0.856 | 0.766 / 0.762 | 0.820 / 0.832 |
| 2022-09-24 | 0.833 / 0.951 | 0.487 / 0.931 | 0.719 / 0.947 |
| 2023-09-24 | 2.100 / 0.800 | 1.404 / 0.752 | 1.778 / 0.777 |
| 2024-09-24 | 3.197 / 0.355 | 2.637 / 0.302 | 2.934 / 0.333 |
| 2025-09-24 | 0.677 / 0.607 | 0.565 / 0.524 | 0.608 / 0.582 |
| sum5y | 7.718 | 5.858 | 6.859 |

## Gate (BINDING: full PROMISING legs + dSum5y >= +0.273)

| variant | years S>=base | years DD ok | dSum5y | dDDmean | gate |
|---|---|---|---|---|---|
| V1 | 0/5 | 5/5 | -1.860 | -0.060 | FAIL |
| V2 | 0/5 | 5/5 | -0.859 | -0.019 | FAIL |

Both variants lose EVERY year on sums (0/5) by a wide margin (dSum5y -1.86 / -0.86 vs required
+0.273). DD legs pass 5/5 trivially (smaller positions after the bank), but ALL THREE
conditions are required. **No engine run** per the frozen PLAN (oc_crashgate/oc_rungquality path).
Negative result, valid.

## Diagnostics (why it fails)

- Split share V1 = 77.7% (part_tp 12,231 / part_time 4,845 / part_stop 191 / part_backstop 62;
  whole time 4,315 / stop 462 / backstop 206). The early half triggers on most fills.
- Win rate UP as predicted: base 0.702 -> V1 0.744 / V2 0.725. But mean bps DOWN:
  base +17.87 -> V1 +12.98 / V2 +15.68. Banking half at 0.5/0.75sg cuts the runner upside that
  carries the sleeve (fast full TPs are the edge: oc_ladderfill TP<=15min = 93% of edge);
  the stop-funding saving (remainder pays 0.5*FUND at settle timeouts) is second-order.
- Consistent with oc_dipexit E1 (split 0.5+1.5 FULL halves: 0/5 years, NOT PROMISING) — splitting
  the proven 1.0sg TP loses on this ladder in every year.

## Fees / funding (gate costs inside every leg)

- Fill maker 0.0002 + TP/partial maker 0.0002 (2*maker per maker half); stop/backstop/timeout
  taker 0.00055; settle funding 0.0001 on longs held through (T+4h).hour in (0,8,16) — split
  fills pay it on the remainder half only (0.5*FUND total, disclosed). No separate dollar split
  is reported because the replica scores in w*y units, not account equity; every leg is net of
  its exact fee/funding. No engine equity/DD exists by design (gate not passed).

## Leakage checklist

- Feature timing: sigma from 4h opens of bars ending at j-1 (shift(1)); n from 1m closes at
  T+m-1; Pp/tp/sl/bl from px (= lv, the resting fill price) and sg only. Truncation-tested
  (`test_truncation_later_minutes_cannot_change_outcome`, pre-fill scramble, NaN tests).
- Label windows: no labels fit; exits are mechanical 1m races.
- Fit windows: no fits/thresholds anywhere; 0.5/0.75 frozen ex-ante in PLAN.md; no test-year
  statistic feeds any choice. CLOSED FULL-exit rows (oc_tpbyn/oc_deeptp/oc_beartp/oc_dipexit)
  read first; this is DIP HALF-early + 1.0sg runner (v365 partial was BOOK side).
- Fill timing: entries live 16..238 STRICT low<lv (minute-5 ban inherited); partial live f+1..239
  STRICT high>Pp, runner STRICT high>tp, no re-peg; same-minute stop+partial -> stop,
  backstop+partial -> backstop (stop-first); same-minute partial+runner -> both maker.

## Verdict

VERDICT: REJECT both V1 and V2 — clean gate failure (0/5 sum years, dSum5y deeply negative);
no 4-phase engine run. The direction is closed for this mechanism: do not re-test earlier
partial levels on this ladder (a later/closer Pp only converges to BASE from below).

## Ket luan tieng Viet (3 dong)

- y tuong partial TP (ban non nua duong, giu runner 1.0sg) THUA o ca 5 nam: V1 dSum -1.86, V2 -0.86 (can +0.273).
- Win rate co tang (70% -> 72-74%) nhung bien do trung binh giam (17.9 -> 13.0/15.7 bps): cat non som lam mat phan runner tao edge.
- Ket luan: REJECT ca 2 bien the, khong chay engine, dong huong partial-TP tren ladder nay.
