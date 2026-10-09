# oc_convttl REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS8 #7 (rank 7): conviction-dependent order TTL — order price/offsets frozen (G2 deployed
vol-scaled `max(0.10%,0.25*sigma4h)`); TTL = 2 bars if |w_base| > pre-anchor quantile else 1 bar.
V1 threshold median, V2 p75. One placement, no re-peg, expire unfilled. In-position scale orders keep
uniform n_valid=2; SL/TP unchanged. HOW LONG one signal's single price rests, not WHERE the price sits
(CLOSED `oc_bookoffset` vol-scaled SINGLE offset, `oc_booktwo` two-price ladder kept as distinct).

STATUS: DONE. G2 reproduced to the digit first (5.41 / 16.91 / 16.82, dev years + Y4 exact). 4-phase
engine dev (REF+V1+V2+C_V1+C_V2) + scored-once last year (REF+V1 only). NULL result: V1 beats G2 by
+0.014pp/mo on dev4 mean and +0.030pp on the scored-once year with matching WORST and +0.01 DD, but
loses to its own exposure-matched constant control by -0.22pp dev4 mean; book win rate drops. Direction
closed in this form (timing adds nothing beyond a dumb trim).

## G2 reproduction (binding gate, passed)

REF (unpatched engine) reproduces v421 R2B1D17BFG2 to the digit, dev + last:
R/DD per year [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] +
Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82. No overlay; overlay path not
needed (book-entry mechanism, not an equity overlay).

## Thresholds (frozen, pre-anchor + 7d embargo, non-zero |w_base| pooled)

| year | q50 | q75 | pV1 (long share) | sV1 | pV2 | sV2 |
|---|---|---|---|---|---|---|
| 2021 | -1.0 (inactive: grid starts 2021-09-24, empty pool) | -1.0 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| 2022 | 0.036617 | 0.061839 | 0.6762 | 0.8381 | 0.5099 | 0.7549 |
| 2023 | 0.047048 | 0.084965 | 0.6813 | 0.8406 | 0.3714 | 0.6857 |
| 2024 | 0.054884 | 0.092891 | 0.5271 | 0.7636 | 0.3206 | 0.6603 |
| 2025-09-24.. (scored-once) | 0.055696 | 0.096170 | 0.4847 | 0.7423 | 0.2547 | 0.6274 |

s = (1+p)/2 = realised mean-TTL weight scale for the diagnostic constant controls
(C rows use test-year p, so NOT tradable, NOT eligible).

## Per-year table (4-phase reset %/mo geometric, max yearly DD; Y4 scored ONCE for the dev4 pick + REF only, labelled)

| year | REF R / DD | V1 R / DD (diff) | V2 R / DD (diff) | C_V1 (diag) | C_V2 (diag) |
|---|---|---|---|---|---|
| 2021 dev | 2.588 / 10.86 | 2.588 / 10.86 (+0.000) | 2.588 / 10.86 (+0.000) | 2.588 / 10.86 | 2.588 / 10.86 |
| 2022 dev | 3.282 / 16.91 | 3.255 / 16.92 (-0.027) | 3.126 / 17.09 (-0.156) | 3.088 / 16.79 | 2.872 / 16.65 |
| 2023 dev | 6.045 / 15.81 | 6.057 / 15.83 (+0.012) | 5.998 / 15.79 (-0.047) | 7.209 / 15.79 | 8.147 / 15.59 |
| 2024 dev | 10.677 / 8.27 | 10.751 / 8.27 (+0.074) | 10.885 / 8.27 (+0.208) | 10.654 / 10.06 | 10.789 / 11.04 |
| 2025-09-24..2026-09-23 scored-once | 4.648 / 12.90 | 4.678 / 13.11 (+0.030) | — (not run; discipline) | — | — |

