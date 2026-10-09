# oc_vrprobust PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: is the G2 + weekly short-straddle overlay real? oc_vrpstraddle V2
(weekly naked ATM straddle BTC+ETH, sold Fri 08:05 UTC at 0.97 x DVOL) as an
overlay on G2 at f=0.25 gave 5y 6.41 %/mo, worst 4.37, DD 16.01 (G2: 5.41 /
2.59 / 16.82). Main doubt: PRICING (DVOL = 30d ATM index vs 7d straddle IV;
fills were BS mids, no bid/ask). This is a robustness study of the SAME rule;
no new variants of the rule itself. Code is COPIED from
research/tournament/oc_vrpstraddle/{vrp,run_vrp}.py into this folder
(vrprobust.py + run_robust.py); the original is never edited.

## Frozen base rule (V2 copy, identical unless a section overrides it)

- Fri 08:05 UTC entry, S = 1m close of 08:04, K = S rounded NEAREST to grid
  (BTC 1000, ETH 50); expiry next Fri 08:00; T_entry = (7d-5min)/365.
- sigma_sell = k x latest-known-DVOL/100 (k = SELL_MULT, default 0.97).
  Premium = BS call+put (r=q=0) at sigma_sell, T_entry.
- Fees (base): per leg per side min(0.0003 x S_trade, 0.125 x leg_price);
  settlement per ITM leg min(0.00015 x S_settle, 0.125 x intrinsic).
- Size: q = 0.5 x f x E / S per coin (f=1 standalone; f of TOTAL equity overlay).
- SL: hourly closes, P&L(t) = -q x mark(1.05 x DVOL) + opt_cash <= -1.0 x gross
  premium -> buy back at BS(1.05 x DVOL) + fees (no hedge in V2, so no hedge leg).
  TP: 4h closes (checked FIRST), mark(DVOL) <= 0.3 x gross -> buy back + fees.
  Else settle vs mean of 30 1m closes 07:30..07:59 + settlement fees.
- Overlay: UTA combo A(t) = A(t-1)(1+r_bot(t)) + dSleeve(t), r_bot from stored
  4-phase G2 hourly mix (v421_runs.pkl via v388.hourly); reset metric per
  research/diagnostics/r2_decompose5/reset_metric.py; boundary weeks skipped.
- Gate costs: maker 0.0002 / taker 0.00055; funding N/A (V2 unhedged, no hedge).

## A. Pricing break-even (dev4 selection; recent year once for the same rows)

- k in {0.97 (reproduce EXACTLY first), 0.92, 0.88, 0.85, 0.80}; marks unchanged
  (SL buyback 1.05 x DVOL, TP/mark 1.0 x DVOL). Per k: V2 standalone dev4
  (R/DD/trades/win) + G2 overlay f=0.25 dev4 (yearly R/DD, dev4-mean R, worst,
  maxDD) + full-path DD of the overlay.
- ASSERT k=0.97 reproduces oc_vrpstraddle dev4 standalone V2 yearly R/DD and
  the G2+0.25 overlay yearly R/DD to the digit; else stop and report.
- k*_gain = linear interpolation (descriptive) of overlay dev4-mean gain over
  G2 vs k to gain = 0; also report the discrete bracket (last k with gain > 0,
  first k with gain <= 0). k*_DD = first k (descending) where overlay max yearly
  DD exceeds G2's 16.91. k* (verdict) = k*_gain.
- Recent year 2025-09-24..2026-09-23 scored ONCE for all 5 k rows (standalone +
  overlay f=0.25) + G2 reference. Descriptive only, no selection.

## B. Term structure from traded prices (read-only; preliminary)

- Month files present at start (full-calendar-month hour coverage verified
  2026-10-07; manifests attest only a subset - disclosed as fetch-ongoing):
  BTC: 2021-01,02,03,04,05,06,07, 2023-03, 2025-06 (9 files);
  ETH: 2021-01..09, 2023-03, 2025-06 (11 files).
  No other months are used even if the download finishes mid-task.
- Per coin, per Friday F whose date lies in those months: rows with
  hour in {08,09,10,11} UTC of F, expiry.date() == (F+7d).date(),
  |strike/vwap_index - 1| <= 0.02, cp in {C,P}, sum_amount > 0.
  IV_7d_ATM = sum(vwap_iv x sum_amount)/sum(sum_amount) (vol points);
  Friday skipped if no rows (logged).
- DVOL_0800 = latest known hourly DVOL candle close <= F 08:00 UTC (same
  dvol_known helper as the pricer). r = IV_7d_ATM / DVOL_0800.
- Report per coin per month + pooled over all Fridays: n, mean, median, p10,
  p90 of r; share of Fridays with r < k*_gain (extra: vs k*_DD).
