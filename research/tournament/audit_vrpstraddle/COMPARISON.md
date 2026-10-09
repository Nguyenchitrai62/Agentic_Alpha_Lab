# audit_vrpstraddle COMPARISON (blind replication of oc_vrpstraddle V2 + G2 overlay f=0.25)

Blind protocol followed: replication built ONLY from `research/tournament/oc_vrpstraddle/PLAN.md`
+ `research/tournament/oc_carrycompound/analyze_carrycompound.py` (G2 loading convention).
`replication.json` (part A) was written BEFORE opening `oc_vrpstraddle/REPORT.md`, `results.json`,
`vrp.py`, `run_vrp.py`. G2 baseline reproduced to the digit first (5.41 / 16.91 / 16.82).
No computation on the most recent year except the overlay 5y row (needed for full-path DD);
that row is labelled and was not used for any choice.

## Part A (mine) vs theirs

Standalone V2 (R %/mo geometric / DD % hourly-marked / trades TP/SL/expiry):

| year | mine (part A) | theirs (results.json/REPORT.md) | delta |
|---|---|---|---|
| 2021-09-24 | 7.823 / 25.55 / 104 (24/13/67) | 8.004 / 25.82 / 104 (24/13/67) | R -0.181pp MISMATCH(>0.10), DD -0.27 ok, counts exact |
| 2022-09-24 | 4.224 / 16.60 / 102 (34/16/52) | 4.197 / 18.24 / 102 (34/17/51) | R +0.027 ok, DD -1.64 MISMATCH(>0.5), SL -1/expiry +1 (within 2) |
| 2023-09-24 | -0.329 / 24.79 / 102 (18/24/60) | -0.165 / 25.05 / 102 (20/23/59) | R -0.164 MISMATCH, DD -0.26 ok, TP -2/SL +1/expiry +1 (each within 2) |
| 2024-09-24 | 2.056 / 23.34 / 102 (36/17/49) | 1.903 / 23.40 / 102 (36/17/49) | R +0.153 MISMATCH, DD -0.06 ok, counts exact |
| dev4 mean/worst/maxDD | 3.400 / -0.329 / 25.55 | 3.441 / -0.165 / 25.82 | mean -0.04, worst -0.16 |

Overlay f=0.25 (R / yearly DD), reset metric, per-year reset A=1.0:

| year | mine | theirs | delta |
|---|---|---|---|
| 2021 | 4.658 / 11.19 | 4.655 / 11.18 | +0.003 / +0.01 ok |
| 2022 | 4.390 / 16.09 | 4.365 / 16.10 | +0.025 / -0.01 ok |
| 2023 | 6.027 / 15.59 | 6.073 / 15.59 | -0.046 / 0.00 ok |
| 2024 | 11.351 / 8.27 | 11.314 / 8.53 | +0.037 / -0.26 ok |
| 2025 labelled-once | 5.799 / 13.72 | 5.780 / 13.70 | +0.019 / +0.02 ok |
| 5y R / worst / maxDD | 6.415 / 4.390 / 16.09 | 6.408 / 4.365 / 16.10 | +0.007/+0.025/-0.01 ok |
| full-path DD marked/close/max | 16.01 / 15.20 / 16.01 | 16.01 / 15.20 / 16.01 | exact |

So the G2 overlay (the decision-relevant leg) reproduces to <0.05pp R and <=0.26pp DD
with bit-exact full-path DD; the standalone V2 breaches the strict thresholds on R in
3/4 years (0.15-0.18pp) and on DD in 1 year (1.64pp), with exit counts within 2/yr.

## Causes (spec ambiguity vs bug)

1. Hourly price convention (spec ambiguity, affects everything ~0.1-0.2pp).
   PLAN.md Data: "Hourly close = 1m close of minute :59" but SL section: "price = 1m
   close of that minute". I used the 1m candle of that minute (:00, exact match;
   `replicate.py::simulate_coin` / `get_close` with `searchsorted == ts`).
   They use the prior minute (:59): `run_vrp.py:484`
   `px = np.array([px_at(d["m_ts"], d["m_cl"], int(t) - 60_000_000_000)[0] for t in gn])`
   with `px_at` = "1m close of bar open exactly q; else last bar open strictly
   before q" (`run_vrp.py:115-122`). One-minute shift in every SL/TP/mark/buyback
   price explains same-count R gaps (2021, 2024) and worst-week pct gaps
   (mine -16.91/-13.47/-12.65/-16.57 vs theirs -16.85/-13.84/-12.99/-16.05).
2. SL trigger sigma (spec ambiguity, flips 1-2 trades/yr).
   PLAN.md SL trigger: "position P&L(t) = hedge_cash + pos*px(t) - q*(mark_call +
   mark_put) + opt_cash" with "sigma from latest known DVOL" (1.0x implied), while
   the buyback is explicitly "at BS with sigma = 1.05 x latest known DVOL"
   (`PLAN.md:46-55`). I trigger on the 1.0x mark and buy back at 1.05x.
   They trigger on the 1.05x mark: `run_vrp.py:245`
   `pnl = hc[j] + pos[j]*px[j] - m105[j] + opt_cash` with `sig_sl = SL_MULT*sigv`
   (`run_vrp.py:217`) and `m105 = bs_straddle_vec(px,K,T,sig_sl)` (`run_vrp.py:219`),
   i.e. a stricter/earlier SL. This flips the 2022 SL 16-vs-17 / expiry 52-vs-51
   and 2023 TP 18-vs-20 / SL 24-vs-23 / expiry 60-vs-59. TP-first at 4h closes is
   identical on both sides (`run_vrp.py:242` vs mine), and neither checks exits at
   the expiry step itself (`run_vrp.py:239` `for j in range(L-1)` vs mine `t < expiry`).
