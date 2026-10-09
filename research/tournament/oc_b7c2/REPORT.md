# oc_b7c2 — REPORT (2026-10-08; PLAN frozen before any outcome)

Do the cascade boost B7 and the Chronos tilt C2 stack on the BOT? B7 (dip budget x1.5 for 7d after a
> 4 sigma 4h move, market-wide per shift) acts on WHEN to add dip capital; C2 (rung x1.25/x0.75 by
Chronos downside quantile risk = -ch_q10, per-anchor fits) acts on WHICH rungs get more.
B7C2 = product m_B7*m_C2; B7C2_cap = min(product, 1.5). Book untouched. Dip gross cap 2.0 and every
G2 limit bind. Multisets: B7C2 {0.75,1.0,1.125,1.25,1.5,1.875}, cap {0.75,1.0,1.125,1.25,1.5}.

CONTAMINATION LABEL (pre-registered): both components were already scored on the post-release year
(B7 also contaminated, see oc_cascadeboost) -> every post-release-year (2025-09-24..2026-09-23)
number below is a LABELLED DIAGNOSTIC (not clean evidence); selection on dev4 ONLY.

STATUS: DONE — engine dev (12 sims) + last once (12 sims) + S5 Bybit (16 sims) via heavy_slot;
reproduction gates PASS to the digit; pytest 3/3. Dev4 robust pick: B7 (standalone).

## Engine dev4, base Binance (4-phase reset %/mo, DD in brackets; SELECTION BASIS)

| row | 2021 | 2022 | 2023 | 2024 | mean | WORST | DDmax | losing |
|---|---|---|---|---|---|---|---|---|
| REF (engine) | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0 |
| B7 (copy oc_cascadeboost) | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 | 0 |
| C2 (copy oc_chronos) | 2.711/11.52 | 3.460/15.48 | 6.250/15.07 | 10.721/8.29 | 5.739 | 2.711 | 15.48 | 0 |
| B7C2 (engine) | 2.922/15.45 | 3.573/17.05 | 7.795/16.27 | 12.598/11.04 | 6.652 | 2.922 | 17.05 | 0 |
| B7C2_cap (engine) | 2.874/14.70 | 3.518/17.04 | 7.612/16.36 | 12.261/11.00 | 6.501 | 2.874 | 17.04 | 0 |

- REF reproduces v421 G2 dev 0..3 to the digit (gate passed before any variant scored). Full-path DD
  dev window: REF 16.82, B7 17.75 (copy), C2 15.42 (copy), B7C2 16.91, cap 16.88.
- Sized mean mult (engine): B7C2 1.3067, cap 1.2536 (B7 alone 1.319, C2 alone ~1.0; the stack binds
  where both agree). All-trade win dev4: REF [0.613,0.658,0.697,0.671], B7C2
  [0.609,0.657,0.691,0.664], cap [0.611,0.657,0.691,0.665] — sizing only, no trade-selection move.
- Robust pick on dev4 ONLY among REF / B7 / B7C2 / B7C2_cap (C2 is copy-only reference): all DD <= 20,
  no losing year, all mean >= 5, so highest dev4 WORST wins: B7 (2.955 > B7C2 2.922 > cap 2.874 >
  REF 2.588). PICK: B7. The stack underperforms standalone B7 on dev4 mean (-0.086 uncapped,
  -0.237 capped) and on WORST (-0.033 / -0.081) at slightly LOWER DD (-0.87pp vs B7).

## Engine 5y + post-release year (scored ONCE; Y4 LABELLED DIAGNOSTIC)

- REF: 5y 5.410, W 2.588, DDmax 16.91, full-path DD 16.82; Y4 4.648/12.90. Worst 1m-marked episode:
  peak 2023-04-17 -> trough 2023-06-14, depth 16.82% (marked 16.82, close 16.05).
- B7 (copy): 5y 6.364, W 2.955, full 17.75; Y4 diag 4.88/13.81 (BELOW 5, contaminated). Worst episode:
  same 2023 leg, depth 17.75% (marked 17.75, close 16.96).
- C2 (copy): 5y 5.542, W 2.711, full 15.42; Y4 diag 4.754/12.86.
- B7C2: 5y 6.318, W 2.922, DDmax 17.05, full-path DD 16.91; Y4 diag 4.99/14.17 (BELOW 5,
  contaminated). Worst episode: same 2023 leg, depth 16.91% (marked 16.91, close 16.11). Y4 wins:
  book 1093 @ 0.5361, rung 4298 @ 0.6491, all 0.6262. Sized mean 5y 1.3216.
- B7C2_cap: 5y 6.177, W 2.874, DDmax 17.04, full 16.88; Y4 diag 4.89/13.69. Worst episode: same
  2023 leg, depth 16.88% (marked 16.88, close 16.07). Y4 all-win 0.6241. Sized mean 5y 1.2675.
- Determinism OK (stage-last dev segments equal stage-dev). REF Y4/5y/full reproduce v421 G2 exactly.

## Same rows on Bybit prices S5 (harness of oc_c2bybit; y2021 SHORT from 2021-11-15, labelled)

