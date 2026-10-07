# oc_idea4_carrymax REPORT — Max-basis single-coin carry (IDEAS_20261007 §4)

## 0. PRE-REGISTRATION (frozen BEFORE any run; no other variants)

- M1 max-coin only: per quarterly delivery, among the frozen oc_cashcarry
  entered trades (entry-bar annualised basis >= 4 %/yr, causal entry closes),
  keep ONLY the coin with the HIGHER entry ann_basis; tie-break BTC (no ties
  occur in the 33). f = 0.25 of LIVE account equity at each entry, hold to
  delivery. All else identical to oc_carrycompound (fees spot 0.001/side +
  fut 0.00055 entry / 0.0002 delivery; causal hourly marks; compounding
  account A(t) = A(t-1)*(1+r_bot) + dU; per-year reset to 1.0; spanning
  rebased at each anchor).
- M2 max-coin with 4.5 % re-entry floor (no churn): M1 + require the chosen
  max-coin entry basis >= 4.5 %/yr, else enter NOTHING for that delivery
  (strict subset of M1; same f = 0.25, same mechanics).
- Selection ONLY on dev anchors 2021-2024 (robust criterion: DD <= 20 and no
  losing dev year; prefer dev4 mean >= 5 %/mo, then the highest dev4 WORST
  year; ties -> higher mean). The most recent year 2025-09-24..2026-09-23 is
  scored ONCE, for the chosen variant only, and labelled POST-HOC everywhere
  it appears (all five years were already seen by the baseline builds).
- Gate costs: maker 0.02 %, taker 0.055 %; longs pay 0.01 %/8h. The carry leg
  uses delivery quarterlies (NO funding by construction) with the
  oc_cashcarry fee drag 0.275 %/alloc already inside ret_alloc; the BOT leg
  (G2 4-phase) already carries gate costs from the engine. No extra slippage.
- Repro gate: f = 0 must reproduce v421_result G2 (5.410 / W 2.588 /
  DD 16.91 / full 16.82) TO THE DIGIT, and FULL33 f = 0.25 must reproduce
  oc_carrycompound (5.634 / W 2.778 / DD 16.75 / full 16.66) TO THE DIGIT,
  else STOP and report. Metric = reset_metric.year_reset per anchor year +
  v421 continuous full-path DD. Book ideas judged in the 4-phase engine
  (here: the stored 4-phase G2 path, no vectorised screen).

## 1. Method (reuses audited blocks unchanged)

- Closest closed: oc_cashcarry (both BTC+ETH whenever each passes 4 %) and
  oc_carrymore (multi-coin, PARKED: needs borrow). New here: ONE coin per
  delivery (the higher locked basis) at f = 0.25, freeing the other coin's
  spot cash.
