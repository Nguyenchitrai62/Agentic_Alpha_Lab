# oc_dipdaily REPORT (2026-10-08) — a SLOWER dip sleeve on the daily grid next to G2

Assignment: docs/opencode/OPENCODE_W_oc_dipdaily.md (+ COMMON 20261007). Method
frozen in PLAN.md BEFORE any outcome; exactly two pre-registered variants
(D05 = 0.5x G2 rung size, D025 = 0.25x). No post-outcome changes (no extra rows).
Results: `results.json` (this folder). Code: `dipdaily_core.py`,
`run_dipdaily.py`, `run_dipdaily_pass2.py`. Tests: `tests/test_oc_dipdaily.py`
(13 passed).

## G2 baseline (gate to proceed)
f=0 overlay reproduces `v421_result.json` R2B1D17BFG2 TO THE DIGIT
(years 2.588/3.282/6.045/10.677/4.648, DDs, 5y R 5.41, full-path DD 16.82).
Overlay method = oc_carrycompound/oc_dip1h UTA: A(t)=A(t-1)(1+r_bot(t))+dSleeve(t).

## Standalone daily sleeve, own capital (per-year reset to 1.0)
786 rungs total (all finite) — fewer, larger fills than the 1h sleeve (20,870).
Exit split 5y: TP 479 (60.9%) / timeout 243 (30.9%) / stop 64 (8.1%).
Pooled win (ret>0) 76.0%. Win rises with depth (k=2.5: 71%, k=4.0: 88%).
Fee share 1.5–4.2% of gross (vs 13–20% for the 1h sleeve — fees matter less).

| year | D05 %/mo | D05 DD | D05 trades/win/fee% | D025 %/mo | D025 DD | D025 trades/win/fee% |
|---|---|---|---|---|---|---|
| 2021-09-24 | +1.024 | 0.66 | 163 / 81.0% / 1.5% | +0.512 | 0.33 | 163 / 81.0% / 1.5% |
| 2022-09-24 | +0.056 | 1.90 | 136 / 67.6% / 2.6% | +0.028 | 0.95 | 136 / 67.6% / 2.6% |
| 2023-09-24 | +0.924 | 0.00 | 222 / 87.8% / 2.1% | +0.462 | 0.00 | 222 / 87.8% / 2.1% |
| 2024-09-24 | +0.451 | 0.22 | 130 / 75.4% / 2.6% | +0.225 | 0.11 | 130 / 75.4% / 2.6% |
| post 2025-09-24 (once, labelled, 363 traded opens) | -0.416 | 6.21 | 135 / 59.3% / 4.2% | -0.203 | 3.11 | 135 / 59.3% / 4.2% |
| dev4 mean/WORST/DD/losing | 0.613 / 0.056 / 1.90 / 0 | | | 0.307 / 0.028 / 0.95 / 0 | | |
| 5y mean | 0.406 | | | 0.204 | | |

Standalone verdict: ~0.3–0.6 %/mo, high win rate (76%), no losing dev year —
but an order of magnitude below the 5% goal, and LOSING in the post year.

## Pre-sample 2017–2020, standalone (labelled; SPOT 1m, perp gate costs; SOL absent)

| leg | D05 %/mo | D05 DD | trades/win | D025 %/mo | D025 DD | trades/win |
|---|---|---|---|---|---|---|
| Y2017 (77d) | +2.068 | 0.00 | 30 / 100% | +1.031 | 0.00 | 30 / 100% |
| Y2018 | +0.740 | 0.28 | 112 / 76.8% | +0.370 | 0.14 | 112 / 76.8% |
| Y2019 | +0.544 | 0.00 | 102 / 74.5% | +0.272 | 0.00 | 102 / 74.5% |
| Y2020p (244d, incl. COVID crash) | -0.963 | 12.04 | 97 / 59.8% | -0.465 | 6.08 | 97 / 59.8% |

Pre-sample exit split: TP 61.9% / timeout 29.3% / stop 8.8%, pooled win 73.3%.
Three of four legs positive, but the COVID-crash leg loses ~1 %/mo with a 12%
DD: without a backstop, the daily sleeve eats the biggest flushes.

## Combined with G2 (reset years; full-path DD continuous v421 convention)
2x cap: 0 skips in every row (max sleeve gross 0.80x D05 / 0.40x D025, cap vacuous;
G2 gross proxied 1.0x, disclosed).

| row | dev4 %/mo | dev4 WORST | dev4 DD | dev4 losing | 5y %/mo | full-path DD |
|---|---|---|---|---|---|---|
| G2 | 5.601 | 2.588 | 16.91 | 0 | 5.410 | 16.82 |
| G2+D05 | 6.192 | 3.259 | 16.33 | 0 | 5.794 | 16.48 |
| G2+D025 | 5.897 | 3.065 | 16.62 | 0 | 5.603 | 16.53 |

