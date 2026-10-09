# oc_governor REPORT — does the PER-PHASE drawdown governor cost G2 return?

Pre-registered in PLAN.md (frozen before any outcome). G2REF harness reproduces
stored G2 dev years to the digit (fresh-vs-stored max-abs-diff 0.0); G2 5y
5.410 / W 2.588 / DD 16.91 / full-path 16.82 reproduced exactly before overlay.
Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h, win_start=5,
1m trade-through, stop-first. Engine via heavy_slot (dev 1.3 min, full 1.3 min).

## 0. LIVE governor check (read-only): YES, live is also per-phase

- scripts/forward_trade_phase.py build(): each phase s replays
  `eu.simulate(books, opens.reindex(grid), prep, trade=trade, ...)` on its own
  shifted grid with its own books/prep, so `g` inside is computed from THAT
  phase sub-book's own trailing-90d-peak equity (lagged 2 bars), exactly like
  research (engine_user.py: `gz, gw = (0.20, 0.10) if gov is None else gov`).
- backend/multiphase.py merge(): the account is the MEAN of the four sub-book
  growths (`mix = sum(growth.values()) / len(phases)`, `cap = 0.25*growth/mix`,
  never rebalanced) and nothing feeds the pooled mix back into any phase's `g`.
- So YES: live also runs four independent per-phase governors on sub-account
  equity. A pooled-account governor would be a design change, not what runs now.

## 1. Descriptive: G2's per-phase governor binds on ONE phase path (Task 1)

