# oc_clockagree REPORT — IDEAS8 #5: Cross-clock agreement sizing

Method (PLAN pre-registered 2026-10-08, no changes): 4-phase engine replica of
v421 `R2B1D17BFG2` (rule inv, k 1.0, kd 1.7, bear True, G 2.0, agents ON v376
tables, win_start 5) over all 5 rows. Books from cached members
(`research_books_d2` = 0.8·o1 + 0.2·cb); REF replica asserts <1e-12 vs
`research_books_d2` (got 2.2e-16). Cross-clock values per standard bar T:
v0 = w[T], v1/2/3 = latest standard row ≤ T−3h/2h/1h (ffill, 0.0 on warm-up);
k = #{s: sgn(v_s)==sgn(v0)}; V1 = {1.0 k==4, 0.75 k==3, else 0.5}, V2 =
{1.0 k>=3 else 0.5}, zero-ensemble → scale 1.0; v421 ×0.5 bear filter after
scaling; direction = phase-0 sign (unchanged). Controls C_V1/C_V2 =
w_REF × per-year realised gross ratio (diagnostic, in-year, NOT eligible).
Script: `run_clockagree.py` (`--build-books` / `--shift S` via heavy_slot +
nohup + tmp logs / `--score`). Test: `tests/test_oc_clockagree.py` (7 passed).
REF reproduces `v421_result` G2 (5.41 / W 2.588 / DD 16.91 / full 16.82) TO THE
DIGIT (asserted in-script); if it had not, the study would have stopped.
Selection dev4-only among REF/V1/V2 (controls reported, not eligible).

## Per anchor year (R %/mo, DD %) — dev 2021-2024 for all; y4 scored ONCE for pick+REF

| year | REF G2 (=v421) | V1 (dev4 pick) | V2 | C_V1 (ctrl) | C_V2 (ctrl) |
|---|---|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.591 / 10.79 | 2.591 / 10.79 | 2.634 / 10.82 | 2.634 / 10.82 |
| 2022-09-24 | 3.282 / 16.91 | 3.254 / 16.91 | 3.254 / 16.91 | 3.269 / 16.79 | 3.269 / 16.79 |
| 2023-09-24 | 6.045 / 15.81 | 6.001 / 15.81 | 6.001 / 15.81 | 6.045 / 15.81 | 6.045 / 15.81 |
| 2024-09-24 | 10.677 / 8.27 | 10.653 / 8.27 | 10.653 / 8.27 | 10.671 / 8.28 | 10.671 / 8.28 |
| dev4 mean / worst / DDmax / losing | 5.601 / 2.588 / 16.91 / 0 | 5.578 / 2.591 / 16.91 / 0 | 5.578 / 2.591 / 16.91 / 0 | 5.608 / 2.634 / 16.79 / 0 | 5.608 / 2.634 / 16.79 / 0 |
| 2025-09-24 (REF + pick ONLY, labelled) | 4.648 / 12.90 | 4.622 / 13.00 | NOT_SCORED | NOT_SCORED | NOT_SCORED |
| 5y mean (dev4 + scored y4) | 5.410 | 5.386 | NOT_SCORED | NOT_SCORED | NOT_SCORED |
| full-path DD (marked/close/full) | 16.82 (native continuous) | 16.82 | NOT_SCORED | NOT_SCORED | NOT_SCORED |

Dev4 pick: all three eligible (DD ≤ 20, no losing, mean ≥ 5); highest WORST →
**V1** (2.591 vs REF 2.588; V1/V2 tie on worst AND mean → first-listed V1).
Effect (V1−REF): dev4 −0.023 pp/mo, y4 −0.026, 5y −0.024; DDmax ±0.00;
full-path ±0.00. V1−C_V1 dev4: 5.578 vs 5.608 = −0.030 pp/mo (trails its
exposure control → pure exposure story, worse than a dumb constant cut).
V1==V2 on every one of 54750 standard cells (k==3 count 0 in all 5 years;
k==2 count 0; k==1 share 2.0–3.7%/yr; mean scale 0.986–0.991; gross ratio
≈0.9988) — the pre-registered degeneracy holds exactly, so V2 is not an
independent variant in practice. Gate check on pick: 5y 5.386 ≥ 5 ✓,
y4 4.622 < 5 ✗, no losing ✓, DD 16.82 ≤ 20 ✓ → FAILS gate rule (b).

