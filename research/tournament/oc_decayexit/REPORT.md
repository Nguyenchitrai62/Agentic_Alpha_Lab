# oc_decayexit REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS8 #6 (rank 6): signal-decay exit / asymmetric hold — remember entry |w0|;
exit (limit, maker) when |w| < frac*|w0|, V1 frac 0.3, V2 frac 0.5; sign-flip
tighten+close kept; winners ride to flip (no clock cap); SL/TP unchanged,
minute-5 ban kept. HOW a position ends (signal death) not WHEN (oc_bookholdcap
fixed 42-bar cap) or at which price bank (oc_bookexit +1.0 ATR HGB bank).
CLOSED `oc_bookholdcap` (NOT PROMISING 2/5 + 2/5) / `oc_bookexit` (win rate up,
P&L collapse) read first; this is a FROZEN FRACTION of entry signal, no model,
no bar count, no price bank.

STATUS: DONE. G2 reproduced to the digit first (5.41 / 16.91 / 16.82, dev years
+ Y4 exact). 4-phase engine dev (REF+V1+V2+C_V1+C_V2) + scored-once last year
(REF+V2 only, the dev4 robust pick). MARGINAL result: V2 beats REF by +0.006pp
dev4 mean / +0.004 WORST / +0.08 scored-once Y4 with +0.13 DD, but trails its
exposure-matched control by -0.14pp with worse DD — an exposure story, not timing
alpha. Effect is ~1% of the 4-8 bps round-trip bound. Direction closed in this form.

## G2 reproduction (binding gate, passed)

REF (unpatched policy, same books) reproduces v421 R2B1D17BFG2 to the digit, dev +
last: R/DD per year [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] +
Y4 (4.648/12.90), 5y 5.410, W 2.588, max yearly DD 16.91, full-path DD 16.82.
No overlay; overlay path not needed (in-position policy mechanism).

## Per-year table (4-phase reset %/mo geometric, max yearly DD; Y4 scored ONCE for the dev4 pick + REF only, labelled)

| year | REF R / DD | V1 (0.3) R / DD (diff) | V2 (0.5) R / DD (diff) | C (exposure-matched) R / DD |
|---|---|---|---|---|
| 2021 dev | 2.588 / 10.86 | 2.588 / 10.86 (+0.000) | 2.592 / 10.79 (+0.004) | 2.404 / 10.77 |
| 2022 dev | 3.282 / 16.91 | 3.193 / 17.19 (-0.089) | 3.308 / 17.04 (+0.026) | 3.135 / 16.86 |
| 2023 dev | 6.045 / 15.81 | 6.060 / 15.81 (+0.015) | 5.892 / 15.81 (-0.153) | 6.908 / 15.92 |
| 2024 dev | 10.677 / 8.27 | 10.684 / 8.27 (+0.007) | 10.832 / 8.27 (+0.155) | 10.766 / 9.01 |
| 2025-09-24..2026-09-23 scored-once | 4.648 / 12.90 | — (not run; discipline) | 4.728 / 12.02 (+0.080) | — (not run; diagnostic dev only) |

- dev4 robust pick (DD<=20, no losing dev year; prefer mean>=5, highest WORST,
  ties→mean; among REF+V1+V2, controls NOT eligible): REF (5.601/2.588/16.91) vs
  V1 (5.583/2.588/17.19) vs V2 (5.607/2.592/17.04) — all eligible, all mean>=5,
  V2 wins on WORST (2.592>2.588). PICK = V2.
- 5y (dev4 pick + REF, scored-once Y4): REF 5.410 / W 2.588 / maxDD 16.91 /
  full-path DD 16.82; V2 5.431 / W 2.592 / maxDD 17.04 / full-path DD 16.94
  (deltas +0.021 / +0.004 / +0.13 / +0.12). No losing year anywhere.
- Beats-exposure (frozen claim rule: R(V)>R(C) AND DDmax(V)<=DDmax(C) on dev4):
  V1 False (5.583<5.751 AND 17.19>16.86); V2 False (5.607<5.751 AND 17.04>16.86).
  Both variants trail their constant controls on mean with worse DD.
- V2 beats REF in 3/4 dev years (2021, 2022, 2024) and the scored-once year
  (+0.080), loses 2023 (-0.153). V1 beats REF in 2/4 dev years (2023, 2024).

## 5y, full-path DD, book episode win rate, fee split

- Book win rate (trade_stats discrete trades, after fees; per-year 4-phase sums):
  dev years REF [0.5032,0.5158,0.5191,0.5082] (dev 0.5114) vs V1
  [0.5032,0.5087,0.5186,0.5069] (0.5094) vs V2 [0.5027,0.5105,0.5279,0.5130]
  (0.5139). Scored-once Y4: REF 0.5365, V2 0.5372 (+0.07pp).
  5y book win: REF 0.5169 (5085 fills) vs V2 0.5190 (5269 fills, +184 fills from
  decay-close/re-enter churn); all-trade win (book+dip): REF 0.6539 vs V2 0.6534
  (dip rung_win identical 0.6859 — dip sleeve untouched, as designed).
