# oc_clockweights REPORT — IDEAS6 #6: Adaptive 4-clock capital share (yearly weights)

Method: overlay accountant on stored G2 (`v421_runs.pkl`, `R2B1D17BFG2`) + reset
metric. At each anchor, capital weights from the trailing 365d ending 7d before
the anchor (embargo), frozen all year, sum 1: V1 ∝ 1/trailing max-DD (marked,
clip [1,100]); V2 ∝ max(trailing hourly Sharpe·√8760, 0), else equal. y0 has no
history → 1/4. Per-year R/DD = weighted reset (rebased per phase, same pk
convention as `reset_metric.year_reset`). Full-path DD: REF = native continuous
mix (v421); variants = yearly-weighted compounding stitch (year y covers
(A_y, A_{y+1}], y4 to +365d, so every grid point is assigned — this also covers
the leap day 2024-09-23→24 that the 365d reset convention skips). f=0-equivalent
(REF) reproduces `v421_result.json` G2 (5.41 / W 2.588 / DD 16.91 / full 16.82)
TO THE DIGIT (asserted in-script). Engine confirm NOT run (overlay exact at 1x
under linear sizing; no new orders). Script: `compute_clockweights.py`.
PLAN.md frozen pre-outcome; selection dev4-only.

## Per anchor year (R %/mo, DD %) — dev 2021-2024 for all; y4 scored ONCE for pick+REF

| year | REF G2 (=v421) | V1 invDD | V2 sharpe (dev4 pick) |
|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.588 / 10.86 | 2.588 / 10.86 |
| 2022-09-24 | 3.282 / 16.91 | 3.245 / 17.02 | 3.512 / 16.63 |
| 2023-09-24 | 6.045 / 15.81 | 6.093 / 15.78 | 6.664 / 15.41 |
| 2024-09-24 | 10.677 / 8.27 | 10.551 / 8.28 | 10.494 / 8.86 |
| dev4 mean / worst / DDmax / losing | 5.601 / 2.588 / 16.91 / 0 | 5.573 / 2.588 / 17.02 / 0 | 5.770 / 2.588 / 16.63 / 0 |
| 2025-09-24 (REF + pick ONLY, labelled) | 4.648 / 12.90 | NOT_SCORED | 4.677 / 12.78 |
| 5y mean (dev4 + scored y4) | 5.410 | — (not picked) | 5.550 |
| full-path DD (marked/close/full) | 16.82 (native continuous) | — | 16.63 / 15.88 / 16.63 (stitched) |

Weights used (p0..p3): 2022 V1 [.283,.187,.277,.253] V2 [.425,.299,.182,.093];
2023 V1 [.250,.270,.244,.235] V2 [.276,.285,.279,.160];
2024 V1 [.351,.270,.255,.124] V2 [.536,.189,.276,.000] (p3 Sharpe −0.683 → 0);
2025 V1 [.266,.188,.283,.263] V2 [.237,.211,.293,.258].
Dev4 pick: both eligible (DD ≤ 20, no losing, mean ≥ 5), worst tied 2.588 →
ties → higher mean → **V2_sharpe** (5.770 vs 5.573; REF 5.601).
Effect (V2−REF): dev4 +0.169 pp/mo, y4 +0.029, 5y +0.140; DDmax −0.28 (dev and
5y); full-path −0.19. V1 trails REF on dev4 mean (−0.028) and DDmax (+0.11).
Win rates: N/A — `v421_runs.pkl` holds t/eq/eq_min only, no trade ledger
(needs engine confirm). Fee/funding split: N/A for the same reason; stored
equity is already net of gate costs (maker 0.0002, taker 0.00055, longs
0.0001/8h). Gate check on pick: 5y 5.55 ≥ 5 ✓, y4 4.677 < 5 ✗, no losing ✓,
DD 16.63 ≤ 20 ✓ → FAILS gate rule (b). Fix note (disclosed, pre-report): the
first stitch left the leap day 2024-09-23→24 unassigned (NaN→0, fake DD 73.14);
fixed to cover (A_y, A_{y+1}] with a full-coverage assert — per-year outcomes
and the pick are unchanged (reset convention untouched).

## Leakage checklist
- Feature timing: weights from hourly closes only (known at close); y0 fallback (no history).
- Label windows: none (no labels; trailing stats are realised equity, not returns-to-predict).
- Fit windows: trailing [A−372d, A−7d] only (n = 8589/8760/8760/8760 h; y0 = 0 → fallback); never the test year.
- Fill timing: unchanged from G2 engine (limit maker, SL market taker, TP limit maker, trade-through, minute-0–4 ban, stop-first, expiry); overlay only rescales capital shares.
- y4 scored once for pick + REF; loser V1 y4 NOT_SCORED.

## Vi (3 dong)
- Chia von theo Sharpe thang nam truoc chi hon G2 deu 1/4 chut it (5y +0.14pp, DD −0.2), nam moi nhat 4.677 khong dat moc 5 nen ROT gate.
- Bien the nghich-DD con te hon deu (mean −0.03, DDmax +0.11), trong so 0 cho dong ho 3 nam 2024 cho thay Sharpe de vot cuc doan.
- Quyet dinh: REJECT de dua vao san xuat, can bang chung prospective neu muon ghep tiep.
