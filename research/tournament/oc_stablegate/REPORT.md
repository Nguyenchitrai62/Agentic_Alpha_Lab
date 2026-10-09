# oc_stablegate REPORT — stablecoin net-creation impulse as book-long gate (B3) and dip-budget dial (B7)

Signal: `cap(D)` = USDT+USDC CoinMetrics daily caps summed; `impulse(D)=log(cap(D)/cap(D-30))`;
`z(D)=(impulse-mean)/std` over trailing <=730 impulse values ending at D (min 365, ddof=1, std==0->NaN).
Day D usable from D+1 04:00 UTC (asof `D+1 04:00 <= T`); NaN/unknown -> multiplier 1. File spans
2019-01-01..2026-09-23, so 2021-09-24..2026-09-23 is fully covered (no fallback needed).
Day shares: z<-1.0 16.9%, z<-1.5 4.5%, z>+1.0 14.9%. PLAN.md was written before any outcome; no
threshold/multiplier was changed after seeing numbers (only indexing bug-fixes in the engine script,
logged below). Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001/8h (00/08/16 UTC), shorts
nothing; limits fill only on 1m trade-through, no fill in the first 5 min after a 4h close,
stop-first in the same 1m bar.

## Leg 1 — book gate (4-phase engine; selection ONLY on dev years 2021-2024)

G2 reproduced exactly from `v421_runs.pkl` first: 5.41 %/mo, max yearly DD 16.91, full-path DD 16.82
(`reset_metric.year_reset` + `v388.mix`); the engine harness re-ran G2 bit-exact (same triple), so the
overlay comparison is valid. Mechanism = v426 copy: multiplier on STANDARD book rows with
bear-filtered weight>0, after the bear filter, before the shifted-clock ffill; shorts/flats/NaN-z
untouched; rows before 2021-09-24 not gated (v426 convention). G1: longs x0.75 if z<-1.0.
G2S: longs x0.75 if z<-1.5. CTRL: per-year constant long multiplier = G1's realised mean over long
cells in that year (0.8465 / 0.9876 / 1.0 / 0.9963 for Y0..Y3) — exposure-matched, no timing.

| dev year | G2 R/DD | G1 R/DD | G2S R/DD | CTRL R/DD | long cells gated G1/G2S |
|---|---|---|---|---|---|
| 2021-22 | 2.588 / 10.86 | 2.694 / 10.38 | 2.403 / 11.09 | 2.929 / 10.37 | 61.4% / 2.2% |
| 2022-23 | 3.282 / 16.91 | 3.209 / 16.82 | 3.289 / 16.91 | 3.317 / 16.98 | 4.9% / 0.0% |
| 2023-24 | 6.045 / 15.81 | 5.986 / 15.79 | 6.045 / 15.81 | 6.071 / 15.79 | 0.0% / 0.0% |
| 2024-25 | 10.677 / 8.27 | 10.434 / 8.33 | 10.677 / 8.27 | 10.657 / 8.29 | 1.5% / 0.0% |
| dev4 mean / worst / DD | 5.601 / 2.588 / 16.91 | 5.537 / 2.694 / 16.82 | 5.555 / 2.403 / 16.91 | 5.699 / 2.929 / 16.98 | 16.4% / 1.3% of all long cells |

Full-5y context (engine byproduct; NOT a selection input — no candidate, so the most recent year was
not scored for gated variants): G2 5.41/16.91/full-DD 16.82; G1 5.355/16.82/16.75; G2S 5.368/16.91/16.83;
CTRL 5.471/16.98/16.91. G1's only winning year (2021-22, where it gated 61% of longs) is more than offset
by small losses in the other three dev years; G2S fires on 1.3% of cells and only moves 2021-22 (down).
Verdict Leg 1: REJECT both — G1 dev4 R 5.537 < G2 5.601 and < CTRL 5.699 (timing worth less than nothing;
the level cut explains all of it); G2S dev4 R 5.555 < 5.601 with a worse worst year (2.403 < 2.588).

