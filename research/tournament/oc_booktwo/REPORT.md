# oc_booktwo REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS6 #7 (rank 7): two-rung book entry ladder — split each book order into half
at 10bps better + half at 25bps better, both PostOnly maker, 60min expiry
(minutes [5,65)), strict trade-through, minute-5 ban; unfilled expire, no market
fallback. V1 = 50/50; V2 = 70/30. SL/TP unchanged. HOW one signal's price is
split, not WHEN or how far a single offset sits (CLOSED `oc_bookoffset`
vol-scaled SINGLE offset, `oc_cadence` slower cadence, `oc_idea5_manualrest`
MANUAL rest kept as distinct).

STATUS: DONE. G2 reproduced to the digit first (5.41 / 16.91 / 16.82, dev years
+ Y4 exact). 4-phase engine dev (REF+V1+V2) + scored-once last year (REF+V2
only). NEGATIVE result: both ladders lose to G2 on dev4 mean, WORST year and DD;
dev4 robust pick V2 still trails REF by -0.15pp mean / -0.05 WORST / +0.6 DD, and
trails on the scored-once year too. Direction closed in this form.

## G2 reproduction (binding gate, passed)

REF (unpatched engine) reproduces v421 R2B1D17BFG2 to the digit, dev + last:
R/DD per year [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] +
Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82. No overlay; overlay path not
needed (book-entry mechanism, not an equity overlay).

## Per-year table (4-phase reset %/mo geometric, max yearly DD; Y4 scored ONCE for the dev4 pick + REF only, labelled)

| year | REF R / DD | V1 R / DD (diff) | V2 R / DD (diff) |
|---|---|---|---|
| 2021 dev | 2.588 / 10.86 | 2.490 / 10.35 (-0.098) | 2.534 / 10.29 (-0.054) |
| 2022 dev | 3.282 / 16.91 | 2.768 / 17.54 (-0.514) | 2.795 / 17.50 (-0.487) |
| 2023 dev | 6.045 / 15.81 | 6.006 / 15.77 (-0.039) | 6.124 / 15.72 (+0.079) |
| 2024 dev | 10.677 / 8.27 | 10.439 / 8.10 (-0.238) | 10.567 / 8.20 (-0.110) |
| 2025-09-24..2026-09-23 scored-once | 4.648 / 12.90 | — (not run; discipline) | 4.521 / 12.05 (-0.127) |

- dev4 robust pick (DD<=20, no losing dev year; prefer mean>=5, highest WORST,
  ties→mean): V1 (5.378/2.490/17.54) vs V2 (5.456/2.534/17.50) — both eligible,
  both mean>=5, V2 wins on WORST (2.534>2.490). PICK = V2.
- 5y (dev4 pick + REF, scored-once Y4): REF 5.410 / W 2.588 / maxDD 16.91 /
  full-path DD 16.82; V2 5.268 / W 2.534 / maxDD 17.50 / full-path DD 17.41
  (deltas -0.142 / -0.054 / +0.59 / +0.59). No losing year anywhere.
- V2 beats REF in 1/4 dev years (2023 +0.079) and loses the scored-once year
  (-0.127). V1 beats REF in 0/4 dev years. Neither variant beats G2 on dev4
  mean, WORST, or DD.

## Win rates, fills, fee / funding split

- Book win rate (trade_stats discrete trades, after fees; per-year 4-phase sums):
  dev years REF [0.5032,0.5158,0.5191,0.5082] (dev 0.5114) vs V1
  [0.5005,0.4994,0.5090,0.4885] (0.4989) vs V2 [0.5058,0.5000,0.5193,0.4940]
  (0.5044). Scored-once Y4: REF 0.5365, V2 0.5442 (V2 wins Y4 win rate but loses
  Y4 return — smaller winners / larger losers on the deeper rung).
- 5y book win: REF 0.5169 vs V2 0.5131; all-trade win (book+dip): REF 0.6539 vs
  V2 0.6543 (dip rung_win identical 0.6859/0.6874 — dip sleeve untouched, as designed).
- book_fill events (dev, 4-phase sums; ladder emits up to 2 per position vs 1 for
  REF — convention disclosed, not a fill-rate doubling): REF 3968 vs V1 7155 vs
  V2 7141; per-year fills in results.json. Trade counts (discrete book trades)
  come from trade_stats nb (not shown per-row here; win rates above are per-trade).
