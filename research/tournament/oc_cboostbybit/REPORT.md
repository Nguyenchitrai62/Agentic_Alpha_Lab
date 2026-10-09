# oc_cboostbybit — REPORT (2026-10-08; PLAN frozen before any outcome)

Question: does B7 keep its edge under frictions and on BYBIT prices (S5)?
B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move, oc_cascadedelay
definition) — dev4 robust pick of oc_cascadeboost (dev4 mean 6.74 / WORST 2.96 / DD 17.92 vs G2
5.60 / 2.59 / 16.91; 5y 6.36). Friction harness copied EXACTLY from oc_c2bybit (itself from
v421_audit/robust_v421.py). PLAN.md was written BEFORE any outcome; no definition changed after outcomes.
Engine via heavy_slot (sequential shifts, one heavy process, heartbeat every 600 s, nohup + tmp logs).
pytest 5/5.

CONTAMINATION LABEL (pre-registered): the B7 idea was formed after oc_cascadedelay's replica had covered
all five years incl. the post-release year, so every post-release number below is a LABELLED DIAGNOSTIC
(not clean evidence); new evidence here comes from frictions + Bybit prices only; only prospective paper
could confirm B7.

STATUS: DONE. 12 engine rows (REF/B7 x base/S1/S2/S3/S4/S5, 4 phases each = 48 phase sims) + CPU scoring.
Reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- Base REF == `v421_result.json` G2 (R2B1D17BFG2) all 5 years + 5y 5.410 + full-path DD 16.82.
- Base B7 == `oc_cascadeboost` results.json B7 (dev 2.955/14.67, 3.264/17.92, 8.537/15.94, 12.486/11.01;
  Y4-diagnostic 4.88/13.81; 5y 6.364; full-path DD 17.75; dev4 6.738/W 2.955).
- REF_S1..S5 == `v421_audit/ROBUST.md` G2 friction row to the digit (S1 4.571/17.45/17.37,
  S2 5.212/16.91/16.86, S3 4.578/17.32/17.24, S4 4.898/17.31/17.24, S5 4.883/18.11/18.09),
  so friction implementations are exactly the existing ones. Comparison valid.

## 1. Dev4 (anchors 2021..2024 — select/compare window; B7 idea itself is post-hoc, see label above)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| fric | REF | B7 | gap dev4 |
|---|---|---|---|
| base | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 \| 5.601/2.588/16.91 | 2.955/14.67, 3.264/17.92, 8.537/15.94, 12.486/11.01 \| 6.738/2.955/17.92 | +1.137 |
| S1 | 1.975/11.18, 2.592/17.45, 4.853/16.01, 9.712/8.31 \| 4.740/1.975/17.45 | 2.219/14.96, 2.100/18.70, 6.852/16.29, 11.222/11.05 \| 5.532/2.100/18.70 | +0.792 |
| S2 | 2.513/11.09, 3.132/16.91, 5.624/15.82, 10.479/8.29 \| 5.391/2.513/16.91 | 2.957/14.62, 2.980/17.91, 8.240/15.83, 12.301/11.02 \| 6.548/2.957/17.91 | +1.157 |
| S3 | 2.070/11.85, 2.476/17.32, 4.346/16.03, 9.798/8.36 \| 4.628/2.070/17.32 | 2.291/15.57, 2.049/18.46, 6.703/17.13, 11.532/11.11 \| 5.574/2.049/18.46 | +0.946 |
| S4 | 2.363/11.06, 2.915/17.31, 4.422/17.08, 10.460/8.27 \| 4.992/2.363/17.31 | 2.778/15.00, 2.668/18.50, 6.876/16.96, 12.170/11.00 \| 6.053/2.668/18.50 | +1.061 |
| S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 \| 4.994/2.129/18.11 | 2.200/15.07, 2.457/19.08, 8.368/15.98, 12.172/12.54 \| 6.217/2.200/19.08 | +1.223 |

S5 y2021 is a SHORT window (Bybit from 2021-11-15, labelled). No losing dev year in any row.
Sized mean multiplier (5y): B7 1.325 base / 1.324 S1 / 1.325 S2 / 1.325 S3 / 1.324 S4 / 1.335 S5
(REF 1.0 everywhere) — the boost binds on ~65% of sizings.

## 2. Post-release year Y4 2025-09-24..2026-09-23 (CONTAMINATED: B7 formed after seeing this year via the delay replica — every Y4 number here is a labelled DIAGNOSTIC re-score under frictions, never a selection input)

| fric | REF R/DD | B7 R/DD | gap Y4 |
|---|---|---|---|
| base | 4.648/12.90 | 4.880/13.81 | +0.232 |
| S1 | 3.900/13.61 | 3.909/14.51 | +0.009 |
| S2 | 4.501/12.98 | 4.737/13.85 | +0.236 |
| S3 | 4.380/12.75 | 4.430/14.35 | +0.050 |
| S4 | 4.522/13.54 | 4.714/14.82 | +0.192 |
| S5 | 4.443/12.37 | 4.670/13.43 | +0.227 |

