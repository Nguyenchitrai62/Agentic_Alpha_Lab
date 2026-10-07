# oc_ethbtc — REPORT: ETH/BTC trend and BTC-dominance regimes

Regimes from 4h opens only (`opens_v154`): `ethbtc30/90` = 30/90 d log
change of ETH/BTC; `dom30` = BTC 30 d log return minus equal-weight
majors 30 d return. Terciles use previous-years cut-offs (dip: prior
MAIN-fill quantiles; book: prior grid-bar quantiles). Anchor years
`[A, A+365d)`, A = 2021-09-24 .. 2025-09-24. Full numbers: results.json.

## (a) Dip rung mean y1.0 of the majors by regime tercile (hi-lo, bps/fill)

| var | 21-22 | 22-23 | 23-24 | 24-25 | 25-26 | sign | LOO holds |
|---|---|---|---|---|---|---|---|
| ethbtc30 | +42.4 | -24.2 | +4.6 | +5.8 | +48.0 | 4/5 + | 1/5 |
| ethbtc90 | -108.1 | +94.2 | -42.6 | +8.9 | -21.6 | 3/5 | 2/5 |
| dom30 | NaN (lo empty) | +21.6 | -7.8 | -36.1 | -23.0 | 3/5 | 4/5 |

Dip verdict: NOTHING PROMISING. ethbtc30 meets sign 4/5 but LOO 1/5
(the 2022 flip kills it); dom30 meets LOO 4/5 but sign only 3/5 with a
degenerate 2021 (no fills below the pre-history cut). Round-trip cost
context ~4-8 bps: several yearly spreads exceed cost but they do not
persist.

## (b) Book gross P&L by regime tercile (hi-lo mean, bps/bar, 6 bars/day)

| var | 21-22 | 22-23 | 23-24 | 24-25 | 25-26 | sign | LOO holds |
|---|---|---|---|---|---|---|---|
| ethbtc30 | -2.27 | -0.08 | -1.64 | -0.44 | +2.18 | 4/5 - | 1/5 |
| ethbtc90 | -2.38 | -1.57 | -3.93 | -1.84 | +5.79 | 4/5 - | 0/5 |
| dom30 | +0.02 | +2.76 | +10.78 | +1.14 | +1.49 | 5/5 + | 4/5 PROMISING |

Book verdict: dom30 is PROMISING by the pre-registered rule (5/5 same
sign, LOO 4/5: held-out hi-lo +1.77/+0.73/+4.63/+2.34 bps/bar for
2021-2024, FAILS 2025 at -0.62). Direction: the book earns more per bar
when BTC dominates the majors than when alts dominate. ethbtc30/90 fail
LOO (1/5, 0/5 — the 2025 sign flip breaks both).

## Verdict (one line)

**Book dom30 PROMISING but fragile (5/5 signs rest on a +0.02 bps/bar
2021, and the single LOO failure is the most recent year 2025); both
ETH/BTC trends and all dip-rung splits are NOT PROMISING — no dip gate,
and at most a weak BTC-dominance tilt for the book, pending prospective
validation.**

## Caveats / post-hoc log

1. Bug fix after first run (code did not match PLAN): book
   previous-years cut-offs were quantiled on the books-grid history
   (empty for 2021 -> NaN cuts) instead of the full opens history from
   2017 as PLAN requires. Fixed to `reg_full`; 2021 book rows now use
   7429 prior bars. Outcome inspected before the fix beyond the NaN
   plus this log entry.
2. The dom30 PROMISING flag is borderline by construction: 2021 hi-lo is
   +0.022 bps/bar (positive but economically zero) and the LOO miss is
   exactly the most recent year — treat as hypothesis-generating, and
   any tilt rule must be judged walk-forward on pre-anchor data only.
3. Gross vectorised book P&L only (no spread/fees/funding, no vol
   target/governor/SL/TP/sleeve/compounding); per-bar means are not
   directly comparable to 4-8 bps round-trip costs. Dip fills: MAIN only
   (5 majors x R2 depths, n=6876, T 2020-08-25..2026-09-23, 0 dropped).
4. Causality: truncate-and-recompute + future-spike tests pass
   (tests/test_oc_ethbtc.py); every fill's grid_t <= T; cut-offs use
   only fills/bars strictly before each anchor.
