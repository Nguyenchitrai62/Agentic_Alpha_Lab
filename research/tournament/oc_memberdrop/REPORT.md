# oc_memberdrop REPORT — which book member carries G2's timing, and what does a dead feed cost?

Method (PLAN pre-registered 2026-10-07, no changes; post-hoc log still empty):
byte-logic replica of `v421/v421_gross_cap.py::worker` for `R2B1D17BFG2`
(rule inv, k 1.0, kd 1.7, bear True, G 2.0, R2 agents ON, win_start 5) on all
4 clock phases, with the book swapped per row. Blend confirmed against the
deployed code: FULL == `forward_v205.research_books_d2` (max diff 2.2e-16),
NO_CB == `research_books_o1` (1.1e-16). `research_books_d2` has no
absent-member path, so NO_FLOW/NO_CB rescale the survivors to sum to 1 as
pre-registered (NO_FLOW: B 1/3, Bq 1/3, D 1/6, Dq 1/6; NO_CB: A/Aq/B/Bq 1/4).
STALE_FLOW freezes A/Aq 72 h at the 50 pre-registered starts
(`Ay+10d+k*36.5d`, 10/year), bear filter after blending on all rows.
Repro: `research/tournament/oc_memberdrop/run_memberdrop.py`
(`--build-books`, `--shift S` via heavy_slot, `--score`); tests
`tests/test_oc_memberdrop.py` (6/6 pass). G2 baseline reproduced TO THE
DIGIT before scoring (R 5.41 / DD 16.91 / full-path 16.82, all yearly rows).

## 4-phase reset R (%/mo geometric) per year — descriptive, NO selection

| year | FULL | NO_FLOW | NO_CB | STALE_FLOW |
|---|---|---|---|---|
| 2021-09-24 | 2.588 | 2.500 | 2.640 | 2.508 |
| 2022-09-24 | 3.282 | 3.118 | 3.194 | 3.505 |
| 2023-09-24 | 6.045 | 6.326 | 5.403 | 5.917 |
| 2024-09-24 | 10.677 | 10.710 | 11.484 | 10.924 |
| 2025-09-24 (recent, labelled) | 4.648 | 5.070 | 3.895 | 4.583 |
| dev4 mean / WORST | 5.601 / 2.588 | 5.614 / 2.500 | 5.623 / 2.640 | 5.664 / 2.508 |
| 5y mean | 5.410 | 5.505 | 5.275 | 5.447 |

Yearly DD / full-path DD: FULL yearly (10.86, 16.91, 15.81, 8.27, 12.90),
full 16.82. NO_FLOW (11.61, 17.29, 15.99, 8.56, 13.44), full 17.32. NO_CB
(11.00, 17.40, 15.92, 7.69, 13.29), full 17.41. STALE (11.55, 17.00, 15.96,
8.65, 12.97), full 16.97. Book-only share: NOT separable (engine stores
t/eq/eq_min only, same as v421; no sleeve-off runs — stated in PLAN).

## Trades (4-phase sums; book episodes net of fees, same walk as v213/score_oos)

| year | FULL rungs / win | FULL book ep / win | NO_FLOW book/win | NO_CB book/win | STALE book/win |
|---|---|---|---|---|---|
| 2021 | 4075 / 63.8% | 926 / 50.3% | 955 / 49.4% | 988 / 50.4% | 908 / 49.9% |
| 2022 | 3941 / 68.9% | 861 / 51.2% | 916 / 53.7% | 869 / 53.3% | 842 / 51.1% |
| 2023 | 4977 / 73.2% | 1002 / 51.5% | 1042 / 52.2% | 1051 / 51.1% | 974 / 51.5% |
| 2024 | 3847 / 71.9% | 1163 / 50.6% | 1180 / 53.1% | 1175 / 50.4% | 1119 / 50.7% |
| 2025 (recent) | 4671 / 64.8% | 1112 / 53.8% | 1106 / 54.5% | 1137 / 51.8% | 1092 / 53.2% |