- Taker-side proxy: SELL = rows with taker_sell_amount > taker_buy_amount,
  BUY = rows with taker_buy_amount > taker_sell_amount (ties excluded),
  amount-weighted IV (weights sum_amount) per subset per Friday; report pooled
  mean/median of IV_buy - IV_sell (labelled per assignment: approximates the
  half spread in vol points; note it reads as the full effective spread, so
  half ~= diff/2 - both stated).

## C. Execution realism rows (overlay f=0.25, k=0.97, dev4; labelled)

- C1 Bybit fees: per leg per side min(0.0003 x S_trade, 0.07 x leg_price);
  settlement per ITM leg min(0.0003 x S_settle, 0.07 x intrinsic).
  Re-run standalone + overlay dev4.
- C2 SL at 15-min closes (:00/:15/:30/:45, price = 1m close of that minute,
  sigma = latest DVOL candle close <= check time), marks at 1.05 x DVOL;
  TP unchanged (4h closes, checked first on coincidence). Standalone + overlay.
- C3 1m-marked combined DD: (i) G2 top-20 DD minutes = 20 hourly steps with
  largest (peak - M)/peak on the G2 continuous full-path marked path;
  (ii) sleeve worst 10 hours = 10 hourly steps with most negative sleeve-only
  hourly dU in the dev4 continuous standalone path (k=0.97). At those 30 steps
  mark each open straddle on the 1m close (same sigma rule, same T rule);
  combined M_1m = A_prev x hh + dU_1m; report max dip vs running hourly peak
  as 1m-marked yearly/full-path DD. Gate DD = max(close, hourly-marked,
  1m-marked). G2 leg stays hourly-marked (labelled partial/lower bound).
- C4 Gap stress at THE worst minute = hourly step with most negative combined
  hourly return in the dev4 yearly-reset overlay (f=0.25, k=0.97); logged with
  date. G2 exposure by the oc_gapstress method (build_state, dip scaled to
  gross cap 2.0 per phase then equity-weighted mix): signed S, gross G.
  Straddles open at that step shocked to BS(S(1+g),K,T,1.5 x DVOL) with DVOL
  as of that time. g in {-10%,-15%,+10%,+15%} all-coin simultaneous. Report
  loss % of combined equity for overlay vs G2 alone on the same base.
  Pass bar: overlay loss <= G2 loss + 3 pp.

## D. Sizing and MANUAL (labelled; chosen on dev4 only)

- D1: f in {0.10, 0.25, 0.50} (k=0.97) on (i) G2 and (ii) G2+carry f=0.25.
  G2+carry base is built EXACTLY as research/tournament/oc_carrycompound/
  analyze_carrycompound.py does (account-realistic UTA, carry notional
  f x A at entry, same trades/fees/mtm); its f=0.25 rows must reproduce
  oc_carrycompound results.json yearly R/DD to the digit (assert; else stop).
  Robust criterion per base on dev4; pick best f per base; recent year ONCE
  for the 2 picks + 2 references (G2, G2+carry f=0.25).
- D2 MANUAL: M5_human hourly equity from
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl via v388.hourly
  (same loader as oc_putwrite/run_overlay.py). Overlay f in {0.25, 0.50}
  (k=0.97) dev4: does any row reach the MANUAL floor (>= 5 %/mo, DD < 20, no
  losing year)? Recent year ONCE for the best MANUAL row + MANUAL reference.
- Bybit executability (evidence 2026-10-07): instruments-info page 1 shows
  weekly Friday USDT-margined BTC expiries (16/23/30OCT26, 06NOV26) + monthlies/
  quarterlies, deliveryFeeRate 0.00015; place-order docs: category=option
  supports Limit/Market + full-size market TP/SL attached at order placement
  (takeProfit/stopLoss params) and conditional orders via triggerPrice.
  Human procedure stated in REPORT from this (no authenticated calls made).

## Selection, leakage, outputs

- Selection ONLY on dev4 (anchors 2021/22/23/24-09-24, [A,A+365d)); robust
  criterion (W_COMMON). Recent-year rows are labelled once-only descriptives.
- Leakage checks (stated in REPORT): DVOL candle known at close; S at 08:04
  known at 08:05; 15-min SL uses 1m closes at/after the check minute only;
  marks use latest closed hourly DVOL; settlement 07:30..07:59 known at 08:00;
  labels use post-entry minutes only; no fits/thresholds; strike-IV data (B)
  is descriptive and never enters pricing; gap shocks are post-hoc overlays.
- Outputs: research/tournament/oc_vrprobust/{PLAN.md, vrprobust.py,
  run_robust.py, carry_base.py, results.json, REPORT.md, tmp/},
  tests/test_oc_vrprobust.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic BS/fee case; pytest -q). Stop when done.
