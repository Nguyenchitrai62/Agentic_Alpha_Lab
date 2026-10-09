# oc_b7frontier — REPORT (2026-10-08; PLAN frozen before any outcome)

Question: B7 on the lower-risk D13BF base: >= 5 %/month with full-path DD <= 20 on BYBIT prices?
B7 = dip budget x1.5 for 7d after a cascade bar (> 4 sigma 4h close-to-close move, oc_cascadedelay
definition). D13BF = kd 1.3, bear, NO gross cap (v424 R2B1D13BF). G2B7 = kd 1.7, G=2.0 + B7.
PLAN.md was written BEFORE any outcome; no definition changed after outcomes.
Engine via heavy_slot (sequential shifts, one heavy process, heartbeat 600 s). CPU scoring +
carry overlay (verbatim oc_c2carry) + stationary bootstrap (10d blocks, 4000 draws, seed 0).
pytest 5/5.

CONTAMINATION LABEL (pre-registered): B7 is contaminated (oc_cascadeboost — idea formed after
oc_cascadedelay's replica had covered all five years incl. the post-release year). Every
post-release number below (anchor 2025-09-24 year, BOT and carry) is a LABELLED DIAGNOSTIC
re-score, never a selection input; only prospective paper could confirm B7.

STATUS: DONE. 2 new engine configs x 4 phases = 8 phase sims (D13B7_base/S5, full-window
[DEV0,Y1)); 4 copied legs (D13BF_base/S5 from oc_c2frontier, G2B7_base/S5 from oc_cboostbybit);
12 account rows (6 BOT x f=0/0.25). All reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- G2 (stored `v421_runs.pkl` R2B1D17BFG2, CPU scored here): 2.588/10.86, 3.282/16.91,
  6.045/15.81, 10.677/8.27, 4.648/12.90; 5y 5.410; full 16.82.
- D13BF_base == v424 R2B1D13BF (2.485/10.21, 3.286/14.98, 4.975/14.76, 9.526/7.33,
  4.723/10.97; 5y 4.971; full 14.86).
- G2B7_base == oc_cascadeboost B7 == oc_cboostbybit B7_base (dev 2.955/14.67, 3.264/17.92,
  8.537/15.94, 12.486/11.01; Y4-diag 4.88/13.81; 5y 6.364; full 17.75).
- G2B7_S5 / G2_S5 / G2_base == oc_cboostbybit table (G2B7_S5: dev4 6.217/W 2.200, 5y 5.906,
  full 20.31; G2_S5 4.883/18.09).
- D13BF_S5 == oc_c2frontier table (dev4 4.492/W 1.945; 5y 4.482; full 15.95).
- G2+carry f=0.25 reproduces oc_c2carry to the digit (Binance 5.634/16.66; Bybit S5
  5.111/17.93); f=0 short-circuits to each BOT leg bit-exact.

## 1. BOT legs — dev4 (anchors 2021..2024; SELECTION window)

4-phase reset %/mo (yearly DD) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| row | y0 | y1 | y2 | y3 | mean | W | maxDD |
|---|---|---|---|---|---|---|---|
| D13BF_base | 2.485/10.21 | 3.286/14.98 | 4.975/14.76 | 9.526/7.33 | 5.033 | 2.485 | 14.98 |
| D13B7_base (NEW) | 2.807/11.78 | 3.622/16.59 | 5.526/20.54 | 11.368/9.14 | 5.779 | 2.807 | 20.54 |
| G2B7_base (copy) | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 |
| D13BF_S5 | 1.945/9.88* | 2.889/16.00 | 4.054/15.98 | 9.228/7.57 | 4.492 | 1.945 | 16.00 |
| D13B7_S5 (NEW) | 2.092/12.45* | 2.903/18.17 | 5.135/22.33 | 11.037/10.24 | 5.235 | 2.092 | 22.33 |
| G2B7_S5 (copy) | 2.200/15.07* | 2.457/19.08 | 8.368/15.98 | 12.172/12.54 | 6.217 | 2.200 | 19.08 |

\* S5 y2021 SHORT (Bybit from 2021-11-15, labelled). No losing dev year anywhere.
Sized mean mult (5y): D13B7 1.322 base / 1.332 S5 (G2B7 1.325/1.335 for reference).
Robust pick on dev4 ONLY (DD <= 20, no losing year; prefer mean >= 5 then highest W):
D13B7 FAILS the DD gate on dev4 itself (20.54 base, 22.33 S5). Eligible: D13BF (5.033/2.485)
vs G2B7 (6.738/2.955 base; 6.217/2.200 S5) -> G2B7 wins on mean AND worst-year.

## 2. BOT legs — 5y + full-path DD + worst 1m-marked episode + Y4 (DIAGNOSTIC)

| row | 5y R/W | full DD | DDmax_full | worst marked episode | Y4 R/DD (DIAG) |
|---|---|---|---|---|---|
| D13BF_base | 4.971/2.485 | 14.86 | 14.98 | 2023-04-17 -> 2023-06-14, 14.86% | 4.723/10.97 |
| D13B7_base | 5.653/2.807 | 19.36 | 20.54 | 2024-01-03 11:00 -> 12:00, 19.36% | 5.152/12.18 |
| G2B7_base | 6.364/2.955 | 17.75 | 17.92 | 2023-04-17 -> 2023-06-14, 17.75% | 4.880/13.81 |
| D13BF_S5 | 4.482/1.945 | 15.95 | 16.00 | 2023-04-17 -> 2023-06-14, 15.95% | 4.443/10.75 |
| D13B7_S5 | 5.120/2.092 | 21.33 | 22.33 | 2024-01-03 11:00 -> 12:00, 21.33% | 4.664/11.80 |
| G2B7_S5 | 5.906/2.200 | 20.31 | 20.31 | 2023-04-17 -> 2023-10-02, 20.31% | 4.670/13.43 |

D13B7's worst episode is a 1-hour 2024-01-03 flash leg (ETF-news crash; no-cap kd1.3 + B7
sizes into it) — honest 1m-marked depth, deeper on Bybit. Y4 all-win: D13B7 0.6294 base /
0.6277 S5 (book ~0.53; sizing, not selection).

