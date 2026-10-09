# oc_netting REPORT — Book/dip + cross-clock inventory netting (IDEAS6 #3, 2026-10-08; PLAN pre-registered before any outcome)

Pre-registered in `PLAN.md` (frozen before any number). G2 baseline reproduced
EXACTLY from `v421_runs.pkl` first (5.41 / W 2.588 / DD 16.91 / full-path 16.82,
per-year R/DD to the digit); G2REF dev harness matches stored dev segments with
max-abs-diff 0.0 on all 4 shifts; dev re-run (disclosed instrumentation: per-row
stats capture, configs frozen) equity bit-identical True. Gate costs: maker
0.0002, taker 0.00055, longs 0.0001/8h, win_start=5, 1m trade-through,
stop-first. Engine via heavy_slot (dev 3.0 min + 2.9 min re-run, full 2.0 min;
sequential shifts, float32).

## Mechanism result

- N1 (book-SHORT vs dip-LONG net, within each phase): gate fires on 44.83% of
  coin-bars (book SHORT is common); dip rungs fall 16852 -> 10272 dev (-39%).
  Skipped SHORT-book rungs were lower-win (dev rung win 0.6965 -> 0.7164) yet
  their removal still costs mean return: post-cascade dips carry profit even
  under SHORT books (same lesson as IDEAS5: vpinveto/rungquality/cascadedelay).
  Book win flat (0.5096 -> 0.5106); book fills 3968 -> 4075, fees 0.2070 ->
  0.2115, funding 0.4114 -> 0.4150 (sums over 4 sub-accounts).
- N2 (N1 + same coin+direction merge across clocks, one TP/stop earliest price):
  PROVEN NULL under proportional fees — a merged OMS leg carries the summed
  notional, so its exit fee equals the sum of the legs' fees (saving = 0).
  Census: 761/768 dev and 974/982 full book exits occur under >=2-phase
  agreement (targets agree 99.4% of hourly coin-slots — same books, 1h-apart
  grids), yet none of it converts to savings. N2 == N1 path-wise (years via the
  same `year_reset` on N1 runs). Legs exit at different times/prices via
  different TP/stop levels; forcing one merged exit would be a strategy change
  needing pooled re-simulation — excluded.

## Per-year table (R %/mo geometric, DD %; dev 2021-2024 = selection; recent 2025-09-24..2026-09-23 scored ONCE for the dev4 robust pick, labelled)

| year | G2REF R / DD (stored REF) | N1 R / DD | N2 R / DD |
|---|---|---|---|
| 2021-09-24 (dev) | 2.588 / 10.86 | 3.141 / 10.54 | 3.141 / 10.54 |
| 2022-09-24 (dev) | 3.282 / 16.91 | 2.830 / 16.56 | 2.830 / 16.56 |
| 2023-09-24 (dev) | 6.045 / 15.81 | 5.890 / 15.85 | 5.890 / 15.85 |
| 2024-09-24 (dev) | 10.677 / 8.27 | 9.970 / 8.25 | 9.970 / 8.25 |
| 2025-09-24 (REF, once) | 4.648 / 12.90 | 4.641 / 10.92 | 4.641 / 10.92 |

Dev4 robust pick: N1 (N1/N2 tie at 5.419/2.830/16.56; both eligible, both mean
>= 5; N1 worst 2.830 > G2REF worst 2.588; tie -> engine row). 5y: N1/N2 5.263 /
W 2.830 / DD 16.56, no losing year; G2REF 5.410 / 2.588 / 16.91. Full-path DD
(max close/1m-marked): N1/N2 16.49 (15.90/16.49) vs G2 16.82. Win rates dev:
book 0.5106 (4063), rung 0.7164 (10272), all-trade 0.6581; G2REF book 0.5096
(3956), rung 0.6965 (16852), all 0.6610. Recent-year census (ONCE): 1617 book
exits, 1591 rungs at 0.6518 win.

## Decision

N1 is a mild risk-off tilt: dev worst +0.24pp (2.588 -> 2.830) and DD -0.35pp
(16.91 -> 16.56) at -0.18pp mean (5.601 -> 5.419); 5y trails G2 by -0.15pp
(5.263 vs 5.410). Gate: (a) 5y >= 5 PASS, (b) recent >= 5 FAIL (4.641 vs G2
4.648, noise-level), (c) no losing year PASS, DD <= 20 PASS (16.56 yearly,
16.49 full-path). Fails gate (b) — the same failure mode as the oc_governor
variants. N2 adds exactly nothing.

## Verdict

VERDICT: REJECT as a standalone change (negative result, valid) — N1 buys a
better worst-year and lower DD with lower mean and still misses the
recent-year 5%-floor; N2 is proven null under proportional fees. Close the
direction standalone; netting survives only as a candidate knob inside future
walk-forward recombination (e.g. v306-style GA), not as an adopted change.

## Leakage checklist

- Feature timing: `books_bear` = latest standard-grid book row <= shifted
  decision time (ffill; identity at s=0); R2 agent size/TP keyed by holding bar
  T = idx + 4h; sig4/vol-scale/governor causal with 2-bar lag; N1 gate reads
  `books_bear[i]` known at the holding-bar start (ladder placed then). Test
  `test_n1_gate_causality_truncation` perturbs future/past rows: gate[i]
  invariant. No statistic from any test year feeds any choice (nothing fitted).
- Label windows: none (no labels, no model, no thresholds).
- Fit windows: none (gate strict `< 0`, no parameter; N2 no parameter; embargo
  N/A). Recent year scored once for the frozen pick only.
- Fill timing: win_start=5 (no fills minutes 0-4), limit fills only on strict
  1m trade-through, stop-first on same-bar ties, unfilled entry limits expire
  (no market fallback), stops taker / TPs maker, adverse funding on longs.
  N2 savings use realised exits at exit minute only (exit time <= accrual hour;
  proven zero anyway).

## Post-hoc log

- `compute_engine.py` gained per-row stats capture after Stage-1 (diagnostics
  only); dev re-run equity bit-identical True, configs frozen.
- `compute_n2overlay.py` first used a mix-level accountant
  (average-then-rebase) that disagreed with `year_reset` (rebase-then-average);
  replaced by the proportional-fee zero-proof with N2 years via `year_reset` on
  N1 runs (identical). No variant added, no selection changed.

## Vietnamese verdict (3 lines)

- Netting book-SHORT/dip-LONG (N1) chỉ là núm risk-off nhẹ: dev worst-year nhích +0,24 điểm (2,59 -> 2,83) và DD -0,35 điểm nhưng mean -0,18 điểm (5,60 -> 5,42), vì 40% rung dip bị cắt vẫn mang lợi nhuận post-cascade; năm gần nhất 4,64 < sàn 5% (ngang G2 4,65) nên rớt gate.
- Merge cùng chiều across-clock (N2) được chứng minh null dưới phí tỷ lệ (vị thế gộp mang notional tổng nên phí thoát bằng tổng phí các chân, tiết kiệm = 0 dù 99% lệnh thoát rơi vào lúc các clock đồng thuận) — N2 == N1.
- Kết luận: REJECT thay đổi độc lập (kết quả âm nhưng hợp lệ), đóng direction, chỉ giữ netting làm núm cho các vòng lai tạo walk-forward sau này.
