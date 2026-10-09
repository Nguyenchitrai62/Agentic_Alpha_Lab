# oc_d_stagger — REPORT (2026-10-08; PLAN frozen before any outcome)

Does placement-time stagger help? Idea #5 (IDEAS12): split each dip rung 50/50 at the
SAME frozen sigma price — V1 second print minute 35, V2 minute 95 (first print minute 5;
both expire 60 min, placed once, never re-pegged; minute-5 ban + strict trade-through
maker kept). Exposure-identical BY DESIGN (halves sum to the base size when both fill).

STATUS: DONE. Pre-sample stagger rebuilt (V1 3,130 rows / V2 5,582 rows vs REF 9,731
fills) + 1,000 B-half timing/block perms per year; base-kind recompute complete
(15 unknown; kinds TP/time/stop/backstop = 5,729/3,445/480/62 — EXACTLY the
oc_cboostpre recompute, cross-validating the VERBATIM core); 2021-2026 stagger rebuilt
(V1 6,616 / V2 11,842 rows vs REF 22,312) + perms. REF reproduction gates pass both
eras (pre: n = 9,731, sums 2.313362/2.678870/0.577643/0.297538; 21-26: n = 22,312,
sum5y = 7.718304). NO ENGINE (PLAN-gated: PRIMARY and SECONDARY both fail for both
variants — valid negative result, no engine claim).

## Pre-sample replica (SPOT fills/exits, perp gate costs inside; caveat on every number)

| year x variant | n_base / stag rows (A/B/both) | base | stag | gain | E (exposure) | timing pct | block pct |
|---|---|---|---|---|---|---|---|
| Y2017 V1 | 909 / 307 (169/292/154) | 2.313362 | 0.692790 | -1.620571 | 0.257 | 92.11 | 100.00 |
| Y2018 V1 | 2986 / 873 (466/829/422) | 2.678870 | 0.819421 | -1.859449 | 0.233 | 36.76 | 67.23 |
| Y2019 V1 | 3115 / 1079 (682/953/556) | 0.577643 | 0.094318 | -0.483325 | 0.271 | 0.40 | 5.79 |
| Y2020p V1 | 2721 / 871 (562/788/479) | 0.297538 | 0.039951 | -0.257587 | 0.263 | 0.40 | 16.88 |
| Y2017 V2 | 909 / 543 (169/455/81) | 2.313362 | 0.669826 | -1.643536 | 0.337 | 99.90 | 100.00 |
| Y2018 V2 | 2986 / 1710 (466/1519/275) | 2.678870 | 0.770272 | -1.908599 | 0.327 | 84.32 | 92.81 |
| Y2019 V2 | 3115 / 1787 (682/1488/383) | 0.577643 | -0.112695 | -0.690338 | 0.337 | 100.00 | 100.00 |
| Y2020p V2 | 2721 / 1542 (562/1276/296) | 0.297538 | -0.120270 | -0.417807 | 0.325 | 66.43 | 63.94 |

- Helps (gain > 0): V1 0/4, V2 0/4. COVID leg Y2020p negative both (-0.26/-0.42).
- Timing: this IS a timing rule and timing mostly does NOT support it either (V1
  2019/2020p pct 0.4 = significantly WORSE than random B placement; V2 2019 pct 100 but
  on a negative sum — beats random B perms yet far below doing nothing).
- Mechanism (honest): the 60-min expiry cuts realised exposure to 23-34% (E column) —
  most base fills arrive after offset 94 — so raw sums lose by construction. The
  IDEAS12 "exposure-identical" holds only when both halves fill (both-halves rows are
  40-55% of stagger rows). Disclosed EXTRA per-unit-exposure diagnostic (stag/E -
  base): V1 helps 2/4 (2017 +0.38, 2018 +0.84; 2019 -0.23, COVID -0.15), V2 helps 0/4
  (2017 -0.32, 2018 -0.32, 2019 -0.91, COVID -0.67). Even exposure-matched, the late
  B window (V2 [95,154]) catches losers: V2 yearly stag sums go NEGATIVE in 2019/2020p.

## Crash risk (stop-hit share of stagger filled halves vs base rate, mu = 1.0)

| year | base stop% | V1 halves stop% (delta) | V2 halves stop% (delta) | base TP% |
|---|---|---|---|---|
| Y2017 | 3.30 | 4.99 (+1.69) | 5.77 (+2.47) | 80.3 |
| Y2018 | 3.29 | 5.48 (+2.19) | 6.15 (+2.86) | 55.8 |
| Y2019 | 6.69 | 8.26 (+1.57) | 8.43 (+1.74) | 55.3 |
| Y2020p | 7.58 | 12.30 (+4.72) | 12.24 (+4.66) | 59.5 |
| pooled | 5.58 | 8.33 (+2.75) | 8.55 (+2.97) | — |

- FAIL (pre-registered b7breaker standard): pooled stagger stop-given-fill rises
  +2.75pp (V1) / +2.97pp (V2), both > +1pp. The 60-min halves that DO fill are
  adversely selected (early-touch rungs stop more). COVID leg worst (+4.7pp both).
- PRIMARY verdict: V1 helps 0/4 (need >= 3/4), COVID negative, stop FAIL. V2 same.
  PRIMARY FAILS for both variants.

