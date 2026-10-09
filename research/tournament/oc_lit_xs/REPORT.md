# oc_lit_xs REPORT — Amihud (H4) + MAX (H5) cross-sectional book tilts

Signal: perp 1d `data/raw/xs_universe_20260924/<SYM>_1d.parquet` (5 majors;
BTC 2019-09-09.., SOL 2020-09-15.., all to 2026-09-23) so 2021-09-24..2025-09-23
plus 30d/21d windows fully covered; no skip, NaN->mult 1 fallback never needed
(coverage 100% on decision times). `r=close/prev-1`, `amihud=|r|/quote_volume`,
`Amihud30=mean 30d (min 20)`, `Size30=mean quote 30d`, `MAX21=max r 21d (min 15)`.
`D*(T)=date(T)-1day` (day usable iff D+1 00:00<=T); XS z at same T only
(ddof=1; <2 finite or std 0 -> 0; NaN->1); A3 terciles by Size30 rank
([0,1]/[2,3]/[4], group<2 or std 0 -> 0). Mults clipped [0.5,1.5].
PLAN.md written before any engine run; no threshold/multiplier changed after outcomes.
Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h, shorts nothing; limits fill
only on 1m trade-through, no fill first 5 min (`win_start=5`), stop-first same bar.

## G2 reproduction (stop-gate passed)

Cached `v421_runs.pkl` via `reset_metric.year_reset` + `v388.mix`: 5.41 %/mo,
W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly
(2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9) — to the digit.
Engine re-ran G2 to the same triple, so overlay comparison is valid. Mechanism =
v426 copy: multiplier on STANDARD rows after bear filter, before shifted-clock ffill;
rows before 2021-09-24 untilted. A1/A3/X1/X3 scale every non-zero weight; A2/X2 longs
only (A2 frame itself asymmetric `max(z,0)`; X2 frame symmetric + longs mask).

## Selection (ONLY dev4 2021-2024; candidate needs mean>G2 5.601, worst>G2 2.588, DD<=17.41, beats control)

| dev year | G2 R/DD | A1 R/DD | C_A1 R/DD | A2 R/DD | A3 R/DD | X1 R/DD | X2 R/DD | X3 R/DD |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | 2.588/10.86 | 2.798/12.21 | 2.585/10.85 | 2.295/11.45 | 2.590/12.88 | 2.843/12.06 | 2.759/11.98 | 2.699/11.10 |
| 2022-23 | 3.282/16.91 | 3.395/16.81 | 3.269/16.79 | 3.415/17.42 | 3.013/16.99 | 3.832/16.20 | 3.397/16.54 | 2.220/18.19 |
| 2023-24 | 6.045/15.81 | 6.390/15.77 | 6.308/15.81 | 6.055/15.41 | 5.234/15.83 | 4.515/16.56 | 4.565/16.62 | 6.423/15.00 |
| 2024-25 | 10.677/8.27 | 10.987/8.42 | 10.678/8.27 | 10.686/8.75 | 10.853/8.31 | 10.408/8.26 | 10.773/7.87 | 10.461/8.23 |
| dev4 mean/W/DD | 5.601/2.588/16.91 | 5.844/2.798/16.81 | 5.662/2.585/16.79 | 5.564/2.295/17.42 | 5.372/2.590/16.99 | 5.359/2.843/16.56 | 5.326/2.759/16.62 | 5.399/2.220/18.19 |

Controls dev4 mean: C_A2 5.520, C_A3 5.608, C_X1 5.599, C_X2 5.604, C_X3 5.608.
A1 beats G2 (+0.243pp), beats worst (+0.210), DD-ok (-0.10), beats C_A1 (+0.182).
A1 wins 4/4 dev years on return vs G2. All other variants fail the mean gate
(X3 additionally fails DD 18.19>17.41 and worst 2.220<2.588 — falsification behaves
as expected). Tilt is continuous: share tilted 100% of affected cells every year
(z~=0 a.s.); mean mult ~1.0 (A1: 1.0002/0.9979/0.9969/1.0002; controls equal by
construction), so the control ~= G2 level and A1's edge is timing, not exposure.
Robust view (DD<=20, no losing dev year; prefer mean>=5 then highest worst): all six
qualify on DD/losing; highest dev4 worst is X1 (2.843) but its mean (5.359) loses to
G2 — reported, not selected (template candidate rule governs).

Most recent year, scored ONCE for candidate only (labelled, not a selection input):
Y4 (2025-26) G2 4.648/12.9, A1 4.750/11.14, C_A1 4.609/12.92; full-5y A1 5.624/16.81/
full-DD 16.66 vs G2 5.41/16.91/16.82. A1 wins Y4 on return (+0.102) with lower DD.

## Leakage / causality checks (how verified)

- Feature timing: `D+1 00:00<=T` mapping; `test_signal_truncation_causal` recomputes
  Amihud30/MAX21 at D0 from data truncated to <=D0 (matches 1e-12), checks the ±1s
  boundary exposes exactly the prior day, and sampled-T truncation leaves multipliers
  unchanged; `test_handchecked_synthetic` checks z/tercile/clip/variant maths.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; cross-sectional mean/std at same T only; windows (30d/21d),
  K=0.25, clip, tercile rule fixed in PLAN.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness,
  G2 bit-exact). `tests/test_oc_lit_xs.py` passes (2 tests).

## Post-hoc log

- No definition changes after outcomes (windows/thresholds/K/clip/side-masks/controls
  identical to PLAN). Two pre-outcome code fixes only: tz-aware searchsorted crash in
  `xs_signal._raw_matrix` (found by pytest, no economic change) and a missing paren in
  `compute_xs_engine.gate_books` (found before first engine launch). First engine run
  already included the G2 bit-exact re-run.

## Vietnamese verdict (3 lines)

- A1 (nghiêng thanh khoản Amihud cả hai chiều) đạt cửa ứng viên trên dev4 (5.844>5.601, năm tệ nhất 2.798>2.588, DD 16.81, hơn control +0.18) và thắng năm gần nhất khi chấm một lần (4.75 so với 4.65 của G2); các biến thể còn lại bị loại, chân phủ định X3 thua đúng như kỳ vọng.
- Hiệu ứng nhỏ (+0.24 điểm dev4, +0.10 năm gần nhất, tilt liên tục 100% ô với hệ số trung bình ~1.0) và chọn 1-trong-6 nên chưa đủ để áp dụng ngay.
- Hướng Amihud cần bằng chứng prospective ngoài mẫu trước khi xem xét đưa vào G2; MAX/lottery và size-neutral nên đóng lại.