Per-year G2+D05 vs G2: 2021 3.541/2.588, 2022 3.259/3.282, 2023 7.052/6.045,
2024 11.105/10.677, post 4.215/4.648 (once, labelled).

Robust pick on dev4 ONLY: all three eligible (DD <= 20, no losing year, mean
>= 5 %/mo); highest dev4 WORST-year monthly return wins → **G2+D05**
(WORST 3.259 > 3.065 > 2.588; mean 6.192 highest; DD 16.33 lowest).

Daily-return correlation (00 UTC grid) sleeve vs G2: dev4 Pearson **-0.16**
(n=1461) — the only sleeve so far that is NEGATIVELY correlated with G2 where
it matters (1h sleeve: +0.25). Post year +0.17 (n=357, labelled).

## Why it helped on dev4 — and why it still cannot be adopted
1. Wider TPs (1 daily sigma ≈ several 4h sigmas) with rare fills (786 in 5y):
   61% TP at 76% win, fee share < 5%. The negative dev4 correlation (-0.16)
   means it offsets G2's drawdown instead of deepening it (dev4 DD 16.91→16.33,
   full-path 16.82→16.48).
2. BUT the post year drags: combined -0.43pp (4.215 vs 4.648) with DD 17.88 vs
   12.90 (+5pp). The sleeve standalone lost -0.42 %/mo in the post year.
3. AND the COVID leg (Y2020p) lost -0.96 %/mo with DD 12.04. Both negative
   episodes are flush/crash episodes: the no-backstop touch stop does not
   protect the daily sleeve when the flush keeps flushing — it buys all the
   way down and stops out at -4 sigma per rung.
4. The lift is small in absolute terms (+0.59pp dev4 on top of 5.6): two
   independent stress episodes already overturn the sign of the sleeve's own
   return. This is fragile, not robust.

## Leakage checks (how each was verified)
- Feature timing: sigma1d = rolling std of daily log returns SHIFTED by 1
  (`dipdaily_core.sigma1d_causal`; test_sigma_excludes_current_and_future_bars);
  bids use the day open only; every main-window bar has the full 120-day window.
- Label windows: n/a — no labels, no fits, no thresholds; every parameter was
  copied from G2 config/gate costs/oc_dip1h readings in PLAN.md before any outcome.
- Fit windows: none (no fitted object exists in this direction).
- Fill timing: strict trade-through (`low < bid`, equality test), minutes 0..4
  excluded (test), exits scanned from f+1 only (test), stop-before-TP each
  minute incl. ties (test), timeout at the next daily open (test), funding only
  for settlements strictly inside (fill, exit] (count_settlements tests).
- Selection hygiene: variants and criterion frozen in PLAN.md; dev4-only pick;
  post year and pre-sample scored once and labelled, never used to choose.

## Engineering
Heavy 1m pass via `heavy_slot --tag oc_dipdaily --min-free-gb 2.0` (one coin at
a time, float32; 1,825 traded days x 5 coins + 4 pre-sample coins; 10-minute
progress prints armed, run finished in ~15s so none triggered; log tmp/run_all.log).
Main window: 0 skipped days (all 1440 minutes + next open present everywhere).
Pre-sample skips (warm-up/sigma/partial days): BTC 29, ETH 37, BNB 27, XRP 15.
pytest: `.venv/Scripts/python.exe -m pytest tests/test_oc_dipdaily.py -q` — 13 passed.
Known bounds (labelled): standalone DD is daily-close DD (1m-marked intrabar
excursion bounded by the 4-sigma touch stop on every rung); G2 gross in the 2x
cap proxied as constant 1.0x (v421 runs store no exposure); post year covers
363 traded opens (last 2026-09-22); pre-sample fills/exits on SPOT prices.

## Vietnamese verdict
- Chọn dev4 là G2+D05 (+0,59pp mean, WORST 2,59→3,26, DD 16,91→16,33, tương quan dev4 −0,16 đa dạng hóa thật), nhưng KHÔNG áp dụng ngay.
- Năm gần nhất kéo lãi xuống −0,43pp và tăng DD thêm 5pp; chân COVID 2020 lỗ −0,96%/tháng DD 12% — sleeve thủng đúng những đợt flush cần bảo vệ.
- Cần bằng chứng prospective (paper log) trước khi bàn adoption; đóng không gian variant của hướng này (đã dùng 2/2 variant), giữ nguyên G2 hiện tại.
