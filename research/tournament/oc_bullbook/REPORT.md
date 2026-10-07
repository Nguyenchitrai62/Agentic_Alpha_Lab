# oc_bullbook REPORT: bull-regime book boost (idea #26)

Book = `forward_v205.research_books_d2` (rebuilt exactly, same code as
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter (longs x0.5 where BTC
4h open < its 1200-bar mean, rolling 1200/min 600 on full history from
2017). BOOST = BASE + longs x1.25 where BTC open > 1200-bar mean AND BTC
180-bar (30-day) return > 0 (strict; equality/NaN -> neither; shorts/flat
never touched; bear rows keep x0.5). Screen = open-to-open 4h returns with
0.05%/unit L1 turnover (each path with its OWN prev, first prev = 0; no
vol scale). Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Long-leg sums use ORIGINAL `w > 0` rows so both paths
compare identical rows. Full tables in `results.json`.

## Verdict

NOT PROMISING (as assigned): book P&L higher in 5/5 years but book maxDD
not worse in 0/5 years — the boost buys return with drawdown in every
single year, the opposite of the v410 bear filter's economics.

## Per-year screen (net, portfolio-return units; costs included)

| year | bear / bullboost share | book P&L base / boost | long-leg P&L base / boost | worst week base / boost | maxDD base / boost | P&L higher | DD not worse |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.763 / 0.112 | 0.278895 / 0.297757 | 0.146420 / 0.165282 | -0.055289 / -0.061175 | 0.092278 / 0.101053 | yes | no |
| 22-23 | 0.407 / 0.357 | 0.235444 / 0.289114 | 0.219915 / 0.273603 | -0.047268 / -0.059534 | 0.073721 / 0.081583 | yes | no |
| 23-24 | 0.217 / 0.559 | 0.544150 / 0.679573 | 0.595114 / 0.730570 | -0.069471 / -0.069471 | 0.087902 / 0.087902 | yes | no |
| 24-25 | 0.138 / 0.584 | 0.517693 / 0.625432 | 0.480437 / 0.588223 | -0.045930 / -0.057693 | 0.065296 / 0.084173 | yes | no |
| 25-26 | 0.804 / 0.144 | 0.394724 / 0.437642 | 0.226569 / 0.269490 | -0.075345 / -0.075345 | 0.087166 / 0.101983 | yes | no |

Counts: P&L higher 5/5; DD not worse 0/5 (2023 DD equal at 1e-6 — the DD
episode sits in a non-boosted stretch — still a FAIL under the strict<
rule). Full 5y path (context): total P&L 1.970907 -> 2.329518 boosted
(+0.359 over 5y, all long-leg); maxDD 0.104644 -> 0.112907 boosted.
Turnover 301.15 -> 332.38 (cost 0.1506 -> 0.1662); the cost delta (0.016)
is an order of magnitude below the P&L delta, so the return gain is gross,
not a cost artefact. LOYO stability (descriptive, no fitted parameter):
P&L effect positive in all 5 held-out years, 5/5 — the return leg is
stable, the DD leg fails everywhere.

## Combined (book + dip) daily context (linear path, native units)

Dip = `harness5.load` BOT rungs (majors + size_dep, y_dep exact net), daily
sums by UTC day; book daily = `sum(rp)` by UTC day; combined = book + dip
(dip stream identical in both variants, so the delta is pure book effect;
absolute levels are NOT engine equity). Linear per-year cumsum path,
peak-to-trough decline in native units:

| year | dip daily sum | book daily base / boost | combined DD base / boost | comb DD not worse |
|---|---|---|---|---|
| 21-22 | 4.484898 | 0.278895 / 0.297757 | 1.050836 / 1.050836 | no (equal) |
| 22-23 | 0.923804 | 0.235444 / 0.289114 | 2.170932 / 2.165618 | yes |
| 23-24 | 6.627248 | 0.544150 / 0.679573 | 1.031128 / 1.030503 | yes |
| 24-25 | 4.265046 | 0.517693 / 0.625432 | 1.130446 / 1.131226 | no |
| 25-26 | 1.905913 | 0.394724 / 0.437642 | 0.650363 / 0.668079 | no |

Combined DD not worse 2/5 — dip-dominated (dip sums 2-12x the book sums),
no drawdown relief from the boost at the combined level either.

Read: the mirror does not mirror. The bear filter cut exposure where longs
lose; the bull boost adds exposure where longs win — but the extra size is
still on during the selloffs inside/after bull regimes, so every year's
peak-to-trough widens (worst week worse or equal in 5/5). Return without
drawdown control is not what this direction needs; close idea #26.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, regimes, multipliers, or
   the decision rule. PLAN.md was written before `compute_bullbook.py` ran.
2. Measurement-unit fix (verified, not outcome-driven): the pre-registered
   combined path compounded `(1 + C)` on book+dip daily sums, but dip daily
   sums are size*y native units, NOT equity fractions (first run printed
   daily sums of -1.93 and DD > 2, impossible for a return path). Combined
   context now uses the per-year LINEAR cumsum path with peak-to-trough
   decline in native units; the BOOK path (fractions, |rp| << 1) keeps the
   pre-registered compounded maxDD. The verdict never depended on the
   combined leg (context only).
3. Performance-only fix (verified): long-leg sums first returned NaN
   (boolean-DataFrame `df[mask]` keeps NaN cells); recomputed with
   `.where(mask).sum()` (skipna) over the same fixed ORIGINAL-long rows.
4. Vectorised open-to-open screen only (no vol target, governor, funding,
   SL/TP, sleeve sizing, or engine limit path); maker-style cost only
   (0.0005/unit turnover, each path's own turnover). All five years were
   available when the rule was frozen (assignment); no hidden year remains
   — prospective validation still required before any adoption (none
   proposed: the verdict is negative).

## One-line verdict

NOT PROMISING: bull-regime long boost (x1.25 where BTC open > 1200-bar
mean and 30-day return > 0) raises book P&L in 5/5 years but worsens book
maxDD in 5/5 years (0/5 not-worse; combined dip context 2/5) — return
bought with drawdown, close the direction.
