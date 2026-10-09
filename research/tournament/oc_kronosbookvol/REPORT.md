# oc_kronosbookvol REPORT: book exposure scaled by Kronos forecast volatility

4-phase BOT engine on top of G2 (v421 R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True,
G 2.0). Per-shift Kronos rows feed their own phase (shift s -> phase s, latest row
T <= bar open); books_bear x m with m = clip(median_train/median f, 0.6, 1.4), BOTH
long and short. G2 reproduced from cache first: 5.41 / 16.91 / 16.82 exact.
Full numbers in results.json. Two stages: dev (KV1/KV2, last year never run) -> pick
KV2 on dev4 -> full-period runs for KV2+CTRL scored ONLY on the last year.

## 1. Dev4 selection (anchors 2021-2024; UPPER BOUND — Kronos pretraining covers dev)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | dev4 R | dev4 W | dev4 DD | dev fullDD | book_win |
|---|---|---|---|---|---|---|---|---|---|
| G2 (cache) | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82* | — |
| KV1 (vol1) | 2.185/12.00 | 3.289/18.65 | 6.722/16.61 | 11.188/9.01 | 5.788 | 2.185 | 18.65 | 18.57 | 0.5098 |
| KV2 (rng1) | 2.273/12.96 | 2.497/18.77 | 6.651/16.65 | 10.790/9.17 | 5.496 | 2.273 | 18.77 | 18.67 | 0.4955 |

*G2 fullDD over the full path (cache). Both KV rows eligible (DD <= 20, no losing
year; both means >= 5); robust criterion picks the highest dev4 WORST year: KV2
(2.273 > 2.185). Choice frozen before stage 2. Note: KV1's small mean edge came
with a worse worst-year and worse DD than G2 — the pattern that failed to transfer
in v189-v197.

## 2. Most-recent-year clean test (2025-09-24 .. 2026-09-23, post-Kronos-release; scored ONCE)

| row | last-year R (%/mo) | last-year DD | y4 book_win (trades) | y4 win_all |
|---|---|---|---|---|
| G2 (cache) | 4.648 | 12.90 | — | — |
| KV2 chosen (rng1) | 4.563 | 11.48 | 0.5440 (1261) | 0.6252 |
| CTRL (sigma42/sigma) | 4.597 | 11.10 | 0.5478 (1099) | 0.6281 |

5y context: G2 5.410/W 2.588/DD 16.91/full 16.82; KV2 5.308/2.273/18.77/18.67;
CTRL 5.473/2.513/17.78/17.82. Multiplier active everywhere (scaled share 1.000,
mean |m-1| ~0.22 both rows) — the overlay is binding, just not helpful.

## 3. What failed and why

Kronos rng1 scaling does not beat the cheap trailing baseline on the clean year
(4.563 < 4.597) and is marginally below unscaled G2 (4.648), while 5y DD is worse
than G2 (18.67 vs 16.82). The dev edge (KV1 mean +0.19pp, KV2 worst-year still below
G2's) did not survive post-release data — consistent with the REPORT.md caveat that
dev ICs are inflated by pretraining overlap. No post-hoc change: definitions, clip,
medians and the pick are exactly as PLAN.md; stage-2 KV2 dev years bit-match stage 1.

## 4. Leakage checks

Feature timing: Kronos row at T uses bars closed <= T; lookup latest T <= bar open t
(tests prove truncation/shift isolation; engine path == tested single-point math).
Fit windows: medians per (anchor, shift, sym) from rows with T < A - 7d only.
Fill timing: untouched engine (win_start 5, trade-through, stop-first, gate costs
maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h).

## Verdict (Vietnamese, 3 lines)

Từ chối áp dụng vol-scaling Kronos cho book: trên năm sạch (sau phát hành) KV2 đạt 4,563%/tháng,
thua cả baseline rẻ trailing (4,597%) lẫn G2 gốc (4,648%) trong khi DD 5 năm tệ hơn (18,67 so với 16,82).
Lợi thế nhỏ trên dev không chuyển sang dữ liệu post-release — đúng cảnh báo pretraining overlap; giữ nguyên G2, khép hướng này.