- Data (local, same as idea #3): data/raw/qbasis_20261003 (um quarterlies 1h)
  + data/raw/bybit_quarterly_20261006 (Bybit inverse inventory, venue check)
  + data/raw/spot_majors_20260925 (spot 4h) + research/tournament/ext/
  hourly_ext.parquet (hourly marks) + v421_runs.pkl strat R2B1D17BFG2.
  No new data, no fitting, no engine rerun; 4h+1h only, one process.
- Causality / leak check: coin picked SOLELY on entry-bar ann_basis
  (ln(F/S)*365/DTE from <= entry closes, frozen oc_cashcarry rule); no
  delivery-time or future info enters the choice; MtM marks use the last
  CLOSED hourly bar strictly before t (searchsorted left-1); settlement from
  frozen ret_alloc. Fewer fills than baseline (M1 18 vs 33 total, 14 vs 25
  in-window; M2 16/12) so CIs are wider — stated, not hidden.

## 2. Results (frozen run 2026-10-07; 2025 rows are POST-HOC)

Validation gates PASSED, else this section would not exist: f = 0 reproduces
v421_result G2 (5.410 / W 2.588 / DD 16.91 / full 16.82) TO THE DIGIT, and
FULL33 f = 0.25 reproduces oc_carrycompound (5.634 / W 2.778 / DD 16.75 /
full 16.66) TO THE DIGIT (asserted in-script; see results.json
baseline_G2_f0 / baseline_FULL33_f025).

Dev-only selection (anchors 2021-2024, f = 0.25, reset_metric.year_reset):

| variant | dev4 %/mo | worst dev yr | max dev DD | losing |
|---|---|---|---|---|
| M1 max-coin | 5.744 | 2.682 (2021) | 16.75 | 0 |
| M2 + 4.5 % floor | 5.739 | 2.682 (2021) | 16.75 | 0 |
| ref: both-coins FULL33 (frozen) | 5.870 | 2.778 (2021) | 16.75 | 0 |

Both pass DD <= 20 with no losing dev year and dev4 mean >= 5; robust
criterion picks M1 (same worst year, higher mean: 5.744 > 5.739). The 4.5 %
floor changes almost nothing (it drops only 2 low-basis picks: BTC
2023-12-29 at 4.3875 % and BTC 2026-03-27 at 4.2188 %).

Chosen M1, full picture (2025 scored ONCE, POST-HOC; full-path DD v421
convention, carry leg close-marked = lower bound):

| year | M1 R %/mo / DD % | FULL33 ref R / DD |
|---|---|---|
| 2021-09-24 | 2.682 / 10.86 | 2.778 / 10.86 |
| 2022-09-24 | 3.332 / 16.75 | 3.353 / 16.75 |
| 2023-09-24 | 6.337 / 15.71 | 6.590 / 15.69 |
| 2024-09-24 | 10.819 / 8.23 | 10.956 / 8.20 |
| 2025-09-24 POST-HOC | 4.682 / 12.76 | 4.698 / 12.66 |
| 5y mean / worst / maxDD / losing | 5.531 / 2.682 / 16.75 / 0 | 5.634 / 2.778 / 16.75 / 0 |
| full-path DD marked/close/full | 16.66 / 15.90 / 16.66 | 16.66 / 15.90 / 16.66 |

M1 keeps 18 of 33 trades (14 vs 25 in-window; M2 16/12) and
loses -0.126 pp/mo on dev and -0.103 pp/mo on 5y vs both-coins, with a worse
worst year (2.682 vs 2.778) and identical DD. The idea's expected
+0.02-0.06 pp/mo (higher locked rate + freed spot cash) did NOT appear:
every dropped second coin was itself net positive (min +0.18 %/alloc locked),
so concentration destroys more yield than it saves. M2 ~= M1 throughout.

## 3. Margin / UTA bound (analytic, entry-equity units)

M1/M2 trades are a strict subset of the audited 33, so carry notionals are
weakly below the baselines that already showed 0 blocked closes
(oc_cashcarry margin table; oc_carrymore BTC+ETH peak-4 note). Actuals at
f = 0.25: peak 2 concurrent pairs (roll overlap only), peak spot cash 0.50x
equity, peak carry gross 1.0x — fundable from idle cash, NO borrow (both-
coins needed 1.0x spot / 2.0x gross at peak 4). Shorts need IM at 5x on
their mark; pairs are delta-hedged so gap loss is only basis widening
(worst alloc MtM among kept trades -2.65 % in 2023 = -0.66 % account).
Capital efficiency is the one real gain; it does not pay for the lost yield.

## 4. Verdict: REJECT as a return improvement

Max-coin carry is cheaper on capital (0.5x vs 1.0x peak spot) but earns less
(-0.10 pp/mo 5y, -0.13 pp/mo dev, worse worst year, same DD): the freed cash
earns nothing extra in the compounding account while each dropped coin took
a locked positive yield with it. M2's 4.5 % floor adds nothing. Close the
direction; keep both-coins f = 0.25 as the frozen carry baseline.

## Ket luan tieng Viet (3 dong) — REJECT

- Max-coin (M1) thua ca 2 coin goc: dev -0,13 diem %/thang, 5 nam -0,10 diem %/thang, nam te nhat cung te hon (2,68 so voi 2,78).
- Duoc duy nhat von nhe hon (peak spot 0,5x thay vi 1,0x, khong can vay) nhung DD khong doi (16,75/16,66) nen khong bu duoc phan loi mat.
- Khong adopt, khong can paper them cho huong nay; giu nguyen baseline both-coins f=0,25.