Rung counts are near-identical across rows (dip sleeve barely sees the book
change); book win rates sit 49-55% in every row/year — member choice does
not move the book win rate.

## Outage cost (STALE vs FULL; 10 x 72 h freezes/year ≈ 8.2% of time)

Yearly drag (STALE minus FULL, pp/mo): 2021 -0.080, 2022 +0.223, 2023
-0.128, 2024 +0.247, 2025 -0.065. Per-72h-episode equity cost:
+9.4 / -25.9 / +14.5 / -26.8 / +7.5 bps (mean ≈ -4 bps, i.e. sign flips
year to year). There is no measurable cost: freezing the whale-flow feed
for 3 days at a time neither helps nor hurts beyond noise.

## Key question (answer)

**Neither feed is critical — the blend is redundant, not carried by one
member.** Dropping whale-flow (NO_FLOW) moves dev4 mean by +0.01 pp/mo and
the worst dev year by -0.09 pp; dropping the Coinbase premium (NO_CB) moves
dev4 mean by +0.02 pp and the worst year by +0.05 pp; no row has a losing
year. The price of redundancy is small: full-path DD rises ~0.5 pp without
either member (16.82 -> 17.32/17.41). A 3-day flow-feed outage costs ≈ 0
(±25 bps/episode noise, sign flips). For the runbook: a stale flow feed is
NOT a stop-trading event — keep trading the last book, fix the feed within
days; do not hot-switch to a reweighted book (the tested reweightings gain
nothing and add operational risk).**

## What failed / limits (honest)

- Effect sizes (±0.02-0.06 pp/mo dev4) are phase/year noise, not signal:
  STALE "beats" FULL on dev4 (+0.06) while freezing 8% of the year — that
  is luck (2022/2024 offsets), not a finding; do not conclude staleness
  helps.
- NO_CB's most-recent year (3.895 vs FULL 4.648, -0.75 pp) is the largest
  single-year gap in the table but the year is descriptive-only (no
  selection); it slightly weakens, not strengthens, the CB member — still
  noise-sized against dev4 (+0.02).
- Book-only share genuinely not separable here (equity-only storage); the
  trade-count/win-rate split above is the closest available decomposition.
- STALE models a data freeze with the book logic otherwise intact; a real
  outage could also break execution/monitoring, which this study does not
  cover.

## Leakage / execution statement

Members are research fits frozen before each anchor (deployed provenance).
No test-year or most-recent-year statistic entered any weight, threshold or
choice (weights/formula fixed in PLAN; STALE starts are calendar formula).
Feature timing: standard rows use member values at t; shifted clocks ffill
the latest standard row r <= t_s; STALE frozen values use rows strictly < S
(truncation-tested). Fits: none (read-only). Fills: engine trade-mode
(limit trade-through, no fill minutes 0-4, stop-first, Bybit maker
0.0002/taker 0.00055, adverse long funding 0.0001/8h) unchanged from v421.
Tests: causality/truncation + hand-checked synthetic
(`tests/test_oc_memberdrop.py`, 6/6 pass, incl. the broadcast bug the suite
caught in `apply_bear` before any engine run).

## Verdict (tiếng Việt, cho runbook)

Không có feed nào là trọng yếu: bỏ whale-flow hay Coinbase-premium đều chỉ lệch dev4 ±0.03 điểm %/tháng, không năm nào lỗ, DD full-path tăng nhẹ ~0.5 điểm (16.82 → ~17.3-17.4) — blend hiện tại dư địa tốt, đừng hot-switch khi mất feed.
Outage 3 ngày của flow feed chi phí ≈ 0 (±25 bps/episode, đổi dấu theo năm — nhiễu chứ không phải tín hiệu): sổ trực ghi "feed stale ≤ vài ngày thì cứ trade book cũ, sửa feed sau", không cần dừng bot hay đổi trọng số.
Không đổi config deployed, không cần prospective log riêng cho câu hỏi này; nếu muốn cắt hẳn một member thì phải đăng ký hướng mới (tune trên các năm này bị cấm).