## Leg 2 — dip-budget dial (replica; PROMISING_5y calibrated on all five years — LABELLED + dev4 view)

Base reproduced exactly: 22312 kept fills, 5y 4-phase-mean sum 7.718304
(per-year S: 0.9113 / 0.8326 / 2.0998 / 3.1974 / 0.6772; DD: 0.856 / 0.951 / 0.800 / 0.355 / 0.607).
z at fills finite 100% (up 13.1%, down 24.8%). Same fills/legs, only weights change
(D1 x1.2308/z>1, x0.7692/z<-1; D2 upside-only x1.2308/z>1).

| year | base S/DD | D1 S/DD | D2 S/DD |
|---|---|---|---|
| 2021-22 | 0.9113 / 0.856 | 0.6845 / 0.789 | 0.9113 / 0.856 |
| 2022-23 | 0.8326 / 0.951 | 0.7595 / 0.951 | 0.8326 / 0.951 |
| 2023-24 | 2.0998 / 0.800 | 2.2898 / 0.905 | 2.2898 / 0.905 |
| 2024-25 | 3.1974 / 0.355 | 3.4281 / 0.405 | 3.4496 / 0.405 |
| 2025-26 | 0.6772 / 0.607 | 0.6143 / 0.607 | 0.6849 / 0.607 |

D1: sum>=base 2/5, DD ok 3/5, dSum5y +0.058 → NOT PROMISING (dev4: 2/4, 2/4, +0.121). The downside cut
fires exactly where dip fills were profitable (2021-22: 0.911→0.684) and adds DD where it fires up.
D2: sum>=base 5/5 (equalities in Y0/Y1 — no z>1 fills those years), dSum5y +0.450 (≥0.273), but DD ok
only 3/5 (2023-24 0.800→0.905 and 2024-25 0.355→0.405 both breach +0.01) → NOT PROMISING (dev4: 4/4
sum, 2/4 DD, +0.442). Upsizing winners scales drawdown faster than gains. Verdict Leg 2: REJECT both.

## Leakage / causality checks (how verified)

- Feature timing: daily availability (`D+1 04:00<=T`, searchsorted right-1); `tests/test_oc_stablegate.py::test_signal_truncation_causal`
  recomputes z(D0) from caps truncated to <=D0 (matches to 1e-9) and checks the avail boundary (±1s) exposes
  exactly the previous day's z; `test_handchecked_synthetic` checks the D+1 04:00 mapping on a 3-day frame.
- Label windows: none fitted (engine uses realised 1m path; dip uses realised exits; CTRL means are
  realised-exposure only, no returns).
- Fit windows: no fits — rolling 730d norm is a causal feature (window ends at D, all inputs known at
  D+1 04:00); thresholds (±1.0/±1.5) and multipliers fixed in PLAN before outcomes.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness, G2 bit-exact);
  dip live offsets 16..238 strict `low<level`, stop-first race, timeout at next-bar open (verbatim replica).

## Post-hoc log

- No definition changes after outcomes (thresholds, multipliers, windows, rules identical to PLAN).
- Two indexing bug-fixes in `compute_stablegate_engine.py` before the first successful run (bool-mask
  `.to_numpy()` removal; per-cell CTRL mean via broadcast) — no economic effect, harness proven by the
  bit-exact G2 re-run. Pre-2021-09-24 rows not gated (v426 convention, disclosed here).

## Vietnamese verdict (3 lines)

- Cả hai chân đều bị loại: cửa sổ book (G1/G2S) thua G2 trên dev4 và thua cả mức khống chế exposure-matched CTRL; núm ngân sách dip (D1/D2) đều không đạt PROMISING_5y (D2 được tổng nhưng vỡ chân DD 2/5 năm).
- Năm gần nhất không được chấm cho các biến thể gated (không có ứng viên nên dừng ở dev4 đúng theo quy tắc selection).
- Hướng supply-impulse này nên đóng lại, không cần thêm bằng chứng prospective cho dạng gate/budget-dial này.