## 3. With quarterly carry f=0.25 (ONE-account, verbatim oc_c2carry; carry close-marked: DD lower bound)

| row | dev4 mean/W/maxDD | Y4 R/DD (DIAG) | 5y R/W | full DD | bootstrap median / P(m>=5%) / P(DD>20%) / P(lose) |
|---|---|---|---|---|---|
| D13BFc_base | 5.304/2.677/14.82 | 4.772/10.84 | 5.198/2.677 | 14.71 | 5.137 / 52.10 / 4.98 / 0.47 |
| D13B7c_base | 6.051/2.996/20.42 | 5.202/12.07 | 5.880/2.996 | 19.24 | 5.844 / 61.88 / 11.28 / 0.43 |
| G2B7c_base | 7.001/3.142/17.76 | 4.930/13.69 | 6.584/3.142 | 17.60 | 6.516 / 69.83 / 10.62 / 0.33 |
| D13BFc_S5 | 4.766/2.139/15.84 | 4.492/10.55 | 4.711/2.139 | 15.79 | 4.821 / 46.83 / 8.30 / 0.78 |
| D13B7c_S5 | 5.508/2.284/22.21 | 4.714/11.58 | 5.349/2.284 | 21.21 | 5.462 / 56.27 / 27.30 / 1.05 |
| G2B7c_S5 | 6.482/2.391/18.93 | 4.719/13.31 | 6.127/2.391 | 19.72 | 6.077 / 64.80 / 15.68 / 0.60 |