4-phase reset %/mo (yearly DD in brackets) [2021s, 2022, 2023, 2024] | dev4 mean / W / maxDD; 5y R / full:

| row_S5 | dev4 years | dev4 mean/W/DD | 5y R/full | Y4 diag R/DD |
|---|---|---|---|---|
| REF_S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 | 4.994/2.129/18.11 | 4.883/18.09 | 4.443/12.37 |
| B7_S5 (fresh) | 2.200/15.07, 2.457/19.08, 8.368/15.98, 12.172/12.54 | 6.217/2.200/19.08 | 5.906/20.31 | 4.670/13.43 |
| B7C2_S5 (pick is B7; disclosed) | 2.253/15.77, 3.064/17.56, 6.503/17.02, 12.243/12.58 | 5.944/2.253/17.56 | 5.685/17.43 | 4.657/13.88 |
| B7C2_cap_S5 (disclosed) | 2.178/15.05, 3.093/17.52, 6.392/17.16, 12.002/12.54 | 5.847/2.178/17.52 | 5.596/17.41 | 4.598/13.27 |

- REF_S5 reproduces oc_c2bybit REF_S5 to the digit (gate passed). S5 all-win Y4: REF 0.6247,
  B7 0.6220, B7C2 0.6251, cap 0.6226 — sizing only.
- On Bybit the ordering FLIPS vs base: B7_S5 has the highest dev4 mean (6.217 > stack 5.944 > cap
  5.847 > REF 4.994) and highest WORST (2.200 vs 2.253 stack — stack WORST is +0.053 better), BUT
  B7_S5 full-path DD is 20.31 (> 20) with yearly DDmax 19.08, while both stack rows stay <= 20
  (17.43/17.41 full, 17.56/17.52 yearly). The cap clips ~0.1pp mean for -0.13pp DD vs uncapped on S5.

## Leakage checklist

- Feature timing: B7 triggers use closes with close_time <= tc only; SIG window excludes the tested
  bar; boost window strictly after tc (0 < T-tc <= 7d); C2 forecast for T uses only 512 closes of bars
  closing <= T; stack lookup uses only (sym,shift,T) at the holding bar. Truncation-tested in
  tests/test_oc_b7c2.py (stack mults from truncated frozen boost+Chronos tables identical on kept
  prefix; multisets ⊂ pre-registered sets; 3/3 pass).
- Label windows: B7 none fit anywhere; C2 harness t_exit < A - 7d inherited, not recomputed.
- Fit windows: B7 no fits (frozen 4.0/540/120/1.5/7d); C2 frozen fits.json (shift-0 only + 7d embargo;
  year y uses anchor-y fit only, never later); no statistic from any test year feeds any choice.
- Fill timing: win_start=5 + 1m trade-through + stop-first in shared 1m bar (engine); S5 same with
  Bybit minutes (live0 2021-11-15+shift). Gate costs inside the engine (maker 0.0002, taker 0.00055,
  longs pay 0.0001/8h, shorts 0).
- Coverage: no skipped anchor year; missing boost history -> 1.0; missing ch_q10 -> 1.0 (engine
  miss_c2 = 0 on base dev+last — full Chronos coverage; S5 same features).
- DISCLOSED: replica-DD-half n/a (direct 4-phase engine here; binding DD check is yearly + full-path
  DD <= 20 — base all pass; S5 B7_S5 full 20.31 breaches, stack rows pass).

## What worked and what did not

- Worked: the stack is mechanically sound (product of two different-mechanism sizing tilts, cap
  binds, gross cap 2.0 holds, reproduction gates pass, determinism holds, S5 harness reproduces
  REF_S5). The uncapped stack beats REF by +1.05pp dev4 mean (+0.33 WORST) at +0.14pp DD on base.
- Did not work: stacking C2 on top of B7 ADDS NOTHING over B7 alone on dev4 (mean -0.09pp, WORST
  -0.03pp vs B7) — the C2 tilt's +0.14pp standalone edge does not compose with the B7 boost; the
  capped variant is weaker still. On the diagnostic Y4 the stack (4.99) edges B7 (4.88) and REF
  (4.65) but stays BELOW 5 and is contaminated by construction. On Bybit the stack buys lower DD
  (17.4 vs 20.3 full) at the cost of -0.27pp dev4 mean vs B7_S5.
- Verdict driver: dev4 robust rule picks B7 over both stack rows; no adoption case for the stack.

## Vietnamese verdict

- Stack B7xC2 không hơn B7 đơn lẻ trên dev4 (mean 6,65 thua B7 6,74, WORST 2,92 thua 2,96; bản cap còn yếu hơn 6,50/2,87), nên pick robust dev4 vẫn là B7 chứ không phải stack.
- Năm post-release chỉ là diagnostic nhiễm (B7C2 4,99, cap 4,89, B7 4,88 — đều dưới cổng 5), còn giá Bybit S5 thì B7 mean cao nhất nhưng full DD 20,31 vượt 20 còn stack giữ DD ≤ 20 với mean thấp hơn.
- Kết luận: REJECT stack — giữ B7 làm ứng viên (chờ paper prospective), không đưa B7C2/B7C2_cap vào G2.
