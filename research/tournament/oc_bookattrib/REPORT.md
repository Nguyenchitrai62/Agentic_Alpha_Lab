# oc_bookattrib REPORT — where does the deployed G2 BOOK's return come from?

Method (PLAN pre-registered, no changes): v421 pickle stores only
`t/eq/eq_min` per phase (verified) so the engine's book P&L is NOT separable —
book-only engine run instead (G2 with dip sleeve OFF, 4 phases, heavy_slot),
plus vectorised gross attribution `B=sum w r` with w = `research_books_d2`
after the v421 x0.5 bear filter ffill'd to each shifted clock and r =
next-bar open-to-open on that shift's prep opens. Repro:
`research/tournament/oc_bookattrib/analyze_bookattrib.py` (G2 validation +
vectorised) and `run_bookonly.py` (heavy engine); test
`tests/test_oc_bookattrib.py`. G2 baseline reproduced to the digit
(R2B1D17BFG2 5.41/W 2.588/DD 16.91/full 16.82) before any attribution.

## Vectorised gross, 4-phase mean monthly R (dev Y0..Y3 + most-recent labelled)

| year | B gross | BETA | TIMING | long | short | nobear | bear gain | placebo pct | mkt beta |
|---|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 2.908 | -0.343 | 3.250 | 1.644 | 1.233 | 2.569 | +0.339 | 100.0 | 0.055 |
| 2022-09-24 | 2.107 | 0.269 | 1.821 | 1.850 | 0.228 | 2.697 | -0.590 | 96.8 | 0.136 |
| 2023-09-24 | 4.617 | 1.227 | 3.353 | 5.022 | -0.399 | 4.641 | -0.025 | 100.0 | 0.122 |
| 2024-09-24 | 4.476 | 1.080 | 3.354 | 4.119 | 0.310 | 4.628 | -0.152 | 100.0 | 0.109 |
| 2025-09-24 (recent, labelled) | 3.357 | -0.010 | 3.361 | 1.851 | 1.466 | 3.848 | -0.492 | 100.0 | 0.057 |

Per-phase detail in `tmp/attrib_raw.json`: all 4 shifts agree (TIMING
1.68–3.53 every phase-year; placebo ≥96.2% every phase-year; beta −0.35–+1.24).
Daily regression: alpha_d t = 1.6–2.9 (positive all 5y), beta t significant
2021–2024 (1.7–3.9), insignificant in the most-recent year (0.8–1.1).

## Book-only engine net (sleeve=False, tradable, 4-phase reset + full-path DD)

| year | net R %/mo | DD % |
|---|---|---|
| 2021-09-24 | 0.585 | 9.76 |
| 2022-09-24 | 1.992 | 10.59 |
| 2023-09-24 | 2.818 | 14.60 |
| 2024-09-24 | 3.854 | 9.42 |
| 2025-09-24 (recent) | 3.438 | 10.24 |
| 5y mean / full-path DD | 2.531 | 18.96 |

Vectorised gross 5y mean 3.489 vs book-only net 2.531 (gap ≈1pp =
fees/funding/limit-miss/SL/TP/governor). Gap is largest in 2021 (2.91→0.59);
the most-recent year matches (3.36→3.44). Book-only DD 18.96 exceeds G2-total
16.82 — the dip sleeve diversifies the book's drawdown.

## Key question

**The book's return is mostly TIMING, not beta: timing is positive in every
year including the bear years (2021 +3.25, 2022 +1.82 %/mo gross) with
placebo percentiles ≥95% in all five years (96.8–100%), market beta is only
0.05–0.14, and even in the 2023–2024 bull years beta is ~1.1–1.2 of ~4.5–4.6
total (~25%) with timing carrying ~75%. Longs earn every year; shorts earn in
4 of 5 years (2023 shorts −0.40). The x0.5 bear filter helps only 2021
(+0.34pp) and costs 0.03–0.59pp in the other four years.**

## What failed / limits (honest)

- Vectorised gross is NOT tradable: no fees/funding/limit-misses/SL/TP; the
  book-only engine is the tradable reference and is much thinner in 2021
  (0.585 %/mo). Do not size on gross.
- 2023 shorts lose money; the bear filter is net-negative outside 2021 —
  both are candidates to cut, but that would be tuning on these years, so no
  change is made here.
- Daily alpha annualises to 26–58% mechanically (daily compounding); read it
  as a sign/t-stat statement (t 1.6–2.9), not a return promise.
- No discrete trade counts/win rates for the vectorised leg (continuous
  weights); engine-leg events were not stored (equity only, same as v421).

## Leakage / execution statement

w at decision bar t uses only the latest standard-grid book row r≤t (ffill;
at s=0 identity); books are research fits frozen before each anchor
(research_books_d2 members); r uses next-bar opens (forward return for
scoring only, never as a feature). No test-year or most-recent-year
statistic entered any weight, threshold or choice (single method, seed 7
fixed in PLAN). Fits/thresholds: none in this study (weights read-only).
Fill timing: vectorised assumes next-open fills (diagnostic); engine leg uses
real trade-mode fills (limit trade-through, no fill minutes 0–4, stop-first,
Bybit maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h) unchanged
from v421. Tests: causality/truncation + hand-checked synthetic
(`tests/test_oc_bookattrib.py`).

## Verdict (tiếng Việt, kết luận chính)

Book G2 sống bằng timing chứ không phải beta (timing dương cả 5 năm, placebo ≥96.8%, beta thị trường chỉ 0.05–0.14; năm bull beta góp ~25%).
Rủi ro live thật: book-only net chỉ 0.59%/tháng năm 2021 và DD 18.96 (cao hơn cả G2), gross phóng đại ~1 điểm — đừng size theo gross, bear market vẫn ăn timing nhưng mỏng và dễ gãy hơn nghiên cứu thể hiện.
Không cần prospective log riêng cho câu hỏi beta-vs-timing này; nếu muốn cứu 2021/short-2023 hay cắt bear-filter thì phải đăng ký hướng mới, không tune trên các năm này.