## SECONDARY: 2021-2026 replica gate (dSum5y >= +0.273 AND sum-half >= 4/5)

| year x variant | base | stag | gain | E | timing pct |
|---|---|---|---|---|---|
| 2021 V1 / V2 | 0.911273 | 0.336494 / 0.029445 | -0.574778 / -0.881828 | 0.224 / 0.292 | 59.54 / 1.30 |
| 2022 V1 / V2 | 0.832599 | -0.017094 / -0.323698 | -0.849692 / -1.156297 | 0.264 / 0.319 | 38.36 / 96.20 |
| 2023 V1 / V2 | 2.099814 | 0.178074 / 0.121491 | -1.921739 / -1.978322 | 0.251 / 0.309 | 29.77 / 100.0 |
| 2024 V1 / V2 | 3.197390 | 0.924968 / 0.903050 | -2.272423 / -2.294340 | 0.214 / 0.295 | 100.0 / 91.01 |
| 2025 V1 / V2 | 0.677229 | 0.104821 / -0.061907 | -0.572408 / -0.739136 | 0.214 / 0.289 | 0.90 / 29.77 |

- V1: dSum5y = -6.191041, sum-half 0/5. V2: dSum5y = -7.049922, sum-half 0/5.
  SECONDARY FAILS decisively for both (needs +0.273 and 4/5). Late-window halves again
  print negative yearly sums (V1 2022 -0.017, V2 2022 -0.324, V2 2025 -0.062).
- ENGINE: NOT RUN for either variant (PLAN-gated: needs PRIMARY + SECONDARY pass).
  No exposure-control (CTRL_C union-window) or Bybit S5 leg was run — there is nothing
  to decompose; running them on a 0/9 idea would be outcome-shopping.

## Candidate-credibility checks

1. Sign-stable / fit-free rule: PASSES by construction (frozen times 5/35/95, 60-min
   expiry, 50/50 split; no fits, no thresholds on returns).
2. Beats the exposure control: N/A at engine stage (not run, gated); replica
   exposure diagnostic: even per-unit-weight V1 helps only 2/4 pre-sample (COVID
   fails) and V2 0/4 — the loss is NOT just the exposure cut.
3. Bybit leg: NOT RUN (gated; nothing passed to confirm).
4. Pre-sample leg: FAILS (0/4 both, COVID negative, stop +2.8pp).
- 1 of 4 holds (fit-free only). Verdict: REJECT.

## Leakage statement

- Feature timing: stagger uses NO market features — rung price from O/sg available at
  T only; placement times are constants; halves fill only on 1m lows at offsets >= 5
  with strict trade-through; exits use minutes > f_h only; truncation-tested in
  tests/test_oc_d_stagger.py (6 pass).
- Label windows: none fit anywhere (no harness join, exits mechanical).
- Fit windows: no fits; 5/35/95 starts, 60-min expiry, 50/50 split, seeds
  20261007/20261008, BLOCK 42 all frozen ex-ante, never scanned; no statistic from any
  test year feeds any choice; pre-sample years never used for any fit.
- Fill timing: strict trade-through + minute-5 ban + stop-first inherited in all
  rebuilt outcomes; perms reassign B-half P&L within (year, shift) only.
- Gate costs inside all rebuilt outcomes (maker 0.0002/taker 0.00055, adverse long
  funding 0.0001/8h). Coverage: no skipped year; base-kind unknown 15/9731 (0.15%).
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).

## What failed and why

- As literally specified (60-min expiry), the stagger trades 23-34% of base exposure
  and loses on sums in ALL 9 available years (pre 0/4 both, 21-26 0/5 both;
  dSum5y -6.19/-7.05). The halves that fill are adversely selected (stop +2.8pp
  pooled, +4.7pp COVID). The late second print (V2 minute 95) is worst: negative
  yearly sums in 2019/2020p/2022/2025 — waiting catches losers, not better prices.
- Round-trip ~4-8 bps bounds nothing here: effects are 10-100x larger and all negative.
- Post-hoc notes (PLAN log): (1) basekind first attempt thrashed (coin-interleaved
  1m reloads; killed, regrouped by coin — same arithmetic, no row changed);
  (2) exposure-normalised stag/E rows are disclosed extras, frozen raw rows primary.

## Vietnamese verdict

Ý tưởng chia lệnh làm hai theo thời gian THẤT BẠI rõ ràng trên cả 9 năm (pre-sample
0/4 cả hai biến thể, 2021-2026 0/5, dSum5y -6,2/-7,0): hết hạn 60 phút cắt khối lượng
còn 23-34% mà nửa lệnh khớp được lại dừng lỗ nhiều hơn (+2,8pp gộp, +4,7pp chân
COVID), lệnh in muộn V2 thậm chí lỗ tuyệt đối.
Chỉ có tính fit-free là đạt (quy tắc đóng băng, không fit); chuẩn hoá theo đơn vị
khối lượng cũng chỉ V1 được 2/4 còn V2 0/4 nên đây không phải vấn đề mỗi khối lượng.
Kết luận: REJECT — đóng hướng stagger, không engine, không Bybit, không prospective.
