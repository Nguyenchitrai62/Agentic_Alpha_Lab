# OpenCode task oc_stablegate - stablecoin net-creation impulse as a book-long gate (engine) and a dip-budget dial (replica)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_stablegate/` and `tests/test_oc_stablegate.py`.
Spec source: docs/opencode/IDEAS_20261007c.md ideas B3 and B7 (read them). Stablecoins were tried before only as model FEATURES
(research-map "Tried and rejected": on-chain) and the USDT PRICE premium was tried as a tilt (oc_usdtprem, engine NO); the SUPPLY impulse as a
gate / budget dial is untested.

## Data and signal (fixed)
- `data/raw/onchain_20260924/stablecoins.csv` (asset, time = UTC day, CapMrktCurUSD; CoinMetrics daily caps). Use usdt + usdc summed.
  A day's cap is known only after that day ends: value of day D is usable from D+1 00:00 UTC (+ a 4h safety lag -> from D+1 04:00 UTC).
- impulse(D) = log(cap(D) / cap(D-30)); z(D) = (impulse(D) - mean) / std over the trailing 730 days of impulse ending at D (min 365).
- Check the data range covers 2021-09-24 .. 2026-09-23; if the file ends earlier, state the uncovered span and use multiplier 1 there
  (no fetching new data in this task).

## Leg 1 - book gate (4-phase engine, heavy_slot)
Copy the book-multiplier mechanism of research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py (multiplier on STANDARD book rows
(T, sym) whose bear-filtered weight is > 0, applied after the bear-book filter and before the shifted-clock forward fill) on top of G2
(`R2B1D17BFG2`, v421 RUNS: rule inv, k 1.0, kd 1.7, bear True, G 2.0). Reproduce G2 exactly first (5.41 / 16.91 / 16.82), else stop.
- G1: book LONG weights x0.75 when z < -1.0 (latest z known at T), else x1. Shorts unchanged.
- G2S: book LONG weights x0.75 when z < -1.5; x1.0 otherwise (asymmetric, fewer events).
- CTRL: exposure-matched control = a constant long multiplier equal to G1's realised mean multiplier per year on every long row.
Report per dev year: 4-phase reset metric, yearly DD, full-path DD, share of book rows gated, and G1 vs CTRL.

## Leg 2 - dip budget dial (dip replica, no engine)
Use the replica of research/tournament/oc_placebo_dip/compute_placebo_dip.py (copy into your folder; reproduce base 5y sum 7.718 first).
- D1: every rung weight x(0.32/0.26) when z > +1.0 at the bar open, x(0.20/0.26) when z < -1.0, else x1.
- D2: upside only: x(0.32/0.26) when z > +1.0, else x1.
Judge with the established dip gate (PROMISING = sum >= base in >= 4/5 years AND DD <= base + 0.01 in >= 4/5 AND 5y sum delta >= +0.273;
calibrated on all five years - label it) and the dev4-only view.

## Verdict
A leg is a candidate only if: (engine) G1 or G2S beats G2 on dev4 mean with no worse worst year and DD <= G2 + 0.3 pp AND beats CTRL; (dip)
PROMISING. Score the most recent year once only for a candidate. Otherwise reject.
