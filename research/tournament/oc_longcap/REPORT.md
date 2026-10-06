# oc_longcap REPORT: total book-long cap at 0.6 (idea #46)

Book = `forward_v205.research_books_d2` (rebuilt exactly, same code as
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter applied FIRST (longs
x0.5 where BTC 4h open < rolling-1200 mean, min 600; BASE validated
cell-exact vs oc_bookcorr: book P&L and maxDD identical all 5 years).
Rule (fixed in PLAN.md): per bar `T`, `L(T)` = sum of positive BASE
weights; if `L(T) > 0.6`, scale all longs by `0.6/L(T)` (shorts/flats
bit-identical). Screen = open-to-open 4h returns with gate costs: net
cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0; each path
its own prev). Long-leg sums use the BASE sign so both paths compare
identical rows. Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. No post-hoc change to hypothesis, definitions,
threshold, or decision rule (see caveats for a disclosure on
floating-point ties, which does not change the verdict).

## Long-weight-sum distribution on BASE (reported first)

| scope | mean | p50 | p75 | p90 | p95 | p99 | max | share L>0.6 | share L>0.8 | share L>1.0 | mean L \| binding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| overall (10955 bars) | 0.2268 | 0.1687 | 0.3541 | 0.5735 | 0.6983 | 0.9312 | 1.3961 | 0.0906 | 0.0246 | 0.0050 | 0.7533 |
| 21-22 | 0.1386 | 0.0627 | 0.2207 | 0.3361 | 0.3570 | 0.9936 | 1.0000 | 0.0338 | 0.0301 | 0.0000 | 0.9066 |
| 22-23 | 0.2237 | 0.2038 | 0.3632 | 0.4791 | 0.5861 | 0.7100 | 0.7824 | 0.0479 | 0.0000 | 0.0000 | 0.6750 |
| 23-24 | 0.2582 | 0.2065 | 0.4287 | 0.5980 | 0.6917 | 0.8716 | 1.1451 | 0.0993 | 0.0173 | 0.0014 | 0.7157 |
| 24-25 | 0.3091 | 0.2945 | 0.4594 | 0.6631 | 0.7678 | 0.8450 | 0.9204 | 0.1356 | 0.0370 | 0.0000 | 0.7315 |
| 25-26 | 0.2042 | 0.0911 | 0.2961 | 0.6608 | 0.7441 | 1.1496 | 1.3961 | 0.1361 | 0.0384 | 0.0238 | 0.7921 |

Read: the 0.6 cap binds on 9.1% of bars overall (3.4% in 21-22 rising to
13.6% in 24-25/25-26); conditional mean scale on binding bars is 0.819
(about an 18% long trim when it binds). Extreme long stacks (L > 1.0)
are rare (0.5% overall).

## Per-year screen (net, portfolio-return units; costs included)

| year | bind share | book P&L base / capped (retention) | long-leg P&L base / capped | worst week base / capped | maxDD base / capped | DD not worse | ret >= 95% |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.0338 | 0.291959 / 0.258326 (0.885) | 0.153468 / 0.119833 | -0.055143 / -0.055143 | 0.086514 / 0.086514 | no* | no |
| 22-23 | 0.0479 | 0.252013 / 0.227138 (0.901) | 0.228949 / 0.204073 | -0.046676 / -0.046676 | 0.071462 / 0.071462 | no* | no |
| 23-24 | 0.0993 | 0.564138 / 0.490090 (0.869) | 0.607182 / 0.533133 | -0.069232 / -0.069232 | 0.087278 / 0.087278 | no* | no |
| 24-25 | 0.1356 | 0.539535 / 0.511617 (0.948) | 0.494588 / 0.466668 | -0.045264 / -0.038961 | 0.062817 / 0.062817 | no* | no |
| 25-26 | 0.1361 | 0.413608 / 0.350765 (0.848) | 0.235489 / 0.172646 | -0.074825 / -0.064734 | 0.085657 / 0.076884 | yes | no |

Counts: DD not worse 1/5 strict (see * note); retention >= 95% 0/5
(best 0.948 in 24-25, worst 0.848 in 25-26). Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.100471; total P&L
2.061253 -> 1.837937 (retention 0.892). LOYO stability (descriptive):
DD 4/5, retention 5/5 (unanimous fail is stable).

\* DD-tie disclosure (no rule change): in 2021-2024 the capped maxDD is
identical to base at 6dp; the unrounded capped-minus-base gaps are
+3.1e-15, +3.3e-16, +2.2e-16, +7.8e-16 — pure floating-point summation
noise (the cap does not move any peak/trough in those years), while 2025
improves by -8.8e-03. Counting fp-ties as "not worse" would make the DD
leg 5/5, but the retention leg is still 0/5, so the verdict is unchanged
either way.

## Gate-grind window 2023-04-17..06-15 (357 4h bars)

| | binding share | book P&L | long-leg P&L |
|---|---|---|---|
| BASE | — | -0.049863 | -0.076115 |
| CAPPED | 0.0532 | -0.051109 | -0.077361 |

The cap binds on only 5.3% of the grind window and makes the window loss
slightly worse (-0.0499 -> -0.0511 book; long leg -0.0761 -> -0.0774):
the grind's long bleed is spread across non-binding bars, so a 0.6 total
cap trims winners elsewhere without touching the episode.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, threshold (0.6), or
   decision rule. PLAN.md was written before `compute_longcap.py` ran.
2. Performance-only implementation (verified, not outcome-driven):
   vectorised cap via `np.where`; BASE validated cell-exact vs
   oc_bookcorr (all 5 yearly book P&L and maxDD match).
3. The DD leg's 1/5 strict count rests on fp noise (see * note); the
   honest reading is DD-neutral in 4 years + improved in 2025 — but the
   retention leg fails outright in all 5 years (0.848-0.948), so the
   verdict does not depend on tie-handling.
4. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). Needs prospective
   validation; all five years were available when the idea was scored.

## One-line verdict

NOT PROMISING: total book-long cap at 0.6 binds on 9.1% of bars but
retains >= 95% of book P&L in 0/5 years (0.848-0.948) with book maxDD
not worse in 1/5 years strict (4 ties at fp noise + 1 real improvement),
and worsens the 2023-04-17..06-15 grind loss (-0.0499 -> -0.0511).