## Book episodes + fee split (per year; book-only P&L not separable from equity)

| year | REF book n / win | V1 book n / win | rung n / win (REF → V1) | maker / taker fees (REF → V1, equity units) |
|---|---|---|---|---|
| 2021 | 926 / 0.5032 | 927 / 0.5027 | 4075 / 0.6378 → same | 0.025251 / 0.002126 → 0.025271 / 0.002126 |
| 2022 | 861 / 0.5122 | 862 / 0.5104 | 3941 / 0.6892 → same | 0.033369 / 0.012190 → 0.033314 / 0.012285 |
| 2023 | 1002 / 0.5150 | 1001 / 0.5135 | 4977 / 0.7320 → 4975 / 0.7319 | 0.034180 / 0.014682 → 0.034378 / 0.014909 |
| 2024 | 1163 / 0.5064 | 1164 / 0.5060 | 3847 / 0.7193 → same | 0.039105 / 0.011228 → 0.039362 / 0.011351 |
| 2025 (pick+REF) | 1112 / 0.5378 | 1112 / 0.5387 | 4671 / 0.6478 → same | 0.034158 / 0.012194 → 0.034339 / 0.012177 |

Book win moves −0.002..+0.001 (noise on ~1000 episodes/yr); no win-rate gain.
Dip untouched (rung counts/wins identical up to ±2 rungs from book-timing
knock-ons). Exposure per year (gross ratio vs REF): V1/V2 =
0.9980/0.9991/0.9989/0.9989/0.9988 — the idea cuts only ~0.1% gross (k==1 on
2.6% of cells halved), so even a perfect timing story had almost no room.

## What failed / limits (honest)

- The literal ffill operationalisation degenerates to binary persistence sizing
  (k ∈ {1,4}; k==2/3 count exactly 0 all years), so V1/V2 coincide bit-exact
  and the V1 middle branch (×0.75) never fires — the two pre-registered
  variants are one experiment, not two.
- The tiny 0.1% exposure cut cannot move the needle (dev4 −0.023pp, y4 −0.026pp);
  worse, it trails its exposure-matched constant control (−0.030pp dev4), so
  there is no consensus TIMING value beyond (below) a mere exposure cut.
- Y4 for V2/controls redacted to NOT_SCORED per protocol (engine necessarily
  covers the full span; selection used dev4 only — `robust_pick` reads dev4_*
  fields exclusively; the redaction is in `results.json`, verifiable in code).
- Book-only P&L not separable (engine stores t/eq/eq_min only, same as v421);
  trade counts/win rates are the decomposition. No prospective log for this
  direction (rejected on dev4 + control, y4 only confirms).

## Leakage checklist

- Feature timing: v_s use standard rows with bar time ≤ their clock close ≤ T
  (searchsorted ffill; identity at s=0); shifted clocks use latest standard row
  r ≤ t_s. Truncation-tested on synthetic + real member files (rows ≤ T
  unchanged when later rows removed; 7 pytest passed).
- Label windows: none (no labels; agreement is a frozen sign count).
- Fit windows: none (books read-only caches; scales are frozen integers
  4/3/2 → 1.0/0.75/0.5; C_Vx use in-year realised means, labelled
  diagnostic/non-eligible, never picked).
- Fill timing: real `eu.simulate` (limit trade-through, no fill minutes 0–4,
  stop-first, Bybit maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h).
- y4 scored once for pick V1 + REF; loser V2 and controls y4 NOT_SCORED.

## Vi (3 dong)

- Size theo dong thuan 4 clock ve dung nhu du bao la nhi phan cung-rem (k chi 1/4, V1==V2 tren 100% o), chi cat ~0.1% exposure nen dev4 −0.023pp, nam moi nhat −0.026pp, ROT gate (b).
- Te hon ca control cat-exposure mu (dev4 5.578 vs 5.608, −0.030pp): khong co gia tri timing nao, win book dung yen +-0.1pp.
- Quyet dinh: REJECT de dua vao san xuat, dong huong nay (khong can prospective log); neu mo lai phai dinh nghia agreement khac co phan biet that (khong phai ffill) va dang ky moi.
