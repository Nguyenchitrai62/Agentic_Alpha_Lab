# oc_bookband REPORT — book turnover and fee drag; does a no-trade band help?

PLAN frozen 2026-10-08 before any outcome; implemented exactly. REF = G2 unchanged
(v421 R2B1D17BFG2 wiring); NB10/NB25 = no-trade band p=0.10/0.25 on the bear-filtered
book target (trailing-90d mean |T| causal, flip bypass, protection/exits unchanged).

## G2 reproduction (gate to proceed)

Stored v421 runs reproduce to the digit before any overlay: 5y R 5.410, W 2.588,
max yearly DD 16.91, full-path DD 16.82; dev years R/DD (2.588/10.86), (3.282/16.91),
(6.045/15.81), (10.677/8.27); Y4 (4.648/12.90). Engine REF rerun is bit-exact on
all four shifts (eq_end 29.4873/11.3134/15.6300/3.5617, same as oc_booktwo REF).

## Part A — descriptive book turnover (4h open-to-open proxy, no selection)

Target T = deployed G2 book target (research_books_d2 + bear filter). Years
[A, A+365d), fee proxy maker 0.0002/unit turnover, gross_small = marginal d*fwd1.

| year | turnover | fee proxy | book gross* | p10: share# / shareTO | p10 net_small | p25: share# / shareTO | p25 net_small |
|---|---|---|---|---|---|---|---|
| 2021 | 43.55 | 0.0087 | 0.3007 | 76.0% / 27.1% | -0.0066 | 98.3% / 60.3% | -0.0300 |
| 2022 | 55.23 | 0.0110 | 0.2631 | 74.1% / 34.2% | -0.0019 | 96.3% / 72.9% | +0.0070 |
| 2023 | 66.39 | 0.0133 | 0.5771 | 74.3% / 33.9% | -0.0046 | 94.3% / 69.5% | +0.0043 |
| 2024 | 72.81 | 0.0146 | 0.5541 | 69.2% / 31.4% | +0.0073 | 94.3% / 70.5% | +0.0242 |
| 2025 | 62.98 | 0.0126 | 0.4264 | 68.5% / 31.6% | +0.0079 | 92.5% / 68.6% | +0.0108 |

\*4h proxy gross (sum T*fwd1), not engine P&L. Small changes are the majority of
re-targets by count (69-76% under p10, 93-98% under p25) but a minority of turnover
under p10 (27-34%). Their marginal net is negative in 2021-2023 and positive in
2024-2025 — i.e. no stable bleed to harvest. Band-path turnover saved (L1): NB10
5.1-8.6/yr, NB25 9.8-18.2/yr (fee proxy saved 0.0010-0.0036/yr).

## Part B — engine dev4 (selection basis ONLY)

4-phase reset %/mo + DD; robust pick on dev4 ONLY (eligible DD<=20, no losing year;
prefer mean>=5, then highest WORST, ties->higher mean).

| row | 2021 | 2022 | 2023 | 2024 | Rdev4 | Wdev4 | DDdev4 | book_win | fills | fees |
|---|---|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0.5114 | 3968 | 0.2070 |
| NB10 | 2.617/10.98 | 3.270/16.99 | 5.649/16.12 | 10.426/8.06 | 5.447 | 2.617 | 16.99 | 0.5116 | 3735 | 0.2022 |
| NB25 | 2.512/13.03 | 3.131/17.55 | 6.567/15.48 | 9.706/8.28 | 5.440 | 2.512 | 17.55 | 0.5079 | 3407 | 0.1957 |

Cells = R/DD per year. book_win: pooled dev4 (per-year: REF
0.5032/0.5158/0.5191/0.5082; NB10 0.4948/0.5141/0.5322/0.5055; NB25
0.4893/0.5244/0.5383/0.4838). Fills cut 5.9% (NB10) / 14.1% (NB25); fees saved
0.0048 / 0.0113 — but gross given up exceeds the saving: Rdev4 -0.154 (NB10) /
-0.161 (NB25) vs REF. DD not improved (16.99/17.55 vs 16.91). PICK (dev4 only): NB10
(highest WORST 2.617 among mean>=5 rows; margin over REF 0.029pp).

## Last year scored ONCE (REF + pick only)

| row | 2025 R/DD (scored-once) | R5 | W5 | maxDD | fullDD | book_win 5y | fills | fees |
|---|---|---|---|---|---|---|---|---|
| REF | 4.648/12.90 | 5.410 | 2.588 | 16.91 | 16.82 | 0.5169 | 5085 | 0.2692 |
| NB10 | 4.679/12.30 | 5.293 | 2.617 | 16.99 | 16.88 | 0.5156 | 4783 | 0.2626 |

NB10 last year +0.031pp/mo vs REF (noise-scale), 5y -0.117pp/mo vs REF, DD +0.08
(yearly) / +0.06 (full path), book win -0.13pp, fees saved 0.0066 over 5y. No losing
year anywhere; both rows pass the numeric gate, NB10 never beats REF on mean.

## Verdict: REJECT the band (keep G2 unchanged)

The band works mechanically (fewer fills, lower fees) but the suppressed small
changes carry roughly as much signal as cost — Part A shows their marginal net
flipped sign across years, and the engine confirms return given up > fees saved,
with no DD or win-rate gain. NB10's dev4 pick rests on a 0.029pp WORST margin and
does not transfer to a mean gain (5y -0.12pp/mo vs REF).

## Leakage statement (how checked)

Feature timing: T[t] known at bar-t close (cached members read-only);
typ[t] = mean |T| over strictly-before-t bars (shift(1) + rolling; unit test perturbs
T[t] and asserts typ[t] unchanged while typ[t+1] moves; first bar NaN = band inactive).
F[t] uses only T[t], typ[t], F[t-1] (sequential loop; truncation-tested: window capped
at 540 bars). Shifted-grid input = F ffill (latest standard row <= shifted bar, same as
v421). Label windows: fwd1 proxy is scoring-only; engine exits mechanical (no labels
fit). Fit windows: none — p=0.10/0.25, 90d/540-bar, min 120 frozen in PLAN; R2 tables
and agents pre-date all anchors. Fill timing: engine unchanged (limit fills [5,65)
strict trade-through, minute-5 ban, SL market taker / TP limit maker, stop-first, NaN
never fills). No test-year or most-recent-year statistic feeds any choice; dev pick
preceded the last stage, whose cache holds REF+NB10 only. Gate costs inside every leg.
Seam note: last-stage REF/NB10 2024 fills differ from dev-stage by 3 events (1174 vs
1171) with P&L bit-identical (10.677) — the dev run truncates the book/show-ahead
index at DEV1+4h so o1/o2 NaN at the seam; disclosed, immaterial.

## Compute

Part A + validation: direct python (4h parquets only, <<0.4 GB). Part B: 4 dev + 4
last phase-runs through heavy_slot (one job at a time), resume caches
tmp/runs_dev.pkl + tmp/runs_last.pkl. Tests: tests/test_oc_bookband.py (3 tests pass).

## Post-hoc log

- None (no definition changed after an outcome; seam fill-count note above is a
  disclosed observation, not a change).

## Vietnamese verdict (3 lines)

- GIỮ NGUYÊN G2, KHÔNG dùng no-trade band: NB10 thua REF ở trung bình 5 năm (-0,12 điểm %/tháng) mà DD và win rate không cải thiện.
- Band cắt được ~6% lệnh và một ít phí nhưng đánh mất phần gross lớn hơn; P&L biên của các thay đổi nhỏ không ổn định qua các năm.
- Hướng này đóng lại, không cần bằng chứng prospective thêm.
