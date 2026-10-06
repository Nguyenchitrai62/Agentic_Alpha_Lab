# oc_bookcorr REPORT: correlation-scaled book exposure (idea #43)

Book = `forward_v205.research_books_d2` (rebuilt exactly, same code as
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = audited v410 bear filter applied FIRST (longs
x0.5 where BTC 4h open < its 1200-bar mean, rolling 1200/min 600 on full
history from 2017; shorts/flat unchanged). SCALED = BASE x s(T) on ALL
five coins, `s(T) = clip(1.5 - rho(T), 0.5, 1.0)`, `rho(T)` = mean of the
10 pairwise Pearson correlations of the majors' 4h log returns over the
180 bars strictly before T (>= 120 overlapping points per pair, >= 8/10
pairs else NaN -> s = 1.0). Screen = open-to-open 4h returns with
maker-style cost 0.0002/unit L1 turnover (each path with its OWN prev,
first prev = 0; no vol scale). Equity per year reset to 1 and compounded
as `eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows.

## Verdict

NOT PROMISING (as assigned): book maxDD improves in 5/5 years but book
P&L retains >= 90% of BASE in only 1/5 years (retention 73-92%) — the
scale buys drawdown relief with a proportional return haircut in every
year.

## Per-year screen (net, portfolio-return units; costs included)

| year | mean rho / avg scale | book P&L base / scaled | retention | worst week base / scaled | maxDD base / scaled | DD improves | ret >= 90% |
|---|---|---|---|---|---|---|---|
| 21-22 | 0.773 / 0.727 | 0.291959 / 0.213953 | 0.733 | -0.055143 / -0.049504 | 0.086514 / 0.072453 | yes | no |
| 22-23 | 0.694 / 0.806 | 0.252013 / 0.221548 | 0.879 | -0.046676 / -0.035116 | 0.071462 / 0.061901 | yes | no |
| 23-24 | 0.647 / 0.853 | 0.564138 / 0.519753 | 0.921 | -0.069232 / -0.054848 | 0.087278 / 0.070194 | yes | yes |
| 24-25 | 0.685 / 0.815 | 0.539535 / 0.449738 | 0.834 | -0.045264 / -0.038337 | 0.062817 / 0.055985 | yes | no |
| 25-26 | 0.801 / 0.699 | 0.413608 / 0.307819 | 0.744 | -0.074825 / -0.057922 | 0.085657 / 0.069057 | yes | no |

Counts: DD improves 5/5; retention >= 90% 1/5. Full 5y path (context,
compounded from year-1 start): total P&L 2.061253 -> 1.712810 scaled
(-0.348 over 5y); maxDD 0.100471 -> 0.086262 scaled. Rho coverage 100% all years; share of bars
with s < 1.0 is ~98-100% (the rho <= 0.5 floor almost never binds).
LOYO stability (descriptive, no fitted parameter): DD indicator 5/5,
retention indicator 4/5.

## Combined (book + dip) daily context (linear path, native units)

Dip = `harness5.load` BOT rungs (majors + size_dep, y_dep exact net),
daily sums by UTC day; book daily = `sum(rp)` by UTC day; combined = book
+ dip (dip stream identical in both variants, so the delta is pure book
effect; absolute levels are NOT engine equity). Linear per-year cumsum
path, peak-to-trough decline in native units:

| year | dip daily sum | book daily base / scaled | combined DD base / scaled | comb worst day base / scaled |
|---|---|---|---|---|
| 21-22 | 4.484898 | 0.291959 / 0.213953 | 0.562952 / 0.556170 | -0.414037 / -0.418898 |
| 22-23 | 0.923804 | 0.252013 / 0.221548 | 1.929616 / 1.927615 | -1.927831 / -1.926066 |
| 23-24 | 6.627248 | 0.564138 / 0.519753 | 0.563516 / 0.565693 | -0.563516 / -0.565693 |
| 24-25 | 4.265046 | 0.539535 / 0.449738 | 0.701592 / 0.701693 | -0.701592 / -0.701693 |
| 25-26 | 1.905913 | 0.413608 / 0.307819 | 0.648691 / 0.635335 | -0.519087 / -0.515768 |

Combined DD moves by <= 0.013 in every year (dip-dominated: dip sums are
2-12x the book sums) — no material combined-drawdown relief, and the
worst day is set by the dip stream in all years.

## Read

The mechanism works as hypothesised on drawdown (every year's book maxDD
and worst week improve) but the fixed `1.5 - rho` mapping is nearly
always-on: trailing 30-day cross-coin correlation of the majors sits at
0.65-0.80 in every year, so the book runs at 0.70-0.85x exposure on ~100%
of bars. That is a quasi-permanent ~15-30% deleveraging, and the P&L
haircut is proportional (retention tracks average scale almost 1:1:
0.73/0.73, 0.88/0.81, 0.92/0.85, 0.83/0.82, 0.74/0.70). There is no
regime-switching edge here — only the trivial vol-of-exposure trade.
A thresholded variant (scale only above, say, rho 0.8) would be a NEW
idea with its own pre-registration, not a follow-up tweak of this result.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, window, clip, costs, or
   the decision rule. PLAN.md was written before `compute_bookcorr.py`
   ran.
2. Cross-checks (verified, not outcome-driven): the BASE path reproduces
   oc_bullbook's BASE book P&L to within the cost-model delta (0.0002 vs
   0.0005 turnover) in all five years; dip daily sums match oc_bullbook's
   to 1e-6; grid bar count (10955) matches oc_dvolshort/oc_bullbook.
3. If BASE P&L had been <= 0 in any year, that year would count as FAIL
   for leg (b) per PLAN.md; BASE was positive in all five years, so the
   clause did not trigger.
4. Vectorised open-to-open screen only (no vol target, governor, funding,
   SL/TP, sleeve sizing, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own turnover). All five years were
   available when the rule was frozen (assignment); no hidden year
   remains — prospective validation still required before any adoption
   (none proposed: the verdict is negative).

## One-line verdict

NOT PROMISING: correlation scaling (x clip(1.5 - rho, 0.5, 1.0) on the
bear-filtered book) cuts book maxDD in 5/5 years but keeps >= 90% of book
P&L in only 1/5 years (retention 73-92%, tracking the 0.70-0.85 average
scale) — proportional deleveraging, not a drawdown edge; close idea #43.
