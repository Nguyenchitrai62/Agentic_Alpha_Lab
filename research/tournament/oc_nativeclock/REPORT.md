# oc_nativeclock REPORT — own fresh book signals for the shifted clocks?

Method (PLAN pre-registered, no changes): reproduce G2 (`R2B1D17BFG2`,
rule inv, k 1.0, kd 1.7, bear True, G 2.0) exactly first; audit the 6 book
members for shifted-grid computability; build NATIVE book frames (phase 0
unchanged); run REF + NATIVE through the exact v421 engine per shift via
heavy_slot. Repro: `reproduce_g2.py`, `audit_members.py`,
`build_native_books.py`, `run_nativeclock.py`; test
`tests/test_oc_nativeclock.py`. G2 reproduced to the digit (5.41 / 2.588 /
16.91 / 16.82) and the heavy replica matches `v421_runs.pkl` bit-exact
(max |diff| 0.0) before any comparison.

## Member audit (all 6 forward-filled, listed)
| member | cache | why not native |
|---|---|---|
| A | member_A_O1_orders | needs shifted-panel rebuild + per-anchor HGB refit (= retraining, forbidden); daily/funding/TV/flow/xs inputs |
| Aq | member_Aq_O1_orders | same as A + quarterly v202 refits (models not persisted) |
| B | member_B_tv | same + Deribit options-flow archive, per-anchor fit not persisted |
| Bq | member_Bq_tv | same as B + quarterly refits not persisted |
| D | members_v154[D] | same + Coinbase-1h vs Binance-spot-4h premium, per-anchor fit not persisted |
| Dq | members_quarterly_D | same as D + quarterly refits not persisted |
`models/frozen` holds only single-cutoff (2026-09-08) live models, never the
per-anchor/quarterly research fits (predictions-only caches). So NATIVE ==
REF bit-exact on all 4 shifts (max |diff| 0.0); phase 0 unchanged by
construction. Staleness confirmed: phases 1-3 trade 1/2/3 h stale books on
100% of decision bars — the hypothesised timing value is untestable without
per-anchor model persistence + full shifted-panel rebuilds.

## dev4 (selection years, 4-phase reset %/mo, DD) — REF and NATIVE identical
| year | R | DD |
|---|---|---|
| 2021-09-24 | 2.588 | 10.86 |
| 2022-09-24 | 3.282 | 16.91 |
| 2023-09-24 | 6.045 | 15.81 |
| 2024-09-24 | 10.677 | 8.27 |
| dev4 mean / worst / DD / losing | 5.601 / 2.588 / 16.91 / 0 | — |
| 2025-09-24 (recent, labelled, scored once) | 4.648 | 12.90 |
| 5y mean / full-path DD | 5.41 / 16.82 | — |

## Per-phase table (single-phase reset R/DD; official metric is the 4-phase mean)
| phase | 2021 | 2022 | 2023 | 2024 | recent |
|---|---|---|---|---|---|
| 0 (= REF, NATIVE identical) | 4.567/13.41 | 3.571/16.91 | 11.249/14.56 | 10.023/10.75 | 5.427/11.88 |
| 1 | 2.919/22.46 | 3.942/15.67 | 4.226/18.91 | 9.645/15.22 | 3.577/21.21 |
| 2 | 2.153/13.70 | 3.226/17.39 | 6.412/20.07 | 11.849/10.14 | 4.590/13.69 |
| 3 | 0.188/15.94 | 2.312/17.99 | -2.431/43.23 | 11.040/10.90 | 4.905/14.21 |
Single phases are wild (phase 3 2023: -2.43, DD 43.2) — the 4-phase mean is
what diversifies them; phase clocks are not tradeable standalone.

## Book turnover / fees (NATIVE = REF, so identical)
Turnover proxy (mean |dW|/bar, same on all shifts): 0.0203 / 0.0252 / 0.0303 /
0.0332 (dev Y0..Y3), 0.0288 recent. Engine full-path totals per phase
0/1/2/3: fills 1320/1217/1336/1209, fees 0.070/0.065/0.071/0.064,
funding 0.138/0.130/0.133/0.118 (equity units), book trades
1031/987/1038/912 @ win 0.512/0.505/0.521/0.499, dip rungs
5346/5526/5453/5188 @ win ~0.67-0.70, all-trade win ~0.64-0.67.

## Key question
**NATIVE ties G2 exactly on dev4 mean (5.601), worst year (2.588) and DD
(16.91): no timing gain is demonstrated, because no member could be natively
recomputed without retraining — the 1-3 h staleness is real (100% of shifted
bars) but its value remains untested, not disproven.**

## What failed / limits (honest)
- The core hypothesis (fresher signals add timing value) could not be
executed: per-anchor/quarterly HGB models are not persisted anywhere, and the
assignment forbids the refit that native predictions would require.
- Single-cutoff live models (2026-09-08) exist but applying them to dev years
would be leakage (trained on the test years) — not done.
- Turnover/fees per year are book-frame proxies + full-path engine totals,
not per-year engine accountings; fees/funding are inside the equity paths.
- The most-recent year (4.648/12.90) is the already-published v421 row,
re-scored once as reference and labelled; it entered no choice.

## Leakage / execution statement
Book frames at decision bar t use only standard rows r <= t (ffill; s=0
identity); truncation test asserts ffill never looks ahead. No fit used any
row >= anchor - 7d (no new fits at all — read-only caches + live-model
exclusion above). No test-year or most-recent-year statistic entered any
weight, threshold or choice (single fixed method; NATIVE==REF discovered,
not tuned). Fill timing: real `eu.simulate` (limit trade-through, no fill
minutes 0-4, stop-first, Bybit maker 0.0002/taker 0.00055, adverse long
funding 0.0001/8h) unchanged from v421. Tests: causality/truncation +
hand-checked synthetic (`tests/test_oc_nativeclock.py`, 4 passed).

## Verdict (tiếng Việt, kết luận chính)
NATIVE hòa G2 tuyệt đối (dev4 5.601, worst 2.588, DD 16.91) vì cả 6 member đều phải forward-fill — không có timing gain nào được chứng minh, không thành candidate đăng ký.
Rủi ro live thật: clock lệch vẫn trade signal cũ 1–3h trên 100% bar, phase đơn lẻ DD tới 43% — muốn test native thật phải lưu model per-anchor + rebuild panel shifted, tốn kém và vẫn có nguy cơ leakage khi refit.
Không cần prospective log cho hướng này; đóng hướng native-clock ở dạng hiện tại, nếu mở lại phải đăng ký mới với model persistence đầy đủ từ đầu.
