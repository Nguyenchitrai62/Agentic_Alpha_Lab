# oc_coinattrib REPORT — per-coin and per-side attribution of G2 (book timing + dip sleeve)

Method (PLAN pre-registered 2026-10-07, one change disclosed): book reuses
`oc_bookattrib/analyze_bookattrib.py` read-only (deployed book rows +
v421 x0.5 bear filter, 4 shifted clocks, B=sum w r, BETA/TIMING split,
block-42 x500 placebo) split PER COIN and per side; dip uses the frozen
`oc_stoptf/fills.parquet` D0 leg read-only (validated n=22312, 5y
4-phase-mean sum 7.718304 = oc_placebo_dip base to 1e-6 before use — no 1m
reload). Change: per-coin identity assert tolerance 1e-6 -> 1e-3 (rounded
outputs only; unrounded identity still holds in oc_bookattrib). Repro:
`research/tournament/oc_coinattrib/analyze_coinattrib.py` (heavy_slot) +
`tmp/coinattrib_raw.json` + `results.json`; test
`tests/test_oc_coinattrib.py`. G2 baseline reproduced to the digit
(R2B1D17BFG2 5.41/W 2.588/DD 16.91/full 16.82) before any attribution.
Book 4-phase-mean B/TIMING reproduces oc_bookattrib exactly
(2.908/3.250, 2.107/1.821, 4.617/3.353, 4.476/3.354, recent 3.357/3.361).

## Book timing per coin (4-phase mean; shares from mean timing sums, H = sum share^2)

| year | BNB | BTC | ETH | SOL | XRP | max (share) | H |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 0.205 | 0.276 | 0.107 | 0.238 | 0.174 | BTC 27.6% | 0.217 |
| 2022-09-24 | -0.002 | 0.247 | 0.059 | 0.172 | 0.525 | XRP 52.5% | 0.369 |
| 2023-09-24 | 0.183 | 0.223 | 0.296 | 0.159 | 0.138 | ETH 29.6% | 0.216 |
| 2024-09-24 | 0.095 | 0.131 | 0.187 | 0.037 | 0.551 | XRP 55.1% | 0.366 |
| 2025-09-24 (recent, labelled) | 0.336 | 0.229 | 0.210 | 0.116 | 0.109 | BNB 33.6% | 0.235 |

Per-coin TIMING_R (%/mo): 2021 [0.68,0.91,0.35,0.78,0.57]; 2022
[-0.01,0.47,0.11,0.32,0.99]; 2023 [0.63,0.75,1.01,0.54,0.47]; 2024
[0.31,0.43,0.63,0.12,1.87]; recent [1.15,0.77,0.72,0.40,0.37] (order
BNB,BTC,ETH,SOL,XRP). Per-coin placebo pct (timing vs own shuffle):
XRP 90/99/88/100/88; BTC 99/78/94/79/91; ETH 84/61/99/96/98; SOL
97/72/87/64/92; BNB 99/51/96/71/99. Sides pooled (reproduces bookattrib):
long [1.64,1.85,5.02,4.12,recent 1.85], short [1.23,0.23,-0.40,0.31,1.47].
LOCO (timing R without coin): dropping XRP cuts 2022 1.82->0.86 and 2024
3.35->1.47; dropping BTC cuts 2021 3.25->2.35; otherwise timing stays >1.3
every dev year for every single-coin drop (no single coin is the whole book).

## Dip sleeve per coin (D0 leg, 4-phase-mean S sums in w*y units; win/stop pooled over 4 phases)

| year | BNB | BTC | ETH | SOL | XRP | max (share) | H |
|---|---|---|---|---|---|---|---|
| 2021 | -0.159 | 0.300 | 0.355 | 0.570 | -0.156 | SOL 62.6% | 0.712 |
| 2022 | -0.190 | 0.101 | 0.150 | 0.177 | 0.595 | XRP 71.4% | 0.655 |
| 2023 | 0.193 | 0.293 | 0.301 | 0.765 | 0.548 | SOL 36.4% | 0.249 |
| 2024 | 0.329 | 0.442 | 0.596 | 0.663 | 1.167 | XRP 36.5% | 0.241 |
| 2025 recent | 0.267 | -0.112 | 0.065 | 0.158 | 0.299 | XRP 44.1% | 0.441 |

