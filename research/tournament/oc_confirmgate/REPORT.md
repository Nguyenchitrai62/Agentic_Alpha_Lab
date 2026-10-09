# oc_confirmgate — REPORT (2026-10-08; retrospective meta-study, stored runs only)

Q: do the IDEAS10 #1 confirm legs separate transferred from non-transferred dev4 picks?
Leg1 = Bybit-S5 dev4 robust vs REF. Leg2 = pre-sample 2017-2020 replica. Transfer = Y4
(CAND>REF, Binance base, quoted labelled). Zero new engines/fits (0/6 S5 reruns used).

## 1. Stored dev table (Binance base, 4-phase reset %/mo; Y4 scored ONCE by origin)

| cand | 2021 | 2022 | 2023 | 2024 | dev4/W/DD | Y4 (gap) | 5y/fullDD |
|---|---|---|---|---|---|---|---|
| REF G2 | 2.588 | 3.282 | 6.045 | 10.677 | 5.601/2.588/16.91 | 4.648 | 5.410/16.82 |
| C2 | 2.711 | 3.460 | 6.250 | 10.721 | 5.739/2.711/15.48 | 4.754 (+0.106) | 5.542/15.42 |
| K2 | 2.469 | 3.478 | 6.679 | 10.653 | 5.772/2.469/16.20 | 4.801 (+0.153) | 5.577/16.09 |
| D1 | 2.921 | 3.604 | 6.541 | 10.191 | 5.776/2.921/16.09 | 4.591 (-0.057) | 5.538/15.98 |
| W2 | 2.590 | 3.345 | 8.215 | 10.711 | 6.162/2.590/15.19 | 4.488 (-0.160) | 5.825/15.19 |
| L2 | 2.529 | 3.282 | 7.074 | 10.827 | 5.877/2.529/16.91 | unscored | —/16.82dev |
| V1 vpin | 2.598 | 3.333 | 5.999 | 10.086 | 5.464/2.598/17.20 | 4.749 (+0.101) | 5.320/17.13 |
| V2 decay | 2.592 | 3.308 | 5.892 | 10.832 | 5.607/2.592/17.04 | 4.728 (+0.080) | 5.431/16.94 |
| AS18 | 2.704 | 3.042 | 6.174 | 10.488 | 5.556/2.704/18.02 | 4.628 (-0.020) | 5.37/18.05 |
| B7 | 2.955 | 3.264 | 8.537 | 12.486 | 6.738/2.955/17.92 | 4.880 (+0.232c) | 6.364/17.75 |
| A1 xs | 2.798 | 3.395 | 6.390 | 10.987 | 5.844/2.798/16.81 | 4.750 (+0.102) | 5.624/16.66 |
| M1 mvrv | 2.588 | 3.367 | 7.824 | 11.218 | 6.192/2.588t/16.26 | 4.648 (+0.000) | 5.881/16.22 |

c=contaminated idea (formed after seeing Y4 via delay replica). t=worst tied (no strict win).
No losing dev year anywhere; all dev DD<=20. No Y4 row reaches 5.0 (max B7c 4.88, K2 4.80).

## 2. Confirm legs vs transfer (frozen §PLAN rules)

