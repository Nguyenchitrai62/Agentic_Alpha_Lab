# oc_carryd13 REPORT — frozen cash-carry sleeve overlaid on the low-DD row D13BF

Question (stretch DD < 15 with base return >= 5): does the stored low-DD row
plus the carry sleeve meet 5y >= 5.0 %/mo AND max yearly DD < 15 AND full-path
DD < 15 AND no losing year? Method: base = stored 4-phase hourly equity
(`v424_runs.pkl`) via `reset_metric.year_reset` exactly; carry = frozen
`oc_cashcarry` rule reused verbatim (roll next-quarter at <= 7 d, enter iff
ann basis >= 4 %, equal-notional spot long + quarterly short, hold to
delivery, fees 0.001/side + 0.00055/0.0002), marked HOURLY (causal:
last closed hourly bar strictly before t; 0 before entry-bar close; locked
to frozen ret_alloc from settlement-bar close), sized f of year-start equity
(yearly rebalance, labelled), rebased to 0 at each anchor; combined es/ms =
base es/ms + carry curve; 5y mean = geometric mean of yearly monthly factors
(same as v424); full-path DD = chained-reset path (labelled). POST-HOC,
REPORTING ONLY: these rows were already scored on all five years; the carry
rule itself was fixed before any combination. Repro:
`research/tournament/oc_carryd13/{combine_carryd13.py,results.json}`;
test `tests/test_oc_carryd13.py`. 4h+1h data only, one process, no engine reruns.

## Which rows qualified (max yearly DD < 15 scanned in v424 + v425 result jsons)

- v424: R2B1D17BF 18.33, R2B1D13BF 14.98, R2B1D14BFX5 15.34, F20K17BFX5 15.69.
- v425: R2B1D17BF 18.33, D13BFG2 15.07, D14BFG2 15.55, D14BFX5G2 15.54, D15BFG2 16.24.
- ONLY v424/R2B1D13BF qualifies (14.98). v425 has no row < 15 (nearest D13BFG2
  15.07). v421 G2 rows read for reference only (16.91 / 18.33 / 18.33, none < 15).

## Base reference (official vs recomputed via the shared reset function)

- v424/R2B1D13BF official: 5y 4.971, worst 2.485, max yearly DD 14.98,
  full-path DD 14.86 (continuous-mix convention).
- Recomputed here: 5y 4.971, worst 2.485, max DD 14.98 (gaps 0.000) +
  chained-reset full-path DD 14.98 (same chaining as the combos; +0.12 vs the
  official continuous convention — convention gap, not a finding).

## Combos (per anchor year R %/mo and DD %; base in brackets)

v424/R2B1D13BF @ f=0.25 — 5y 5.104, worst 2.634, max yearly DD 14.85,
chained full-path DD 14.85, losing years 0:

| year | R (base) | DD (base) |
|---|---|---|
| 2021-09-24 | 2.634 (2.485) | 10.05 (10.21) |
| 2022-09-24 | 3.338 (3.286) | 14.85 (14.98) |
| 2023-09-24 | 5.292 (4.975) | 14.63 (14.76) |
| 2024-09-24 | 9.640 (9.526) | 7.33 (7.33) |
| 2025-09-24 | 4.754 (4.723) | 10.84 (10.97) |

v424/R2B1D13BF @ f=0.50 — 5y 5.234, worst 2.781, max yearly DD 14.71,
chained full-path DD 14.71, losing years 0:

| year | R (base) | DD (base) |
|---|---|---|
| 2021-09-24 | 2.781 (2.485) | 9.88 (10.21) |
| 2022-09-24 | 3.390 (3.286) | 14.71 (14.98) |
| 2023-09-24 | 5.599 (4.975) | 14.58 (14.76) |
| 2024-09-24 | 9.754 (9.526) | 7.32 (7.33) |
| 2025-09-24 | 4.785 (4.723) | 10.72 (10.97) |

Win rate note (both f): BOT all-trade win rate UNCHANGED — the overlay is
equity-level and adds zero trades (`v424_runs.pkl` stores only t/eq/eq_min
for these rows, so no trade-level rate is recomputed here). Carry pairs are
33/33 net positive on allocated capital per oc_cashcarry, reported separately.

## Verdict

YES — both combinations meet all four bars on the stated conventions:
f=0.25: 5.104 >= 5.0, max yearly DD 14.85 < 15, chained full-path DD
14.85 < 15, no losing year. f=0.50: 5.234, 14.71, 14.71, no losing year.
The sleeve added return (+0.13pp at f=0.25, +0.26pp at f=0.50 on the 5y mean;
smaller than the sleeve-alone +0.21/+0.42 because the same absolute carry
accrual is a smaller rate on top of strong base years) and did NOT add DD —
yearly DD fell 0.0-0.3pp (carry MtM troughs do not coincide with base
troughs; the positive drift raises the peak denominator). Margins: 0.13pp
(f=0.25) and 0.29pp (f=0.50) above the 5.0 line; DD margin 0.15pp/0.29pp below
15 — thin, and the carry leg is close-marked (no intra-hour low), so treat the
DD side as a lower bound. Honest context: post-hoc combination on the same
five research years (labelled, no selection claim); needs the same
prospective paper check as everything else. Gap: `oc_carrycombo/` has no stored
implementation in this repo, so "exactly as oc_carrycombo does" is realised as
the hourly-mark + equity-level + reset-metric method defined in the script
docstring (same three named properties). No new predictive features were
built (VF_COMMON feature-study rules: not applicable, no `compute`/`events`).