Win (d0>0): SOL highest 3/5y (0.73/0.73/0.76/0.74/0.67); XRP 0.69/0.76/0.78/
0.78/0.71; BTC lowest in recent (0.60). Stop+backstop rate: XRP 8.1% in 2021
(worst), BNB 7.5-7.9% in 2022-23, ~0-2% in calm 2024. LOCO dip: without SOL
2021 falls 0.91->0.34; without XRP 2022 falls 0.83->0.24; without XRP recent
falls 0.68->0.38 (XRP/BNB carry the thin recent year; BTC is negative there).
Top-5 sleeve DD episodes (pooled daily exit sums): 2023-06-01..08-17 (-3.13;
BNB -1.67 dominates), 2021-12-03..04 (-2.87; XRP -1.89), 2022-05-10..12
(-2.45; spread), 2024-04-12..13 (-2.33; BNB -0.87), 2024-01-02..03 (-2.29;
BTC -0.86). 5-episode totals: BNB -3.81 (29.2%), XRP -3.87 (29.6%), ETH
-2.26, BTC -1.74, SOL -1.37 — losses are BNB+XRP-led, no single coin >40%
of the combined DD loss (max 29.6%).

## Key question

**No single coin carries G2 in most years, but concentration spikes are real:
book timing exceeds 40% for one coin in 2/4 dev years (XRP 52.5% in 2022 and
55.1% in 2024; H 0.37/0.37 vs 0.22 in balanced years) and dip P&L exceeds 40%
in 2/4 dev years (SOL 62.6% in 2021 with BNB+XRP negative, XRP 71.4% in 2022;
H 0.71/0.65 vs 0.24-0.25 in 2023-24). The carrier rotates (BTC->XRP->ETH->
XRP for timing; SOL->XRP->SOL->XRP for dips), the recent year is balanced on
the book (max BNB 33.6%) but XRP-led on the thin dip year (44.1%), and DD
losses concentrate in BNB+XRP (59% of the top-5 episode loss). So the answer
is NO for "most years" on both legs (2/4 each, 2/5 and 3/5 with recent) —
yet XRP is the repeat offender (top timing carrier twice, top dip carrier
twice + recent) and the only coin whose removal halves a dev year's timing
(2024 3.35->1.47) or dip sum (2022 0.83->0.24).**

## What failed / limits (honest)

- Book leg is vectorised GROSS (next-open fills, no fees/funding/limit-miss/
  SL/TP); tradable book-only net is thinner (oc_bookattrib 2021 0.59 %/mo).
  Shares are of gross timing sums — net concentration could differ.
- Timing shares use additive sums; 2022 BNB is slightly negative (-0.2%),
  H exceeds naive bounds when signs disagree (dip 2021/2022 H 0.65-0.71
  reflects BNB+XRP negativity, not diversification).
- Dip sums are raw w*y units (no compounding normalisation); DD episodes use
  exit dates only (no open marks, no funding beyond timeouts) — diagnostic.
- Per-coin placebo uses seed 7+coin+1000*(shift*5+yi): deterministic but the
  2022 per-coin percentiles are weak (BNB 51%, ETH 61%, SOL 72%, BTC 78% —
  only XRP 99% beats its own shuffle), so 2022's timing is the least
  trustworthy year at coin resolution even though pooled timing is strong.

## Leakage / execution statement

w at decision bar t uses only the latest standard-grid book row r<=t (ffill;
s=0 identity); books are research fits frozen before each anchor
(research_books_d2 members); r uses next-bar opens (scoring only, never a
feature). Dip ledger is the frozen replica (strict 1m low trade-through,
close5 stop / 8sg backstop / TP1sg / timeout-next-open, maker/taker + settle
funding). No test-year or most-recent-year statistic entered any weight,
threshold or choice (single method, seeds fixed in PLAN). Fits/thresholds:
none (read-only). Fill timing: vectorised book assumes next-open (diagnostic);
dip fills are real replica fills (labelled). Tests: causality/truncation +
hand-checked synthetic (`tests/test_oc_coinattrib.py`).

## Verdict (tiếng Việt, kết luận chính)

Không coin nào gánh G2 quá 40% trong đa số năm (book 2/4 năm, dip 2/4 năm; carrier xoay vòng) nên tập trung là rủi ro đợt sóng chứ không phải phụ thuộc cấu trúc — nhưng XRP là điểm nóng lặp lại (timing 2022/2024 >52%, dip 2022 71%, DD cùng BNB gánh 59% lỗ top-5).
Rủi ro live thật: năm dip mỏng (2021BNB/XRP âm, 2022 XRP 71%, recent XRP 44%) và năm timing XRP-dẫn (2024 bỏ XRP còn 1.47) dễ gãy nếu microstructure XRP đổi (listing/ETF) — size theo book cân bằng gần đây, theo dõi riêng XRP/BNB.
Không cần hướng tune mới cho câu hỏi này; nếu muốn cắt/giảm XRP-BNB dip hay gate timing theo coin thì phải đăng ký hướng mới và chứng minh prospective, không tune trên các năm này.