Carry adds +0.23-0.27 5y on every leg (same as oc_c2carry). Assignment question — Bybit S5
with carry, 5y >= 5 AND full-path DD <= 20: D13BFc 4.711/15.79 FAILS return; D13B7c
5.349/21.21 FAILS DD (also fails dev4 DD 22.21; bootstrap P(DD>20%) 27.3%); ONLY G2B7c
6.127/19.72 PASSES both (dev4 6.482/W 2.391/DD 18.93; bootstrap median 6.077, P(m>=5%) 64.8%,
P(DD>20%) 15.7%, P(lose) 0.6%). No losing year in any of the 12 rows.

## 4. Leakage / causality checks (how verified)

- Feature timing: cascade triggers use closes with close_time <= tc only (SIG excludes tested
  bar; boost window strictly after tc 0 < T-tc <= 7d); `test_truncation_causal_on_real_bars`
  recomputes triggers from truncated real 4h bars — identical on kept prefix; multiset in
  {1.0, 1.5}. Engine exact (shift,T) match + causal ffill fallback, missing -> 1.0. kd/G
  asserted (D13B7 1.3/no-cap, G2B7 1.7/2.0, F 2.5).
- Label windows: no labels fit anywhere. Fit windows: no fits; threshold 4.0, windows
  540/120, boost 1.5, N=7, kd/G, carry 0.04/f 0.25 all frozen ex-ante; no test-year statistic
  feeds any choice (S5 = price-source switch, carry = account switch, not fits).
- Fill timing: win_start=5 asserted in test (S5 live0 2021-11-15 + Bybit dir in source);
  engine fills only on 1m trade-through with stop-first (inherited); carry MtM uses last
  CLOSED hourly bar strictly before t; bootstrap uses daily causal ffill, no 1m peeking.
- Gate costs inside engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h; carry
  fees spot 0.001/side + fut 0.00055/0.0002 frozen).
- `tests/test_oc_b7frontier.py` 5/5 pass.

## 5. What failed / caveats

- The hypothesis FAILED: B7 on D13BF does not give >= 5 %/mo with DD <= 20 on Bybit — it
  gives 5.349 with DD 21.21 (with carry; 5.120/21.33 without). Worse, it already breaches DD
  20 on dev4 (22.33 S5, 20.54 base), so it is not even selectable under the robust rule.
  The no-cap kd1.3 base + 1.5x boost sizes into the 2024-01-03 flash leg.
- The row that DOES meet 5y >= 5 and full DD <= 20 on Bybit with carry is the old high-risk
  base: G2B7c_S5 6.127/19.72 (without carry G2B7_S5 5.906/20.31 breaches, as known). That is
  not a new finding — it is the contaminated B7 on G2 plus a post-hoc carry overlay on the
  same five years; Y4 diagnostic adds no clean evidence; bootstrap P(DD>20% in a year) is
  still 15.7%.
- S5 y2021 SHORT; carry marks close-marked (DD lower bound); bootstrap assumes ~stationary
  daily returns with ~10-day dependence (no annual regime structure).

## 6. Post-hoc log

- No PLAN definition changed after outcomes. All 6 BOT + 6 carry rows scored as
  pre-registered; reproduction gates passed to the digit.

## Vietnamese verdict (3 lines)

- Trên giá Bybit kèm carry f=0,25, chỉ G2+B7 đạt cả hai (5y 6,13%/tháng, full-path DD 19,72); D13BF+B7 thiếu DD (5,35 nhưng DD 21,21, dev4 đã 22,33), D13BF thiếu return (4,71 dù DD 15,79).
- Nhưng G2+B7 là hàng nhiễm (ý tưởng sau khi thấy cả 5 năm) cộng carry post-hoc trên cùng 5 năm, năm diagnostic không sạch và bootstrap P(DD>20%) vẫn 15,7% — không adopt vốn thật.
- Kết luận: needs prospective evidence — giữ B7 và carry trong paper runner hiện tại, không triển khai thật, D13BF+B7 reject vì vỡ DD ngay trên dev4.