- dev4 robust pick (DD<=20, no losing dev year; prefer mean>=5, highest WORST,
  ties→mean): REF (5.601/2.588/16.91) vs V1 (5.615/2.588/16.92) vs V2 (5.599/2.588/17.09) —
  all eligible, all mean>=5, WORST ties at 2.588 (2021 inactive by construction), V1 wins on mean.
  PICK = V1.
- 5y (dev4 pick + REF, scored-once Y4): REF 5.410 / W 2.588 / maxDD 16.91 /
  full-path DD 16.82; V1 5.427 / W 2.588 / maxDD 16.92 / full-path DD 16.83
  (deltas +0.017 / +0.000 / +0.01 / +0.01). No losing year anywhere.
- V1 beats REF in 2/4 dev years (2023 +0.012, 2024 +0.074), loses 2022 (-0.027), ties 2021.
  V2 beats REF in 1/4 (2024 +0.208) and loses two years. Neither moves WORST (all 2.588).
- Controls (reported, NOT eligible): dev4 C_V1 5.834 (+0.219 over V1), C_V2 6.042 (+0.443 over V2).
  The dumb uniform trim at the variant's realised mean scale beats the conviction-selective expiry by
  ~15-30x the variant-vs-REF gap. Per oc_premexpo lesson: no timing edge, only exposure.

## Win rates, fills, fee / funding split

- Book win rate (trade_stats discrete trades, after fees; per-year 4-phase sums):
  dev years REF [0.5032,0.5158,0.5191,0.5082] (dev 0.5114) vs V1
  [0.5032,0.5117,0.5157,0.5047] (0.5086) vs V2 [0.5032,0.5053,0.5168,0.5043]
  (0.5074) vs C_V1 (0.5101) vs C_V2 (0.5097). Scored-once Y4: REF 0.5365, V1 0.5380
  (V1 wins Y4 win rate by +0.15pp and Y4 return by +0.030pp — the only year both move together).
- 5y book win: REF 0.5169 vs V1 0.5151 (-0.18pp); all-trade win (book+dip): REF 0.6539 vs
  V1 0.6535 (-0.04pp); rung win identical 0.6859/0.6859 (dip sleeve untouched, as designed).
- book_fill events (dev, 4-phase sums): REF 3968 vs V1 3968 vs V2 3968 vs C_V1 3889 vs C_V2 3915;
  per-year fills in results.json (V1 vs REF per year: 932/932, 864/863, 997/1002, 1175/1171 —
  TTL barely moves the fill count because most fills happen in the issue bar; the second bar only
  rescues a handful of late fills). 5y fills: REF 5085 vs V1 5095 (+10).
- Engine totals (dev stage, fractions of equity; gate costs inside every leg):
  fees REF 0.2070 vs V1 0.2067 vs V2 0.2061 vs C_V1 0.1856 vs C_V2 0.1719;
  funding (adverse longs-only) REF 0.4114 vs V1 0.4109 vs V2 0.4088 vs C_V1 0.3608 vs C_V2 0.3290.
  5y totals (scored-once): fees REF 0.2692 vs V1 0.2697 (+0.0005); funding REF 0.5202 vs V1 0.5206.
  Book-episode maker/taker split 5y: REF maker 0.166063 / taker 0.052420 vs V1 maker 0.166317 / taker
  0.052044. The TTL saves nothing on costs (same fills, same positions 99% of the time).
- Exposure diagnostic: mean TTL scale s (weight sense) per year above; realised position-time is
  essentially REF (fill counts identical) — the second resting bar contributes ~0 fills and ~0 P&L.
  The uniform controls cut weight every bar (fewer units everywhere) and win on 2023 trend capture;
  the TTL cuts only the unfilled tail (almost nothing to cut).

## What failed and why