- Engine totals (gate costs inside every leg; sums over 4 phase sub-accounts):
  dev fees REF 0.2070 vs V1 0.2064 vs V2 0.2109; funding (adverse longs-only) REF
  0.4114 vs V1 0.4091 vs V2 0.4077. 5y totals (scored-once): fees REF 0.2692 vs
  V2 0.2735 (+1.6% from extra decay exits); funding REF 0.5202 vs V2 0.5156
  (-0.9% from shorter holds). All R above are NET of these costs.
- Exposure diagnostic (standard-grid proxy gross ratio variant/REF per year):
  0.695/0.888/0.902/0.888/0.852 for BOTH V1 and V2 (identical bit-for-bit: for
  typical entries |w0|~0.06 the decay thresholds 0.018/0.030 sit BELOW the G2
  opening threshold 0.05, so decay only binds beyond signal-gone for large entries
  |w0|>0.167 (V1) / >0.10 (V2); the proxy cut comes from zeroing sub-threshold
  bars, identical for both fracs). Controls C_V1/C_V2 coincide by construction
  (same c_y); engine C rows identical bit-for-bit as well (3624 fills each).
  Engine time-in-position is NOT separately logged (engine stores t/eq/eq_min only,
  same as v421); fills above are the holding proxy.

## What failed and why

The decay exit barely binds: typical book entries are tiny (|w0|~0.05-0.08), so
0.3*w0 and 0.5*w0 lie below the 0.05 signal-gone line and the rule reduces to
G2's existing close on signal-gone. Only large-entry positions (|w0|>0.10 for V2)
see an earlier exit, and those are rare — hence V1≈REF (2/4 years, -0.018pp dev)
and V2≈REF+noise (+0.006pp dev, +0.021pp 5y, +0.25pp book win dev). The scored-once
Y4 gain (+0.080, DD -0.88) does not survive the exposure control: a plain constant
book-target cut to the same mean exposure (C: dev4 5.751, DD 16.86) beats V2 on
both mean (+0.14pp) and DD (-0.18pp). Round-trip ~4-8 bps bounds the mechanism;
measured dev4 edge is +0.006pp/mo (V2) at full BOT scale — economically zero.
The oc_bookholdcap failure mode (cutting live winners) is avoided (winners ride:
V2 wins 2024 +0.155 and Y4 +0.080), but decayed losers are cut no better than by
a constant exposure trim.

## Leakage checklist

- Feature timing: |w0| and |tg| are close-known policy targets only (bars ≤ decision);
  shifted clocks use latest standard row r <= t_s (ffill; identity at s=0); proxy uses
  closes <= T only. Truncation-tested in tests/test_oc_decayexit.py (post-window data
  cannot move the decay decision or proxy prefix; sub-THETA signals never open).
- Label windows: no labels fit anywhere (exits mechanical decay/flip/SL/TP/timeout).
- Fit windows: no fits, no thresholds, no quantiles anywhere (0.3/0.5 + THETA 0.05 +
  band (0.03,0.40) + COOL 6 frozen ex-ante in PLAN; R2 size/TP agents pre-date anchors;
  C_* use in-year realised means so labelled diagnostic/non-eligible and never picked).
- Fill timing: decay close is a G2-identical resting limit (vol-scaled offset,
  valid 2 bars, live [5,240), strict trade-through + minute-5 ban); SL market taker /
  TP limit maker; stop-first in the shared minute; NaN never fills/triggers. Gate
  costs inside every leg (maker 0.0002 / taker 0.00055 / longs 0.0001 per settling 8h,
  shorts 0). No statistic from any test year feeds any choice (dev pick used
  2021-2024 only; Y4 scored once for REF+V2).
- No post-hoc change: PLAN.md frozen before any outcome; the dev table was computed
  once; last stage ran REF+V2 only; C rows coincide (identical c_y) by pre-registered
  construction, reported as-is. One infra relaunch (last-stage heavy_slot job died
  while waiting for RAM; relaunched with identical rows; resume-safe caches verified).

## Repro

`research/tournament/oc_decayexit/{PLAN.md,decayexit_rule.py,compute_controls.py,run_engine.py,analyze.py,results.json,
tmp/std_books.pkl,tmp/controls.json,tmp/runs_dev.pkl,tmp/runs_last.pkl,tmp/run_dev.log,tmp/run_last.log}` +
`tests/test_oc_decayexit.py` (8 pass). Heavy via heavy_slot (tag oc_decayexit, one
job at a time, float32 cube one shift at a time; dev 4 shifts × 5 rows + last
4 shifts × 2 rows, each row ~0.2 min/shift). results.json = dev table +
scored-once last table + pick.

## Vietnamese verdict

V1 thua G2 trên dev4 (5,583 so với 5,601, DD 17,19) và thua cả mức khống chế
khớp-exposure (5,751); V2 nhỉnh hơn G2 (+0,006pp dev4, +0,08 năm scored-once)
nhưng vẫn thua khống chế (-0,14pp, DD cao hơn) nên chỉ là câu chuyện exposure.
Kết luận: REJECT cả hai biến thể decay-exit ở dạng đăng ký trước, đóng hướng này
(exit theo decay tín hiệu hầu như không kích hoạt ngoài signal-gone của G2).