3. IV-RV gap reporting scale (their reporting deviation, selection-neutral).
   PLAN.md: "mean IV-RV gap at entries (sigma_sell vs 7d/28d realised vol...)" where
   "sigma_sell = 0.97 * latest known DVOL / 100" (`PLAN.md:19-21,94-96`). I average
   `sigma_sell - rv`. They average raw DVOL: `run_vrp.py:430-431`
   `gaps = [(t["iv"]/100 - rv)...]` with `t["iv"] = p["sig_raw"]` (`run_vrp.py:382`,
   `sig_raw` = pre-0.97 DVOL points, `run_vrp.py:170,287`) plus `rv` with ddof=1
   (`run_vrp.py:284` vs mine ddof=0). 3% of ~60-87 DVOL points ~ 1.8-2.6 vol points
   accounts for mine 0.0709/0.0785/-0.0086/-0.0062 vs theirs
   0.097/0.0954/0.0087/0.0115. Their post-hoc log already flags this row as
   "reporting scale only" (`REPORT.md:20-21`). No selection impact.
4. No other material difference: BS helpers identical (`vrp.py:26-58` vs my `bs_pair`;
   same d1/d2, T<=0/s<=0 -> intrinsic); strike `round(S/grid)*grid` identical
   (`vrp.py:125-129`); fees per-unit x q with caps `min(0.0003*S, 0.125*leg)` /
   settlement `min(0.00015*S, 0.125*intrinsic)` ITM-only identical
   (`vrp.py:132-145`); size `q = 0.5*f*E/S` identical (`vrp.py:148-152`); Friday
   entries 08:05 / S at 08:04 / expiry next-Friday 08:00 / settlement mean
   07:30..07:59 identical; boundary skip identical in effect (trade counts match,
   their `n_skip=2`/yr in `results.json`, yearly expiries all <= year-end).

## Look-ahead and accounting checks (each with a test in tests/test_audit_vrpstraddle.py)

- DVOL as-of PASS: both last candle with close <= decision (`run_vrp.py:125-129`
  `d_ms + 3600s, side="right"`; mine `close_ns <= ts, side="right"`). Entry uses the
  07:00-08:00 hourly candle at 08:05, never the 08:00-09:00 one.
- S at 08:04 PASS: exact 08:04 1m close on both sides; their inexact counter stays 0
  (`REPORT.md:117`), mine requires exact (no fallback taken in dev years).
- Settlement window PASS: mean of 30 closes 07:30..07:59, known at 08:00. Their
  `px_at` falls back to the prior bar on gaps (robustness only); mine requires exact.
  Data are complete so paths coincide.
- SL order/marks: TP-first at 4h closes on both sides PASS as ordering; trigger-sigma
  differs as item 2 above (ambiguity, not leakage: both sigmas are as-of known).
- TP on 4h closes with TP-first PASS (`run_vrp.py:241-244`).
- Fees PASS: per-unit x q on both sides; buyback base = triggering close; settlement
  ITM-only. No missing leg.
- Overlay compounding PASS: `A(t) = A(t-1)*(1+r_bot(t)) + dSleeve(t)` on both sides;
  sleeve notionals `N = f x A` at entry grid (theirs `run_vrp.py:355-360`
  `q = size_q(A_prev, S, f)` + `cash += q*opt_cash`; mine `N = F*A_prev`, `q1=0.5/S`).
  Premium cash and the open short-option liability are booked TOGETHER at the first
  hourly grid > entry (09:00): theirs `cash += q*opt_cash` at `e_step` plus
  `U += q*(-m10 + pos*px)` from the same step (`run_vrp.py:384-396`); mine same.
  Hence at every hourly combo point the liability IS marked (close-marked m10) —
  no free premium-cash interval at hourly resolution. Missed moves are only the
  08:05->09:00 window and intrabar travel, i.e. the labelled lower bound
  (`REPORT.md:104-105` "Marks are hourly closes: DD is a lower bound (no intrabar)").
- Boundary-week skip PASS: same taken set (counts match exactly); expiries past
  year-end excluded on both sides.
- Post-hoc fix #3 CORRECT: final `M = A_prev x hh + dU` (`run_vrp.py:408-409`) matches
  `analyze_carrycompound.py:244-245` and the reset-metric convention; the old
  `M_prev x hh` compounded Pi(ms/es) decay (~104% DDs). My independent implementation
  of the fixed formula reproduces their full-path DD bit-exact (16.01/15.20/16.01),
  confirming the fix.

Accounting verdict: the overlay's DD and return ARE computed with the open straddle
liability marked at every hourly point (close-marked); premium cash is not counted
before the liability at hourly sampling. Combo DD is a lower bound only for the
labelled reasons (hourly closes, 08:05-09:00 window), not from an accounting hole.

## Final line

PASS-WITH-NOTES (overlay exact; standalone V2 within 0.19pp R / 1.7pp DD with
explained causes; no look-ahead, no accounting hole; fix #3 correct).

Tiếng Việt:
- Overlay G2+f=0.25 khớp gần như tuyệt đối (full-path DD khớp từng chữ số), kế toán không có lỗ hổng.
- Standalone V2 lệch nhỏ do quy ước giá nến :59/:00 và ngưỡng SL 1.0x/1.05x, đã giải thích rõ.
- Không phát hiện look-ahead; công thức M sau fix #3 là đúng.