- Engine totals (dev stage, fractions of equity; gate costs inside every leg):
  fees REF 0.2070 vs V1 0.2000 vs V2 0.2019; funding (adverse longs-only) REF
  0.4114 vs V1 0.4010 vs V2 0.4059. 5y totals (scored-once): fees REF 0.2692 vs
  V2 0.2633; funding REF 0.5202 vs V2 0.5140. The ladder saves ~2-3% of fees and
  ~1-2% of funding (smaller open positions from missed deep halves) but gives up
  ~10x more in gross trend capture — net negative every selected metric.

## What failed and why

The second (25bps) rung fills in chop and misses in trends: the halves that fill
are adversely selected (fill = price moved against the signal side's intent by
an extra 15bps of distance), while the halves that would have captured straight
runs expire unfilled. Book win rate drops -0.7pp (V1) / -0.7pp (V2) on dev with
no DD compensation (DD +0.6). The 70/30 split (V2) loses less than 50/50 (V1)
because it keeps more weight on the near rung — i.e. the data prefer the
smallest possible deviation from G2's single price, and even the vol-scaled G2
price (max(10bps,0.25σ4h)) already sits deeper than 10bps in vol regimes, so a
fixed 25bps second rung adds distance without adding edge. Round-trip ~4-8bps
bounds the mechanism; measured dev4 drag is -0.15pp/mo (V2) at full BOT scale.

## Leakage checklist

- Feature timing: rung px from O0 (1m minute-0 open = 4h open, known at T) once;
  sd/s4 from bars ≤ decision-2 lag via the engine (same as G2); no re-peg;
  truncation-tested in tests/test_oc_booktwo.py (post-65 data cannot move fills;
  pre-5 minutes never fill; NaN never fills).
- Label windows: no labels fit anywhere (exits mechanical SL/TP/timeout legs).
- Fit windows: no fits, no thresholds, no quantiles anywhere (10/25bps +
  50/50 + 70/30 frozen ex-ante in PLAN; R2 size/TP agents pre-date anchors).
- Fill timing: entry live [5,65) strict low<px / high>px + minute-5 ban;
  SL market taker / TP limit maker; stop-first in the shared minute; NaN minutes
  never fill/trigger. Gate costs inside every leg (maker 0.0002 / taker 0.00055 /
  longs 0.0001 per settling 8h, shorts 0). No statistic from any test year feeds
  any choice (dev pick used 2021-2024 only; Y4 scored once for REF+V2).
- Engineering fixes before any variant outcome (disclosed, not post-hoc): (1)
  variant-name quoting in the exec patch (`V1`→`'V1'`; first dev launch failed
  with NameError before any V1/V2 number existed); (2) exec globals use the live
  eu module dict (audited oc_idea5 pattern) so the summarize override applies.
  No parameter, split, offset, window, or selection change after any outcome;
  the dev table was computed once; last stage ran REF+V2 only.

## Repro

`research/tournament/oc_booktwo/{PLAN.md,booktwo.py,run_engine.py,analyze.py,results.json,
tmp/runs_dev.pkl,tmp/runs_last.pkl,tmp/run_dev.log,tmp/run_last.log}` +
`tests/test_oc_booktwo.py` (7 pass). Heavy via heavy_slot (tag oc_booktwo, one
job at a time, float32 cube one shift at a time; dev 4 shifts × 3 rows + last
4 shifts × 2 rows, each row ~0.1-0.2 min/shift). results.json = dev table +
scored-once last table + pick.

## Vietnamese verdict

V1 rớt dev4 (5,378 so với 5,601 của G2, kém nhất 2,49 so với 2,588, DD 17,54),
V2 cũng rớt (5,456, kém nhất 2,534, DD 17,50) dù được pick theo luật robust;
năm scored-once V2 vẫn kém G2 (-0,127pp, 4,521 so với 4,648).
Kết luận: REJECT cả hai biến thể ladder book ở dạng đăng ký trước, đóng hướng
này (tách một tín hiệu thành hai giá cố định không mang lại edge sau phí).
