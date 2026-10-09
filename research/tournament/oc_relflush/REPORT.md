# oc_relflush REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup

Inside a multi-coin flush, size the coin that overshoots the others more
(bot_only dip screen). Exact oc_placebo_dip replica: D0 rung outcomes (TP 1sg,
close5 stop 4sg, 8sg backstop, timeout at next 4h open; maker 0.0002 /
taker 0.00055; v293 settle funding longs pay 0.0001 on settling timeouts) with
B1 sizes w = 1/(1+n_fill), majors x R2 depths 2.5/3/3.5/4/5, live offsets
16..238 strict trade-through, on all four clock phases (4h grid from
2020-08-01 00:00 UTC + 0/1/2/3h), bars open in [2021-09-24, 2026-09-24).
Per fill of coin i at minute f (n_fill >= 1): d_x = -log(P_x(f-1)/O_x)/sigma_x
(P = 1m close at f-1, O = bar open same clock, sigma = ladder sigma);
F = {other majors d_x >= 2.5}; rel = d_i - mean(F); n_fill = 0 keeps w = 1.
R1: x1.5 if rel>+0.5, x0.75 if rel<-0.5, else x1. R2 sign control (mirrored).
R3: xclip(1+0.25*rel, 0.6, 1.4). Budget/caps as replica (no re-normalisation);
same fills, same y1.0, same exit days in every arm (size-only change).
All 5 years are research data (established gate below is calibrated on all 5y
incl. the most recent year — labelled).

## Replica fidelity (base, B1 w*y)

Phase-0 fills/coin 1067/1126/952/1179/1174 = oc_dipexit exactly; phase-0 raw
sums 2.388/0.183/3.810/2.579/0.712 = oc_stoptf D0 to 1e-3; 4-phase-mean base
sums 0.911/0.833/2.100/3.197/0.677 and DDs 0.856/0.951/0.800/0.355/0.607 =
oc_placebo_dip base exactly (5y base 7.718). Ledger 22312 fills, checksum
1f6f157a26a39e61. The y1.0-only pairing differs nowhere from the placebo
3-leg pairing on this grid.

## Per-year 4-phase means (w*y units; win equal-weight, identical membership)

| year | S base / R1 / R2 / R3 | DD base / R1 / R2 / R3 | n | win |
|---|---|---|---|---|
| 21-22 | 0.911 / 0.933 / 0.919 / 0.933 | 0.856/0.858/0.922/0.833 | 1043 | .660 |
| 22-23 | 0.833 / 0.860 / 0.790 / 0.868 | 0.951/0.882/1.125/0.860 | 1015 | .699 |
| 23-24 | 2.100 / 2.061 / 2.139 / 2.056 | 0.800/0.787/0.842/0.780 | 1338 | .748 |
| 24-25 | 3.197 / 3.125 / 3.418 / 3.079 | 0.355/0.360/0.364/0.354 | 990 | .734 |
| 25-26 | 0.677 / 0.631 / 0.742 / 0.630 | 0.607/0.607/0.658/0.580 | 1193 | .661 |

dS vs base per year (R1): +0.022/+0.028/-0.039/-0.072/-0.047.
dS (R2): +0.008/-0.043/+0.040/+0.221/+0.065. dS (R3): +0.022/+0.035/-0.044/-0.119/-0.047.
Full pooled sums: base 30.873 / R1 30.439 / R2 32.036 / R3 30.264;
full DD: 3.127 / 2.795 / 3.916 / 2.751.

## Decision — established 5y dip-screen gate (labelled: calibrated on all 5y incl. 2025-09-24..2026-09-24)

PROMISING iff sum>=base in >=4/5 AND DD<=base+0.01 in >=4/5 AND dSum5y>=+0.273.

| leg | R1 | R2 (control) | R3 |
|---|---|---|---|
| Sbar>=base | 2/5 (21,22) NO | 4/5 (21,23,24,25) YES | 2/5 (21,22) NO |
| DDbar<=base+0.01 | 5/5 YES | 1/5 (only 24) NO | 5/5 YES |
| dSum5y>=+0.273 | -0.109 (7.610 vs 7.718) NO | +0.291 (8.009 vs 7.718) YES | -0.152 (7.566 vs 7.718) NO |
| PROMISING | NO | NO | NO |

## Protocol view — dev4 only (Y0..Y3, >=3/4; choice among R1/R3; R2 must mirror R1)

| leg (dev4) | R1 | R2 | R3 |
|---|---|---|---|
| sum>=base | 2/4 NO | 3/4 YES | 2/4 NO |
| DD ok | 4/4 YES | 1/4 NO | 4/4 YES |
| dev4 dSum | -0.062 | +0.226 | -0.105 |

