# oc_phase8 REPORT — 8-clock 30-minute-offset structural screen of R2B1D17BFG2 (2026-10-06)

STRUCTURAL screen, no fitted parameter — post-hoc motivated by oc_phasedisp (labelled so).
8 clocks at 30-minute offsets (0, 0.5, 1, ..., 3.5 h), each a 1/8 sub-account, same G2
configuration as v421 R2B1D17BFG2. Repro: research/diagnostics/oc_phase8/{oc_phase8.py,
results.json, oc_phase8_run_s<XX>.pkl}. Phases ran sequentially (one engine at a time,
2 GB free-RAM gate, per-phase disk cache). All five years are research data; diagnostic only.

## Step 1 — causality verdict: YES, 30-minute shifts are causal with ffill

Shifted 4h bars regroup already-printed 1m minutes (prep_idx: minute m belongs to the bar
starting floor((m − sh)/4h) + sh). At a shifted decision t_s the book uses the last
standard-grid book row r ≤ t_s (0.5 h stale for a 0.5 h shift; r is decided with data up to
r, hence available — no look-ahead). The dip G2 agents have per-integer-shift tables only,
so half-hour clocks ffill the s0 table to the last standard holding bar T_0 ≤ T_s (0.5 h
earlier, walk-forward fitted, hence available). Funding settles per shifted bar
(settle_flags: each 00/08/16 UTC settlement in exactly one bar); the dip ladder runs on the
shifted 1m cube. Book decisions were NOT frozen to hourly phases — both sleeves shift.

## Step 2 — hourly phases reproduced exactly

Metric recomputation from v421_runs.pkl plus a full re-run through this script's worker:
mix 5.41 / worst 2.588 / max yearly DD 16.91 / full-path DD 16.82, per-hourly-phase equities
bit-for-bit identical to cache (max |eq/eq_cached − 1| = 0.0 on all of shifts 0..3).

## Step 3 — per-clock years (R %/month, DD %, all-trade win)

| clock | 2021 | 2022 | 2023 | 2024 | 2025 | 5y mean | worst | maxDD | fullDD | win_all |
|---|---|---|---|---|---|---|---|---|---|---|
| 0h | 4.567, 13.41, .644 | 3.571, 16.91, .662 | 11.249, 14.56, .719 | 10.023, 10.75, .638 | 5.427, 11.88, .622 | 6.923 | 3.571 | 16.91 | 16.91 | .660 |
| 0.5h | 5.584, 15.03, .658 | 2.569, 19.21, .671 | 1.499, 23.58, .694 | 12.250, 9.61, .681 | 5.248, 12.11, .644 | 5.365 | 1.499 | 23.58 | 24.23 | .669 |
| 1h | 2.919, 22.46, .643 | 3.942, 15.67, .657 | 4.226, 18.91, .680 | 9.645, 15.22, .675 | 3.577, 21.21, .644 | 4.834 | 2.919 | 22.46 | 22.46 | .660 |
| 1.5h | 2.914, 13.21, .600 | 3.107, 17.59, .672 | 0.815, 29.47, .658 | 11.715, 12.95, .683 | 4.957, 16.05, .678 | 4.636 | 0.815 | 29.47 | 31.35 | .659 |
| 2h | 2.153, 13.70, .575 | 3.226, 17.39, .655 | 6.412, 20.07, .715 | 11.849, 10.14, .687 | 4.590, 13.69, .616 | 5.592 | 2.153 | 20.07 | 20.07 | .653 |
| 2.5h | 0.690, 20.54, .610 | 0.301, 21.46, .641 | 0.621, 37.12, .698 | 10.204, 15.97, .675 | 4.462, 14.87, .620 | 3.188 | 0.301 | 37.12 | 37.19 | .650 |
| 3h | 0.188, 15.94, .591 | 2.312, 17.99, .655 | −2.431, 43.23, .658 | 11.040, 10.90, .680 | 4.905, 14.21, .624 | 3.102 | −2.431 | 43.23 | 43.55 | .641 |
| 3.5h | 1.335, 16.80, .618 | 3.087, 18.10, .683 | 3.562, 20.29, .699 | 9.795, 14.06, .645 | 2.487, 17.82, .619 | 4.012 | 1.335 | 20.29 | 21.42 | .654 |
| 4-phase mix | 2.588, 10.86, .613 | 3.282, 16.91, .657 | 6.045, 15.81, .696 | 10.677, 8.27, .670 | 4.648, 12.90, .627 | 5.410 | 2.588 | 16.91 | 16.82 | .653 |
| 8-phase mix | 2.709, 11.17, .618 | 2.820, 16.64, .662 | 4.120, 17.98, .693 | 10.861, 10.07, .671 | 4.499, 12.84, .633 | 4.960 | 2.709 | 17.98 | 17.32 | .656 |

Win = (book wins + rung wins)/(book trades + rungs), exit-time bucketed per anchor year
(book episodes use v213 episode logic; rungs use engine ret). Full-period book/rung counts per
clock: 1166–1348 book / 4995–5526 rung trades (agents firing on
every clock, win 0.64–0.67).

## Minimum-notional feasibility per 1/8 sub-account (10 000 USDT → 1 250 per clock)

Order notional = |weight| × 1250 vs Binance minima (BTC 100 / ETH 20 / others 5 USDT).
BTC: 47–60% of orders below 100 USDT on every clock (median BTC order only 77–105 USDT) —
an 8 × 1250 split is NOT placeable as-is (a BTC order needs ≥ 8% sub-account weight).
ETH: 2–8% below 20 USDT. BNB/SOL/XRP: ≤ 3% below minimum (placeable).

## Verdict

VERDICT: NO — the 8-phase mix (5y mean 4.96, full-path DD 17.32, no losing year) dilutes
return by 0.45 pp vs the 4-phase mix and RAISES full-path DD by 0.5 pp (needs ≥ 1 pp lower
at 5.30+ mean). Finer clocks do not diversify away phase luck here: the half-hour clocks
are individually wilder (full-path DD 21–37%) and their crashes land in the same years
(2022–2023), so averaging eight clocks keeps the DD while splitting the capital that earns
the recoveries. The 4-phase hourly mix stands.