g recomputed from stored phase eq (g[i]=clip((0.20-dd)/0.10), dd from trailing
540-bar peak of that phase's eq, lagged 2 bars). Year window = equity time in
(A, A+365d]. Per phase-year (n ~2189 bars; frac g<1 / frac g==0 / mean g /
longest g==0 spell / phase end factor):

- s0: <1 = .005/.130/.119/.000/.001, =0 never; mean .99-1.0; end 1.71/1.53/3.60/3.15/1.90.
- s1: <1 = .252/.172/.343/.016/.247, =0 never; mean .83-1.0; end 1.41/1.59/1.64/3.02/1.52.
- s2: <1 = .010/.090/.223/.000/.077, =0 never; mean .89-1.0; end 1.29/1.47/2.11/3.83/1.71.
- s3: <1 = .073/.333/.715/.021/.039, =0 ONLY here: 7.6% of 2023 bars, longest
  165 consecutive bars 2024-03-06..2024-04-02 (the oc_mvrvmech E3 shutdown);
  mean g 2023 = 0.479; phase end factor 2023 = 0.745 (the phase lost 25% that
  year while the 4-phase mix earned 6.045 %/mo). Other years s3 end 1.02/1.31/3.51/1.77.

Missed-P&L proxy (LABELLED APPROXIMATION, no same-fill counterfactual exists):
standard-grid vectorised book proxy sum((1-g)*b) on shift 0 (exact alignment;
no vol-scale/governor feedback, no costs/fills, book only, dip excluded):
2021 +0.0001, 2022 +0.0194, 2023 -0.0038 (negative: governed bars had negative
proxy bars, i.e. the governor also skipped losses), 2024 +0.0000,
2025 +0.0004 — i.e. the BOOK miss is tiny; the real cost sits in the DIP sleeve
(rung sizes scale with g: oc_mvrvmech E3 rungs +64% bigger when g stayed high,
shift-3 G2 100 rungs at mean g 0.18 vs M1 279 rungs at 0.79).

## 2. Engine rows (one knob each; DD gate = 4-phase-mix max close/1m-marked)

Dev4 = selection (anchors 2021-2024); recent year scored ONCE (2025-09-24 ..
2026-09-23, labelled). R/W in %/mo geometric, DD = max yearly DD.

| row | dev4 R / W / DD | recent R / DD (ONCE) | 5y R / W / DD | full-path DD |
|---|---|---|---|---|
| G2 (stored ref) | 5.601 / 2.588 / 16.91 | 4.648 / 12.90 | 5.410 / 2.588 / 16.91 | 16.82 |
| GV1 (0.25,0.10) | 6.110 / 2.826 / 19.14 | 4.704 / 13.07 | 5.827 / 2.826 / 19.14 | 18.91 |
| GV2 (0.30,0.15) | 6.158 / 2.828 / 19.32 | 4.736 / 13.06 | 5.872 / 2.828 / 19.32 | 19.05 |
| GV3 pooled 2-pass | 6.107 / 2.830 / 17.89 | 4.824 / 13.07 | 5.849 / 2.830 / 17.89 | 17.50 |

Per-year (R, DD): GV1 (2.826,10.52) (3.478,19.14) (7.605,15.97) (10.724,8.26)
(4.704,13.07); GV2 (2.828,10.52) (3.611,19.32) (7.659,15.94) (10.724,8.26)
(4.736,13.06); GV3 (2.830,10.52) (3.374,17.89) (7.697,16.03) (10.724,8.26)
(4.824,13.07). No losing year anywhere; all DD <= 20 (hard cap holds).
Trades (disclosed extra run, same frozen configs, equity bit-identical):
book win G2REF 0.5096 (3968) / GV3 0.5104 (4150); rung win ~0.686-0.687;
all-trade win ~0.658-0.659 (dip rungs dominate counts).

Selection: all three qualify on dev4 (mean > 5.601, worst >= 2.588, DD <= 20).
Robust pick = GV3 nominally (worst 2.830 vs 2.828 vs 2.826) — gaps 0.002-0.004
are noise; GV2 has the highest mean (6.158). Moot for adoption: EVERY row fails
gate (b), recent year < 5 (4.704/4.736/4.824 vs G2 4.648: +0.06/+0.09/+0.18,
all still short). GV3 approximation gap: pass-1 vs pass-2 combined-dd max-abs
0.0440, mean-abs 0.0026 (max dd 0.1605 -> 0.1657) — the two-pass pooling is
self-consistent; the pooled g is only mildly wider than per-phase g because the
mix smooths single-phase drawdowns, as predicted.

## 3. Conclusion: REJECT the direction (negative result, valid)

Loosening the governor (wider bands or pooled equity) buys +0.5-0.6 pp/mo on
dev4 at +2.2-2.4 DD points (GV1/GV2 DD ~19.1-19.3, full-path ~19) — a pure
risk dial, no timing; GV3-pooled keeps DD lower (17.89/17.50) for the same lift
because the mix rarely hits 20%, but its recent year (4.824) still misses the
5%-floor gate. The per-phase governor IS a structural drag on single-phase
paths (s3-2023 shutdown: 165 bars at g=0, phase -25%), yet the pooled 4-phase
account already diversifies most of it away (mix DD 16.91 vs single-phase 43%
in the assignment's example) — which is exactly why GV3 adds only +0.18 on the
recent year. A pooled-account governor would be the honest live design (it
matches the real single pooled account and backend/multiphase.py already
computes the mix), but this study shows it does not pass the gate either, so
adopting it now would spend complexity without reaching 5%/mo. Close the
direction; keep a pooled governor as a candidate knob inside future
recombination (e.g. v306-style GA, walk-forward judged) rather than a standalone
change. Post-hoc log: compute_trades.py added after outcomes (same frozen
configs, events capture only, equity bit-identical) for trade counts.

Leakage/execution statement: books ffill (latest standard row <= t_s), agents
keyed by holding bar, sigma/vol-scale/governor causal with 2-bar lag, fills
win_start=5 + trade-through + stop-first, Bybit gate fees + adverse funding;
no fit used test-year data; recent year scored once for qualifiers only
(G2REF recent = stored/labelled, not re-selected).

## Vietnamese verdict (3 lines)

- Governor tính trên từng phase con đúng là một lực cản có cấu trúc: năm 2023 phase 3 bị tắt 165 bar liên tiếp ở g = 0 (mean g 0,48, phase lỗ 25%) trong lúc thị trường rally, và nới governor (GV1/GV2) hay gộp pooled (GV3) đều nhích dev4 lên +0,5-0,6 điểm/tháng — nhưng đó chỉ là núm rủi ro (DD tăng lên ~19), còn năm gần nhất vẫn dưới sàn 5% (4,70/4,74/4,82 so với G2 4,65).
- Thiết kế pooled-account governor mới là trung thực với tài khoản live thật (một tài khoản gộp, backend/multiphase.py đã có sẵn mix), và GV3 chứng minh nó êm hơn (DD 17,89 so với ~19,1-19,3) vì mix hiếm khi chạm 20% — nhưng vẫn không qua gate nên đừng adopter riêng lẻ, chỉ giữ làm núm cho các vòng lai tạo walk-forward sau này.
- Kết luận: REJECT hướng này (kết quả âm nhưng hợp lệ), đóng direction, không cần thêm bằng chứng prospective cho governor.