Gap stays positive everywhere but shrinks to ~0 under cost stress (S1 +0.009) and latency 30 (S3 +0.050);
no friction flips the sign, but the diagnostic adds no clean evidence (see label).

## 3. Five-year path + full-path DD (v388.mix from 2021-09-24) + worst 1m-marked episode

| fric | REF 5y R/W/DD/full | B7 5y R/W/DD/full | gap 5y | B7 worst marked episode |
|---|---|---|---|---|
| base | 5.410/2.588/16.91/16.82 | 6.364/2.955/17.92/17.75 | +0.954 | 2023-04-17 -> 2023-06-14, 17.75% |
| S1 | 4.571/1.975/17.45/17.37 | 5.205/2.100/18.70/18.64 | +0.634 | 2023-04-17 -> 2023-06-14, 18.64% |
| S2 | 5.212/2.513/16.91/16.86 | 6.183/2.957/17.91/17.75 | +0.971 | 2023-04-17 -> 2023-06-14, 17.75% |
| S3 | 4.578/2.070/17.32/17.24 | 5.344/2.049/18.46/18.44 | +0.766 | 2022-05-10 -> 2022-11-09, 18.44% |
| S4 | 4.898/2.363/17.31/17.24 | 5.784/2.668/18.50/18.40 | +0.886 | 2023-04-17 -> 2023-06-14, 18.40% |
| S5 | 4.883/2.129/18.11/18.09 | 5.906/2.200/19.08/20.31 | +1.023 | 2023-04-17 -> 2023-10-02, 20.31% |

- B7-REF gap > 0 on the 5y mean under base AND every friction (smallest +0.634 on S1).
- Full-path DD <= 20 HOLDS for base/S1/S2/S3/S4 (worst 18.64 on S1) but FAILS on S5: B7_S5 full-path DD
  20.31 > 20 (yearly max 19.08; the marked episode runs 2023-04-17 -> 2023-10-02, longer than the base
  2023-06-14 trough — Bybit prices stretch the 2023 leg). REF_S5 full-path DD is 18.09.
- No losing 5y year in any row (worst yearly R: B7_S1 2.100, B7_S3 2.049).
- All-trade win rates move <= 0.004 (e.g. base Y4 B7 0.6230 vs REF 0.6267; S5 Y4 B7 0.6220 vs REF 0.6247;
  5y base B7 book 0.5118/rung 0.6827-class, same as cascadeboost) — the boost is sizing, not selection.
  Book win stays ~0.50-0.54 (below any manual floor; this study sizes the BOT sleeve).

## 4. Leakage / causality checks (how verified)

- Feature timing: cascade triggers use closes with close_time <= tc only (SIG window excludes the tested
  bar; boost window strictly after tc 0 < T-tc <= 7d); `test_truncation_causal_on_real_bars` recomputes
  triggers from truncated real 4h bars — identical on the kept prefix; multiset subset of {1.0, 1.5}.
  Engine uses exact (shift, T) match with causal ffill fallback (latest grid time <= T), missing -> 1.0.
- Label windows: no labels fit anywhere in this study.
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N=7 all frozen ex-ante, never scanned;
  no statistic from any test year feeds any choice (S5 is a price-source switch, not a fit).
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in source; S5 live0 2021-11-15
  + Bybit dir); engine fills only on 1m trade-through with stop-first (inherited harness).
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h; S1 stress
  maker 0.0004 / taker 0.0012).
- Coverage: 4h boost grid covers every anchor year — no skipped year, nothing imputed.
- `tests/test_oc_cboostbybit.py` 5/5 pass.

## 5. Post-hoc log

- No PLAN definition changed after outcomes. All 12 rows scored as pre-registered; reproduction gates
  passed to the digit (REF_base==v421 G2, B7_base==oc_cascadeboost B7, REF_S1..S5==ROBUST.md G2).
- S1 TAKER = 0.0007 + 0.0005 = 0.0012 (same as robust_v421.py / oc_c2bybit).

## Vietnamese verdict (3 lines)

- B7 hơn REF về return ở mọi ma sát trên cả dev4 (+0,79 tới +1,22) và đường 5 năm (+0,63 tới +1,02), kể cả giá Bybit S5 (dev4 +1,223, 5y +1,023), và năm diagnostic cũng dương ở mọi ma sát (dù S1 chỉ +0,009); không có năm lỗ ở bất kỳ hàng nào.
- Nhưng full-path DD của B7 vượt 20 đúng ở giá Bybit S5 (20,31 so với REF 18,09; các ma sát còn lại ≤ 18,64), vì giá Bybit kéo dài đoạn drawdown 2023 tới tháng 10 — nên tiêu chí ma sát đầy đủ (gap > 0 MỌI hàng VÀ DD ≤ 20) KHÔNG đạt.
- Kết luận: KHÔNG robust theo nghĩa chặt — giữ B7 làm ứng viên chờ log paper prospective xác nhận, không triển khai thật, và mọi con số post-release ở đây chỉ là diagnostic nhiễm.