Low-|w| orders that miss in bar 1 almost never fill in bar 2 either (same vol-scaled price, no re-peg,
trend moved away or chop mean-reverted through the same level in bar 1 already): per-year fill deltas
are -5..+4 fills on ~1000/year. So TTL 1-vs-2 changes neither fill rate nor time-in-market at the
portfolio scale — dev4 mean moves +0.014pp (V1) / -0.002pp (V2), WORST unmoved (2021 inactive tie),
DD +0.01/+0.18. The round-trip ~4-8bps bounds the mechanism; measured dev4 effect is ~1-2bps/mo at full
BOT scale, i.e. noise. The controls prove the point: a real exposure cut (uniform x0.74-0.84 / x0.63-0.75)
moves dev4 mean by +0.23/+0.44pp (C_V1/C_V2 beat REF), while the selective version of "the same cut"
keeps 99% of REF's exposure and 99% of REF's P&L. Conviction (as |w_base| vs its own median/p75) does not
predict which resting order deserves a second bar. V2's 2024 (+0.208) is offset by 2022 (-0.156) with
worse DD — no robustness.

## Leakage checklist

- Feature timing: TTL uses ffill'd w_base[i,a] from source standard row r <= t_s only (known at the
  decision close; identity at shift 0); px from O0 once; sd/s4 from bars <= decision-2 lag via the engine;
  no re-peg; truncation-tested in tests/test_oc_convttl.py (later thresholds leave earlier bars unchanged;
  cut index identical; pre-5 never fills in engine).
- Label windows: no labels fit anywhere (exits mechanical SL/TP/timeout legs).
- Fit windows: quantiles q50/q75 from U < A_k-7d non-zero |w_base| only (7d embargo; frozen round quantiles
  0.50/0.75; Y0 q=-1.0 inactive disclosed PLAN fix before any engine outcome); R2 size/TP agents pre-date
  anchors; C-row s_y in-year realised so diagnostic/non-eligible by construction.
- Fill timing: entry strict trade-through + minute-5 ban (win_start=5); resting fills from minute 0 on
  carried bars (G2); SL market taker / TP limit maker; stop-first in the shared minute; NaN never
  fills/triggers. Gate costs inside every leg (maker 0.0002 / taker 0.00055 / longs 0.0001 per settling 8h,
  shorts 0). No statistic from any test year feeds any eligible choice (dev pick used 2021-2024 only; Y4
  scored once for REF+V1; V2/C rows never ran on Y4).
- Engineering fix before any variant outcome (disclosed, not post-hoc): Y0 empty-pool -> q=-1.0 inactive
  (PLAN post-hoc log 2026-10-08; books154 starts 2021-09-24 so U < A_0-7d is empty; later years unchanged).
  No parameter, threshold, window, or selection change after any outcome; the dev table was computed once;
  last stage ran REF+V1 only.

## Repro

`research/tournament/oc_convttl/{PLAN.md,convttl.py,run_convttl.py,results.json,
tmp/std_books.pkl,tmp/runs_dev.pkl,tmp/runs_last.pkl}` +
`tests/test_oc_convttl.py` (5 pass). Heavy via heavy_slot (tag oc_convttl, one
job at a time, float32 cube one shift at a time; dev 4 shifts x 5 rows + last
4 shifts x 2 rows, each row ~0.1-0.2 min/shift). results.json = dev table +
scored-once last table + pick. G2 REF identity asserted to the digit in the scorer.

## Vietnamese verdict

V1 hơn G2 không đáng kể ở dev4 (+0,014pp, 5,615 so với 5,601, kém nhất hòa 2,588, DD +0,01) và năm
scored-once (+0,030pp, 4,678 so với 4,648), nhưng thua xa control cắt-đều tương đương (-0,22pp dev4)
và làm rớt win rate book; V2 cũng không hơn G2 (5,599, DD 17,09).
Kết luận: REJECT cả hai biến thể TTL theo conviction ở dạng đăng ký trước, đóng hướng này (kéo dài
thời gian chờ khớp lệnh cho tín hiệu mạnh không tạo edge sau phí, chỉ còn là cắt exposure trá hình).
