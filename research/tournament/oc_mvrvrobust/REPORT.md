# oc_mvrvrobust REPORT — is the MVRV-z gate M1 real or one event?

PLAN.md was written BEFORE any new computation; no threshold/window/mult was
changed after outcomes. Frozen M1: all majors' book longs x0.5 while BTC MVRV-z
> 2.0 (trailing <= 365d, min 180, day D usable from D+1 02:00 UTC), v426
mechanism after the bear filter, before shifted-clock ffill. Gate costs: maker
0.0002, taker 0.00055, longs 0.0001/8h, shorts nothing; limits fill only on 1m
trade-through, no fill in first 5 min (`win_start=5`); stop-first in same bar.
G2+M1 reproduced to the digit first (G2 5.41/W 2.588/DD 16.91/full 16.82; M1
dev4 6.192/DD 16.26, 5y 5.881/full 16.22); the 4-phase engine re-ran them
bit-exact, so overlays are comparable. oc_amihudrobust does not exist yet, so
frictions S1-S5 are verbatim the v421-audit family (robust_d13.py):
S1 MAKER 0.0004/TAKER 0.0012, S2 15/16, S3 30/31, S4 stop_slip 0.5, S5 Bybit 1m
from 2021-11-15.

## 1. Event table (frozen M1; 4h-grid proxy, 21 strict windows merged <= 14d -> 6 episodes)

750 gated bars total (anchors: 2021 0, 2022 42, 2023 792, 2024 120, 2025 0).
Window P&L = TOTAL-equity proxy from cached 4-phase paths (the engine does not
separate book-only P&L; the M1-G2 gap inside a gated window is gate-driven by
construction). BTC = buy-hold from xs_universe daily closes.

| ep | gated window | days | BTC | G2 win | M1 win | diff | anchor |
|---|---|---|---|---|---|---|---|
| E0 | 2023-04-14..2023-04-20 | 5.8 | -7.3% | -0.0482 | -0.0540 | -0.0058 | 2022 |
| E1 | 2023-05-06..2023-05-07 | 0.8 | -1.5% | +0.0002 | +0.0002 | ~0 | 2022 |
| E2 | 2023-11-02..2024-01-13 | 71.8 | +22.6% | +0.2272 | +0.3090 | +0.0818 | 2023 |
| E3 | 2024-02-10..2024-04-10 | 59.8 | +48.1% | +0.3411 | +0.5821 | +0.2410 | 2023 |
| E4 | 2024-11-12..2024-12-01 | 18.8 | +10.6% | +0.2984 | +0.3060 | +0.0076 | 2024 |
| E5 | 2024-12-17..2024-12-18 | 0.8 | -5.6% | +0.0003 | +0.0015 | +0.0012 | 2024 |

The dev4 gain (+0.591 pp/mo) lives in TWO anchor years (2023 +1.78pp,
2024 +0.54pp at year level) and three non-trivial episodes (E2 432 bars, E3 360,
E4 114). E0/E1/E5 are negligible one-bar blips (combined diff ~ -0.005).

## 2. Jitters (engine, one knob each; dev4 and 5y)

| row | dev4 R/W/DD | 5y R/DD/full | gated bars |
|---|---|---|---|
| G2 | 5.601 / 2.588 / 16.91 | 5.41 / 16.91 / 16.82 | — |
| M1 frozen | 6.192 / 2.588 / 16.26 | 5.881 / 16.26 / 16.22 | 750 |
| J_T175 | 5.868 / 2.588 / 15.30 | 5.623 / 15.30 / 15.30 | 1242 |
| J_T225 | 6.124 / 2.588 / 16.91 | 5.827 / 16.91 / 16.82 | 444 |
| J_W270 | 6.138 / 2.588 / 15.70 | 5.838 / 15.70 / 15.66 | 948 |
| J_W450 | 6.010 / 2.588 / 16.91 | 5.736 / 16.91 / 16.82 | 762 |

All four jitters beat G2 on dev4 (5.87-6.14 vs 5.601) and on 5y, with DD <= G2.
Tighter threshold / shorter window gate more and cut DD further (15.3-15.7);
looser variants converge toward G2. No jitter flips the sign.

## 3. Leave-one-episode-out (engine; only episodes >= 5% of gated bars: E2/E3/E4)

| row | dev4 R | 2023 R | 2024 R | gain left (vs G2 5.601) |
|---|---|---|---|---|
| M1 | 6.192 | 7.824 | 11.218 | +0.591 |
| LOEO_E2 | 5.879 | 6.484 | 11.295 | +0.278 (E2 explains 0.313) |
| LOEO_E3 | 6.179 | 7.747 | 11.241 | +0.578 (E3 explains 0.013) |
| LOEO_E4 | 6.063 | 7.824 | 10.679 | +0.462 (E4 explains 0.129) |

