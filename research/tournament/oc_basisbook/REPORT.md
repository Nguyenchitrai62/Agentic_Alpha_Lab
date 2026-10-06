# oc_basisbook REPORT — quarterly-basis MOMENTUM gate on book longs (idea #61)

Book = `forward_v205.research_books_d2` (rebuilt exactly, cell-checked vs
oc_dvolshort); opens = v154 4h opens. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC; last bar dropped, no forward open) x 5
coins = 54775 rows. BASE = v410 BTC-only bear filter FIRST (longs x0.5 when
BTC 4h open < 1200-bar mean, rolling 1200 min 600, open[T] inclusive;
per-year base P&L / maxDD reproduce oc_bearshort's v410 base exactly:
total 2.061253, full-path DD 0.100471). RULE = BASE with LONG targets x0.5
on de-leveraging impulse bars (`mom = basis(T) - basis(T-7d) < walk-forward
p20`; BTC front-quarterly annualised basis from `qbasis_features_4h` with
`close_time` strictly `< T` for both legs, no fill-forward; bear+impulse
longs 0.25x raw, shorts/flats/NaN untouched). Screen = open-to-open 4h
returns with gate costs, exactly as oc_dvolshort/oc_bearshort: net cell =
`w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0; each path its own
prev chain). Long-leg sums use BASE sign (`w_base > 0`) so base vs rule
compare identical rows. Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. PLAN.md was written before `compute_basisbook.py` ran;
no post-hoc changes. Impulse thresholds are strictly walk-forward
(`p20_k` from engine 4h grid bars in [2020-08-01, A_k), n_train
2514/4704/6894/9090/11280, coverage 1.0 every year), so LOYO is N/A by
construction — but all five years were available when the idea was scored,
so this still needs prospective validation.

## Verdict

NOT PROMISING (as assigned): total book P&L kept (>= 97% of base) in 4/5
years AND maxDD not worse in only 3/5 years (needs >= 4/5 on both).

## Per-year screen (net, portfolio-return units; costs included)

| year | p20 | flagged share | longs scaled | long P&L base / rule | total book P&L base / rule | ratio | worst week base / rule | maxDD base / rule | P&L kept | DD not worse |
|---|---|---|---|---|---|---|---|---|---|---|
| 21-22 | -0.053367 | 0.027 | 0.035 | 0.153468 / 0.174341 | 0.291959 / 0.312835 | 1.0715x | -0.055143 / -0.051956 | 0.086514 / 0.070835 | yes | yes |
| 22-23 | -0.027702 | 0.058 | 0.046 | 0.228949 / 0.227136 | 0.252013 / 0.250203 | 0.9928x | -0.046676 / -0.046676 | 0.071462 / 0.070956 | yes | yes |
| 23-24 | -0.019767 | 0.168 | 0.175 | 0.607182 / 0.588317 | 0.564138 / 0.545285 | 0.9666x | -0.069232 / -0.069454 | 0.087278 / 0.087999 | no | no |
| 24-25 | -0.018551 | 0.132 | 0.129 | 0.494588 / 0.485558 | 0.539535 / 0.530519 | 0.9833x | -0.045264 / -0.048676 | 0.062817 / 0.064786 | yes | no |
| 25-26 | -0.017200 | 0.053 | 0.047 | 0.235489 / 0.255281 | 0.413608 / 0.433402 | 1.0479x | -0.074825 / -0.069877 | 0.085657 / 0.080767 | yes | yes |

Counts: P&L kept 4/5; DD not worse 3/5. Full 5y path (context,
compounded from year-1 start): maxDD 0.100471 -> 0.098859 rule (-0.16pp);
total P&L 2.061253 -> 2.072244 rule (+0.0110 over 5y).

Read: the gate helps where impulses are rare and sharp (2021: 2.7% bars
flagged, DD -1.57pp and P&L +7.1%; 2025: 5.3% flagged, DD -0.49pp and P&L
+4.8%) but fails exactly where it fires most: 2023 (16.8% bars flagged,
the bull-year long leg it throttles earned +0.607 base) cuts P&L to 96.7%
of base and adds +0.07pp of maxDD — the single leg that breaks the P&L
clause. 2024 keeps 98.3% of P&L yet still adds +0.20pp of DD and worsens
the worst week (-0.0453 to -0.0487). Throttling longs through a 7-day
basis collapse buys DD only when the collapse marks real stress; in grind-
up years it mostly taxes the long edge, so the DD leg fails 2/5.

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, definitions, multipliers, or the
   decision rule. PLAN.md was written before `compute_basisbook.py` ran.
2. Vectorised open-to-open screen only (no vol target, governor, dip
   sleeve, funding, SL/TP, or engine limit path); maker cost only
   (0.0002/unit turnover, each path's own chain). Long-leg membership
   fixed by base sign. Impulse uses the pre-built causal feature table
   (delivery closes strictly `< T` via `close_time < T`, same object as
   rebuilding from `data/raw/qbasis_20261003`; raw 1h files not reloaded).
   No threshold was fitted beyond the walk-forward p20 (fixed x0.5, fixed
   7-day window), so LOYO is N/A by construction, but all five years were
   available at scoring time — needs prospective validation.
3. The 2022-23 DD pass is a -0.05pp improvement, not a tie; the 2023-24
   DD fail is +0.07pp worse, outside the 1e-12 tolerance.

## One-line verdict

NOT PROMISING: 7-day basis-collapse long x0.5 keeps >= 97% of book P&L in
4/5 years but cuts maxDD in only 3/5 (2023, the most-flagged year, loses
both: P&L 96.7% of base, DD +0.07pp) — the impulse taxes bull-year longs.