Choice on dev4 (R1 vs R3): R1 (-0.062) beats R3 (-0.105) with the same 2/4
legs, so R1 is the dev4 pick — but it still loses to base on dev4 sums, so no
candidate is chosen. R2 mirrors R1 on sums in 4/5 years (opposite sign in
22/23/24/25, same sign only in 21) yet its sum edge is tail-heavy: it fails
the DD leg 4/5 years and deepens full pooled DD 3.13 -> 3.92. The mechanism is
therefore NOT believed in the hypothesised direction — if anything the data
favour the laggard (rel<0), at an unacceptable tail cost.

## Descriptives (5y; n_fill>=1 fills only for rel)

- Share of fills with n_fill>=1: 56.1% overall (61.9/51.0/52.1/54.2/61.3% per
  year 21..25); n = 12516 flushed fills of 22312.
- rel distribution (finite: 12516/12516): hi(>+0.5) 10.3%, mid 43.3%,
  lo(<-0.5) 46.4%; p5/p25/p50/p75/p95 = -2.20/-0.95/-0.44/+0.03/+0.83.
  Per-year hi/mid/lo: 21: 12/45/43; 22: 8/36/57; 23: 10/37/53; 24: 10/46/43;
  25: 11/51/39. The filled coin is typically the laggard (median -0.44).
- Mean y1.0 by pooled-rel tercile (cuts -0.752/-0.151), per year:
  21: lo +0.072% / mid +0.068% / hi +0.136% (hi best);
  22: lo -0.239% / mid +0.321% / hi +0.062% (mid best, lo negative);
  23: lo +0.067% / mid +0.031% / hi -0.166% (lo best, hi negative);
  24: lo +0.607% / mid +0.477% / hi +0.507% (lo best);
  25: lo -0.028% / mid +0.132% / hi +0.007% (mid best).
  No stable overshoot premium; the hi-tercile wins only in 2021.
- Log-vs-simple detector sliver: n_fill (simple <=) vs |F| (log >=2.5)
  mismatch on 1163/22312 fills (5.2%); exp(-2.5sg) sits ~3 bps above
  (1-2.5sg) at sg~0.01, so borderline coins flip F without flipping n.
  Base weights always use n_fill (authoritative); rel means always use F.

## Notes (leakage, costs, repro)

- Feature timing: d_x uses only the 1m close at minute f-1 (C[base+f-1]), the
  bar open at T, and sigma from trailing 360 4h opens ending at T-1
  (shift(1)); exits use only minutes f+1..239 plus next-bar open. Checked by
  test_fill_and_n_use_only_minute_f_minus_1, test_sigma_excludes_current_bar,
  and code review (no future indexing). bot_only by construction.
- Label windows: y1.0 is the post-fill D0 outcome, never a feature.
- Fit windows: nothing fitted — thresholds +-0.5, multipliers 1.5/0.75, slope
  0.25, clip [0.6,1.4] are PLAN-fixed; tercile cuts are descriptive only
  (pooled, never used for sizing). 7-day embargo N/A (no fit).
- Fill timing: live 16..238 strict low<lv (first-5-minutes rule satisfied a
  fortiori); stop-first race; gate fees/funding as replica.
- Costs are the gate model (maker 0.0002, taker 0.00055, longs pay 0.0001 on
  settling timeouts); no slippage term per AGENTS.md.
- No post-hoc change to hypothesis, thresholds, multipliers, or decision rule.
  One process, peak RAM ~float32 1m O/C + one-coin H/L, via heavy_slot.
- Repro: research/tournament/oc_relflush/{PLAN.md,core.py,compute_relflush.py,
  results.json,panel.parquet} + tests/test_oc_relflush.py (13 tests pass).

## Verdict

NOT PROMISING — sizing the flush overshoot (R1) beats B1 in only 2/5 years
with 5y delta -0.109 (< +0.273 gate); the smooth tilt (R3) is the same 2/5
with -0.152; the sign control (R2) wins sums 4/5 with +0.291 but fails
drawdown 4/5 years (full DD 3.13 -> 3.92), so the hypothesised direction is
wrong and its opposite is tail-heavy. No engine follow-up.

Dòng 1: REJECT — cả R1 (2/5 năm, dSum -0,109) và R3 (2/5 năm, dSum -0,152) đều thua base, R2 thắng 4/5 năm (+0,291) nhưng vỡ DD 4/5 năm nên không tin được cơ chế overshoot.
Dòng 2: Không đưa biến thể nào lên engine 4-phase và không cần log prospective cho hướng relflush này.
Dòng 3: Đóng hướng size-the-overshoot; nếu mở lại phải đăng ký trước đặc trưng khác và kiểm chứng độc lập từ đầu.
