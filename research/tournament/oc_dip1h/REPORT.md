# oc_dip1h REPORT (2026-10-08) — 1h-grid dip sleeve next to G2

Assignment: docs/opencode/OPENCODE_W_oc_dip1h.md (+ COMMON 20261007). Method
frozen in PLAN.md BEFORE any outcome; exactly two pre-registered variants
(H05 = 0.5x G2 rung size, H025 = 0.25x). No post-outcome changes (no extra rows).
Results: `results.json` (this folder). Code: `dip1h_core.py`, `run_dip1h.py`.
Tests: `tests/test_oc_dip1h.py` (10 passed).

## G2 baseline (gate to proceed)
f=0 overlay reproduces `v421_result.json` R2B1D17BFG2 TO THE DIGIT
(years 2.588/3.282/6.045/10.677/4.648, DDs, 5y R 5.41, full-path DD 16.82).
Overlay method = oc_carrycompound UTA: A(t)=A(t-1)(1+r_bot(t))+dSleeve(t).

## Standalone 1h sleeve, own capital (per-year reset to 1.0)
20,870 rungs total (all finite). Exit split 5y: TP 10,471 (50.2%) / timeout
8,705 (41.7%) / stop 1,694 (8.1%). Pooled win (ret>0) 63.9%.

| year | H05 %/mo | H05 DD | H05 trades/win/fee% | H025 %/mo | H025 DD | H025 trades/win/fee% |
|---|---|---|---|---|---|---|
| 2021-09-24 | +0.736 | 3.58 | 3981 / 61.9% / 13.2% | +0.371 | 1.80 | 3981 / 61.9% / 13.2% |
| 2022-09-24 | -0.061 | 7.43 | 4207 / 66.8% / 14.2% | -0.027 | 3.77 | 4207 / 66.8% / 14.2% |
| 2023-09-24 | +0.140 | 9.20 | 4559 / 68.1% / 14.3% | +0.076 | 4.67 | 4559 / 68.1% / 14.3% |
| 2024-09-24 | +1.290 | 3.75 | 3829 / 62.4% / 15.0% | +0.645 | 1.88 | 3829 / 62.4% / 15.0% |
| post 2025-09-24 (once, labelled) | +0.196 | 5.61 | 4290 / 60.0% / 20.1% | +0.101 | 2.83 | 4290 / 60.0% / 20.1% |
| dev4 mean/WORST/DD/losing | 0.525 / -0.061 / 9.20 / 1 | | | 0.266 / -0.027 / 4.67 / 1 | | |
| 5y mean | 0.459 | | | 0.233 | | |

Standalone verdict: ~0.3-0.5 %/mo, an order of magnitude below the 5% goal,
with a losing dev year (2022). High win rate, negative skew: 8% of rungs stop
out at -4 sigma and erase the fifty 1-sigma TPs. Fee share 13-20% of gross.

## Combined with G2 (reset years; full-path DD continuous v421 convention)
2x cap: 0 skips in every row (max sleeve gross 0.80x H05 / 0.40x H025, cap vacuous).

| row | dev4 %/mo | dev4 WORST | dev4 DD | dev4 losing | 5y %/mo | full-path DD |
|---|---|---|---|---|---|---|
| G2 | 5.601 | 2.588 | 16.91 | 0 | 5.410 | 16.82 |
| G2+H05 | 5.290 | 2.245 | 21.56 | 0 | 4.971 | 21.56 |
| G2+H025 | 5.450 | 2.421 | 19.26 | 0 | 5.194 | 19.21 |

Per-year G2+H025 vs G2: 2021 2.421/2.588, 2022 2.914/3.282, 2023 5.891/6.045,
2024 10.780/10.677, post 4.178/4.648 (once, labelled).

Robust pick on dev4 ONLY: G2+H05 ineligible (DD 21.56 > 20). G2+H025 eligible
but loses to G2 on every leg (mean 5.450 < 5.601, WORST 2.421 < 2.588,
DD 19.26 > 16.91). **Pick: G2 alone (no 1h sleeve).**

Daily-return correlation (00 UTC grid) sleeve vs G2: dev4 Pearson +0.25
(n=1461), post +0.03 (n=365, labelled). Not uncorrelated where it matters:
sleeve stops cluster in the same selloffs that drive G2's drawdown, so the
overlay deepens the 2022 DD (16.91 -> 19.26/21.56) instead of diversifying it.

## Why it failed
1. Hourly dips have no edge at G2's geometry: 1-sigma TPs win often (64%) but
   4-sigma stops (-1% to -2% of notional each) dominate the expectation.
2. The sleeve needs the 4h context it was stripped of (B1 correlation guard,
   learned size/TP agents, risk budget, governor) — fixed fractions on a 1h
   grid keep the worst fills.
3. Positive stress correlation (+0.25 dev4) means it adds DD exactly in G2's
   worst year rather than offsetting it.

## Leakage checks (how each was verified)
- Feature timing: sigma1h = rolling std of hourly log returns SHIFTED by 1
  (`dip1h_core.sigma1h_causal`; test_sigma_excludes_current_and_future_bars);
  bids use the bar open only.
- Label windows: n/a — no labels, no fits, no thresholds; every parameter was
  copied from G2 config/gate costs in PLAN.md before any outcome.
- Fit windows: none (no fitted object exists in this direction).
- Fill timing: strict trade-through (`low < bid`, equality test), minutes 0..4
  excluded (test), exits scanned from f+1 only (test), stop-before-TP each
  minute incl. ties (test), timeout at the next 1h open, funding only on
  timeout exits spanning a 00/08/16 UTC settlement.
- Selection hygiene: variants and criterion frozen in PLAN.md; dev4-only pick;
  post year scored once and labelled, never used to choose.

## Engineering
Heavy 1m pass via `heavy_slot --tag oc_dip1h --min-free-gb 2.0` (one coin at
a time, float32; 43,812 bars x 5 coins, 20,870 rungs; 10-minute progress
prints armed, run finished in seconds so none triggered). pytest:
`.venv/Scripts/python.exe -m pytest tests/test_oc_dip1h.py -q` — 10 passed.
Known bounds (labelled): standalone DD is hourly-close DD (1m-marked intrabar
excursion bounded by ~1-2% — every rung carries a 4-sigma stop); G2 gross in
the 2x cap proxied as constant 1.0x (v421 runs store no exposure); everything
cut at g1 = 2026-09-23 12:00 UTC (G2 grid end), post year ~364.5d labelled.

## Vietnamese verdict
- KHÔNG áp dụng sleeve 1h cho G2: lợi nhuận riêng chỉ ~0,3-0,5%/tháng, năm 2022 lỗ, ghép vào G2 làm giảm lãi và tăng DD vượt ngưỡng (H05 DD 21,56).
- Tương quan stress dương (+0,25) nên sleeve không đa dạng hóa mà còn đào sâu DD đúng năm G2 xấu nhất; hướng này nên đóng lại.
- Không cần bằng chứng prospective thêm: kết quả âm rõ ràng trên cả dev4 và năm cuối, giữ nguyên G2 hiện tại.