| cand | Leg1 Bybit-S5 dev4 | Leg2 pre-sample (gain>0 count) | Transfer Y4 | Gate verdict |
|---|---|---|---|---|
| C2 | PASS (+0.261; W 2.213>2.129; full 16.50) | PASS 3/4 (7/9; COVID fail) | PASS +0.106 (all-fric +) | PASS/PASS->PASS |
| K2 | MIXED (+0.083 mean; W 1.957<2.129 robust-FAIL) | N/A (pretraining contam) | PASS +0.153 (all-fric +) | robust-FAIL yet transfers |
| D1 | PASS (+0.113; W wins; full 17.26) | N/A (no pre-sample; fits rho~0 flip=NULL) | FAIL -0.057 (neg ALL frics) | **PASS->FAIL: counterexample** |
| W2 | UNKNOWN (no S5 row) | N/A (flag drift 3/24/47/25/2%) | FAIL -0.160 | no leg; fails Y4 |
| L2 | UNKNOWN | N/A (2022 data gap; Y4 unscored) | UNKNOWN | correctly unpicked (REF keeps) |
| V1 | UNKNOWN | N/A (V2 dip-leg replica FAIL -0.150) | MIXED (+0.10 Y4, 5y -0.09) | razor pick, noise |
| V2 | UNKNOWN | N/A (trails control -0.14) | MARGINAL (+0.08, exposure story) | razor pick, ~0 edge |
| AS18 | UNKNOWN | N/A (IC no sharpening) | FAIL -0.020 | no leg; fails Y4 |
| B7 | FAIL (mean +1.223 BUT full DD 20.31>20) | PARTIAL 3/4 (COVID fail) | contaminated +0.232c | DD correctly blocks Bybit |
| A1 | FAIL (-0.005; full DD 21.32>20) | N/A (XS book tilt) | Binance +0.102 / Bybit-S5 Y4 +0.024 | venue-correct reject (DD) |
| M1 | PASS-mean (+0.782; DD ok) | N/A (book gate; hurts book, governor artefact) | NEUTRAL 0.000 (never fires) | passes legs, no signal |

Pre-sample reference controls: V_GARCH 3/4, V_RV6 2/4 (both fail COVID + 2021-22).
S5 y2021 is a short window (Bybit from 2021-11-15) everywhere. All Y4 fric re-scores
are labelled diagnostics (already scored once by origin); quoted, never re-selected on.

## 3. Answer

NO — the 2 legs alone do not separate. D1 passes leg1 yet fails Y4 under every
friction (null-signal dev winner: fits rho~0 with +,-,-,+,+ flips); K2 fails strict
robust-worst on both venues yet transfers directionally (known 2021-22 weakness,
regime-dependent per oc_voltilt). Leg1 IS venue-correct: it blocks A1 (S5 DD 21.32)
and B7 (S5 full DD 20.31) for Bybit despite Binance wins. Leg2 catches crash-leg
fragility (COVID Y2020p fails C2/B7/V tilts alike) but is N/A for all 7 book-side
candidates by construction. Per frozen §5 rule (no counterexample allowed),
CONFIRM_GATE.md is NOT written. Recommendation (proposal, not ratified): 3-part gate
0) fit-credibility pre-gate (sign-stable fits, |rho|>noise, stationarity, beats
exposure-control — rejects D1/W2/AS18/V1/V2/M1 at the door) + 1) Bybit-robust + 2)
pre-sample; survivors (C2; K2 to paper with contamination caveat) match Y4 signs here.

## Leakage checklist

Features/fits/fills: inherited quoted audits only (no new timing created here).
Fit windows: no new fits; all thresholds frozen by origins pre-anchor+7d embargo.
Test-year use: Y4 quoted labelled, never a selection input here (selection = legs only).
Fill timing/costs: gate costs inside quoted engines; S5 = price-source switch only.
Blind audits quoted: audit_c2 / audit_d1 / audit_k2 / audit_cboost PASS(-WITH-NOTES).

## Vietnamese verdict

- Cổng 2 chân KHÔNG tách được: D1 qua chân Bybit (+0,11, DD đạt) nhưng thua năm sạch ở mọi ma sát (-0,02 tới -0,07, fit rho~0 đảo dấu); K2 rớt worst-year nghiêm ngặt nhưng vẫn hơn năm sạch (+0,15).
- Chân Bybit đúng theo venue: chặn A1 (DD 21,32) và B7 (DD 20,31) dù thắng trên Binance; chân pre-sample bắt đúng chân crash COVID nhưng vô hiệu với 7 ứng viên phía book.
- Kết luận: KHÔNG ban hành CONFIRM_GATE.md; đề xuất cổng 3 phần (fit-credibility + Bybit + pre-sample) — chỉ C2 (và K2 ra paper với caveat nhiễm) sống sót, khớp dấu năm sạch trong mẫu này.
