# audit_mvrv COMPARISON — blind M1 replica vs oc_lit_position / oc_mvrvrobust

Verdict: **PASS-WITH-NOTES** (numbers PASS; one shared-data note, no code fault).

## Number comparison (gates: |dR| > 0.10 pp, |dDD| > 0.5 pp)

Replica (`replication.json`, saved BEFORE any of their files were opened) vs REPORTs:

| row | replica | oc_lit_position REPORT | oc_mvrvrobust REPORT | max diff |
|---|---|---|---|---|
| M1 dev4 R / W / DD | 6.192 / 2.588 / 16.26 | 6.192 / 2.588 / 16.26 | 6.192 / 2.588 / 16.26 | 0.00 / 0.00 |
| M1 5y R / DD / full | 5.881 / 16.26 / 16.22 | 5.881 / 16.26 / 16.22 | 5.881 / 16.26 / 16.22 | 0.00 / 0.00 |
| M1 yearly R | 2.588, 3.367, 7.824, 11.218, 4.648 | same (incl. 2025 byproduct) | same (dev4 + silent 2025) | 0.00 |
| M1 yearly DD | 10.86, 16.26, 13.73, 9.99, 12.90 | same | — (dev4 DD 16.26) | 0.00 |
| CTRL_M1 dev4 / 5y | 5.735 / 5.519, DD 17.00 | 5.735 / 5.519, DD 17.00 | — | 0.00 |
| Gated exposure | 0.0 / 3.25 / 45.37 / 6.41 / 0.0% | 0 / 3.3 / 45.4 / 6.4 / 0% | 750 gated bars | exact (750 bars) |
| Control means | 1.0 / 0.9837 / 0.7732 / 0.9679 / 1.0 | 1.0 / 0.984 / 0.773 / 0.968 | — | rounding only |

All diffs are 0.00 — far inside the R 0.10 pp / DD 0.5 pp mismatch gates. G2 reproduced to
the digit first on both sides (5.41 / 2.588 / 16.91 / full 16.82).

## Signal-code audit (look-ahead)

Read `oc_lit_position/signals.py` (H8 part) and `oc_mvrvrobust/signals_mvrv.py` AFTER
saving `replication.json`; cross-checked numerically
(`test_crosscheck_lit_position_signal_identical`: max |dz| == 0.0 over 10951 finite bars,
750 gated bars both sides):

- MVRV availability: day D usable from D+1 02:00 UTC (`H8_AVAIL = 26h`, searchsorted
  right-1 on avail) — correct, matches PLAN; no same-day use.
- Rolling window end: pandas trailing `rolling(win, min_periods=180)` on the daily series,
  i.e. days <= D ending at D inclusive — causal; no future-day input. (Their H6 leg uses
  `.shift(1)` strictly-pre-T; H8 needs no shift because the D+1 02:00 lag already excludes D
  from intraday T on day D.)
- No use of future days anywhere in the H8 path (as-of mapping only looks backward).
- `CapMVRVCur` interpreted as the ratio itself — correct (values 0.75..3.96; a USD cap ratio
  would be ~1e12 scale, and both manifests agree).
- Engine application: gate on STANDARD rows with bear-filtered weight > 0, after the bear
  filter, before shifted-clock ffill; pre-2021-09-24 rows forced to NaN->1 (CUTOFF mask) —
  matches PLAN/v426; `win_start=5` + trade-through + stop-first preserved (G2 bit-exact).

## CoinMetrics revision note (shared-data caveat, not a code fault)

- `data/raw/onchain_20260924/manifest.json` shows ONE pull (2019-01-01..2026-09-23, 2823 rows,
  sha256 e64aca4f...): yes, `btc.csv` is a single vintage downloaded 2026-09-24.
- Realised cap is derived from full UTXO history and CoinMetrics does restate history
  (methodology/supply-heuristic fixes); a final-vintage backtest therefore computes early
  z-scores with values as-revised, not as-known-then — a vintage look-ahead distinct from the
  (clean) timestamp handling above.
- Likely bias: small — the gate is relative (z vs trailing 365d, so level shifts partly
  cancel) and fires mostly in 2023-24 (recent, less-revised history); but it is unquantified
  here because no archived vintages exist in the repo. It biases all three implementations
  identically (shared file), so it does not change this PASS; the clean fix is a prospective
  paper log on live vintages (or archived-vintage replay), never a refit on this file.

## Vietnamese verdict (3 lines)

- PASS: tái tạo mù khớp tuyệt đối cả hai báo cáo (mọi chênh lệch R/DD đều 0,00, ngưỡng 0,10/0,5) và audit code không phát hiện rò rỉ thời gian (D+1 02:00, cửa sổ trailing, áp gate sau bear-filter đúng PLAN).
- Ghi chú duy nhất: btc.csv là một vintage duy nhất tải ngày 2026-09-24 nên giá trị MVRV lịch sử có thể đã bị sửa hồi tố (realised-cap revisions) — rủi ro vintage chung cho cả ba bản, không làm đổi kết quả PASS nhưng không lượng hóa được nếu thiếu vintage lưu trữ.
- Đề xuất: giữ nguyên M1 như đã kiểm chứng, mọi bằng chứng tiếp theo lấy từ paper-log prospective trên vintage trực tiếp, không dùng file này để tinh chỉnh thêm.