Largest single episode (E2) explains ~53% of the dev4 gain — under the 80%
single-event bar. Every LOEO row still beats G2 on dev4. E3's window proxy looked
huge (+0.24 absolute over its 60 days) but its marginal dev4 contribution is
tiny once E2 is present (overlapping 2023 rally path-dependence); E4 carries
the 2024 leg. Gain survives each single removal -> spread over >= 2 episodes
(E2 in anchor 2023, E4 in anchor 2024).

## 4. Frictions S1-S5, M1 vs G2 (dev4 R; 5y in parens)

| fric | G2 dev4 (5y) | M1 dev4 (5y) | M1-G2 dev4 |
|---|---|---|---|
| base | 5.601 (5.41) | 6.192 (5.881) | +0.591 |
| S1 cost stress | 4.740 (4.571) | 5.308 (5.025) | +0.568 |
| S2 latency 15 | 5.391 (5.212) | 6.067 (5.752) | +0.676 |
| S3 latency 30 | 4.628 (4.578) | 5.128 (4.978) | +0.500 |
| S4 stop slip | 4.992 (4.898) | 5.673 (5.442) | +0.681 |
| S5 Bybit window | 4.994 (4.883) | 5.776 (5.508) | +0.782 |

M1 > G2 under every friction (dev4 and 5y; S5 on its own truncated window).
DD under stress stays <= 20 (worst M1_S1 17.19 vs G2_S1 17.45). Costs hurt the
level (S1/S3 drop both ~0.9pp) but not the edge.

## 5. Most recent year, scored ONCE (labelled; M1 candidate under robust criterion)

2025-09-24..2026-09-23, from the same full-span engine (no new selection use):
G2 4.648/12.9, M1 4.648/12.9 (gate never fires in 2025 under any MVRV knob —
all jitters also 4.648), CTRL_M1 4.662/12.36. No out-of-sample confirmation and
no contradiction: the gate is silent in the most recent year by construction.

## 6. A1+M1 combined (labelled post-hoc, NOT a candidate)

A1 (Amihud tilt) applied on top of the M1-gated book: dev4 6.238/W 2.798/DD
16.08; 5y 5.939/full 15.92; Y4 4.75/11.14. Slightly above M1 alone on dev4
(+0.046) and 5y (+0.058), lifts the worst dev year (2.798 vs 2.588) with lower
DD — but the combination was conceived after seeing both legs, so it is
evidence of compatibility, not a selection.

## Leakage / causality checks (how verified)

- Feature timing: MVRV daily as-of D+1 02:00 <= T (searchsorted right-1); A1
  daily as-of D+1 00:00 <= T; `test_h8_truncation_causal` recomputes z after
  causal truncation (matches to 1e-12); `test_h8_availability_boundary` checks
  the ±1s usability edge; `test_handchecked_synthetic_mults` checks thresholds
  (2.0/1.75), NaN/Inf -> 1 (no false fires), shapes/clips.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits — rolling norms are causal features; thresholds/windows
  frozen in PLAN; CTRL means realised-exposure only.
- Fill timing: `win_start` per row + 1m trade-through + stop-first (v426 harness,
  G2 bit-exact re-run). `tests/test_oc_mvrvrobust.py` passes (3 tests).

## Post-hoc log

- No definition changes after outcomes (thresholds, windows, mults, merge gap
  14d, 5% LOEO cap, S1-S5 defs, A1M1 order all identical to PLAN).
- `compute_events.py` relabelled per-year bars to per-anchor-year bars (labelling
  only, no signal change).
- Coordination: `oc_amihudrobust/PLAN.md` (parallel worker, appeared mid-task)
  defines S1-S5 verbatim as implemented here (S1 0.0004/0.0012 globals patch;
  S2 15/16; S3 30/31; S4 slip 0.5; S5 Bybit from 2021-11-15) — implementations
  match, no change needed.

## Vietnamese verdict (3 lines)

- M1 đạt cả ba cửa robust đã đăng ký: hiệu quả còn lại sau khi bỏ từng episode (5,88/6,18/6,06 so với G2 5,60; episode lớn nhất E2 chỉ giải thích ~53%), cả 4 jitter đều hơn G2 trên dev4 (5,87-6,14) và 5 năm, M1 hơn G2 dưới mọi ma sát S1-S5 (dev4 +0,50 tới +0,78).
- Điểm trừ phải ghi rõ: hiệu quả dồn vào 2 episode E2+E3 cùng năm anchor 2023 (riêng E3 đóng góp biên chỉ 0,01 khi đã có E2), năm xấu nhất hòa G2 (2,588, gate không nổ năm 2021) và năm gần nhất gate im lặng (M1 = G2 = 4,65) nên không có xác nhận ngoài mẫu.
- Kết luận: robust theo nghĩa đã định (không phải may mắn một sự kiện) nhưng mong manh ở chỗ phụ thuộc chu kỳ euphoria 2023-2024; kết hợp A1+M1 (dev4 6,24, năm tệ nhất 2,80, DD 16,08) chỉ là tương thích post-hoc — nếu cứu M1 thì bằng paper-log prospective, không tinh chỉnh thêm.
