# oc_carrytopup PLAN (pre-registered BEFORE any outcome is computed)

Question (IDEAS3_20261006 idea 2): can the final 7 days before each
BTC/ETH quarterly delivery harvest residual premium with days of lockup
(an EXTRA spot + short pair on top of the frozen base carry), deploying
idle equity exactly when the base sleeve idles? Rule is frozen here; one
allocation row only (f = 0.125 per coin); no variant is tested.

## Rule (fixed, causal, identical machinery to oc_cashcarry)

- Per coin (BTC, ETH), per quarterly contract with delivery D (08:00 UTC
  on the code date for the Binance proxy; instruments-info deliveryTime
  for the Bybit series): candidate entry E = D - 7 days, rounded UP to
  the next spot 4h open_time.
- Actual entry bar T = max(E, first spot 4h bar with BOTH a spot close
  AND a resampled futures 4h close available at its close). Exactly one
  entry opportunity per contract. All information used (F_entry,
  S_entry) comes from 4h closes with close_time <= T close.
- Annualised basis at entry:
  ann_basis = ln(F_entry / S_entry) * 365 / DTE_days,
  DTE_days = (D - close_time(T)) / 86400s.
- ENTER the extra pair iff ann_basis >= 0.04 (4 %/yr, same threshold as
  the base sleeve, no tuning). Else SKIP that contract.
- Position: buy SPOT + SHORT the quarterly in EQUAL notional, each leg
  = f x Eq_entry with f = 0.125 per coin, Eq_entry = 1.0 indexed unit
  (returns scale linearly). Hold to delivery D. No early exit, no stop.
- Settlement = delivery index, modelled as the SPOT 4h CLOSE of the
  spot bar containing D (first spot bar with open_time <= D <
  close_time; its close). If D is beyond the last spot bar, the trade is
  INCOMPLETE and excluded (counted separately, no P&L imputed).
- Fees (same as base): spot 0.001 per side (buy at entry, sell at
  delivery), futures 0.00055 entry short + 0.0002 delivery settlement.
  Fee drag per pair = 0.00275 of allocated. No funding leg (delivery
  futures pay none; the AGENTS.md perp-funding rule is irrelevant here).
- Per-trade net P&L (per Eq_entry = 1):
  P&L = f * [ (S_del - S_entry)/S_entry + (F_entry - S_del)/F_entry
  - 0.00275 ]; ret_alloc = P&L / f (independent of f).
- Worst MtM (basis widening, information only): at each 4h close t in
  (T, D]: mtm_alloc(t) = (S(t)/S_entry - 1) +
  ((F_entry - F(t))/F_entry) - 0.00155 (entry fees paid).

## Two series (fixed)

- binance: `data/raw/qbasis_20261003/um_BTCUSDT_*_1h.parquet` +
  `um_ETHUSDT_*_1h.parquet` (Binance USDT-margined quarterly delivery,
  `cm_*` unused) resampled to 4h exactly as in
  `oc_cashcarry/analyze_cashcarry.py` (last 1h close with 1h open_time <
  spot bar close_time); spot `data/raw/spot_majors_20260925/*_spot_4h.parquet`.
  Delivery D parsed from the code (`um_<COIN>_<YYMMDD>` -> 20YY-MM-DD
  08:00 UTC, matches every manifest last_open_time).
- bybit_inv: `data/raw/bybit_quarterly_20261006/inv_BTCUSD*_1h.parquet` +
  `inv_ETHUSD*_1h.parquet` (Bybit coin-margined inverse quarterlies, the
  only Bybit chain covering all five anchor years) + Bybit spot
  `spot_BTCUSDT_1h.parquet` / `spot_ETHUSDT_1h.parquet`, resampled to the
  00/04/... UTC 4h grid exactly as in
  `research/data_fetch/bybitq/analyze_bybit_carry.py` (a 4h bar is valid
  only if all 4 hours are present; F(t) = last futures 4h close with
  fut close_time <= spot close_time). Delivery = instruments-info
  deliveryTime from `research/data_fetch/bybitq/inventory.json`.
  Coin-settlement convexity is NOT modelled (same approximation as the
  bybitq recompute: ln(F/S) basis + price-return P&L unchanged).
- No 1m data is loaded. No re-download. One process, 4h data only,
  peak RAM < 2 GB.

## Per anchor year reporting (fixed)

- Anchors A = 2021..2025-09-24, year Y = [A, A + 365d), grouped by
  ENTRY bar open_time. Incomplete trades listed but excluded.
- Per venue, per year, per coin and total: n_entered, n_skipped,
  mean ann_basis, mean DTE, mean ret_alloc, sum ret_alloc,
  worst MtM (alloc).
- Contribution to the ACCOUNT at f = 0.125:
  contrib(f) = 0.125 * (sum of ret_alloc over trades entered in Y),
  as total % over the year and %/month = total/12 (indexed equity,
  ignores intra-year compounding; linear in f). 5-year pooled total +
  geometric-mean %/month (compound yearly factors
  (1 + 0.125*year_sum) over 5 years).

## Margin / cash check (fixed)

Stacked on the frozen BASE sleeve at f = 0.25 per coin (Binance base =
`oc_cashcarry/results.json` 33 trades; Bybit base =
`research/data_fetch/bybitq/results_bybit_carry.json` inverse series;
both reused verbatim: entry_open, delivery, no recompute of base P&L):

- On the venue's own spot 4h grid, at each bar t in
  2021-09-24..2026-09-23: B(t) = # base pairs open
  (base entry_close <= t < base delivery), U(t) = # top-up pairs open.
  Combined indexed spot cost C_idx(t) = 0.25*B(t) + 0.125*U(t)
  (spot legs are bought with USDT cash; Eq_entry = 1 indexed).
  Report max C_idx, its bar, and max B/U overlap per venue.
- Live-scaled check: C_live(t) = C_idx(t) / Eq_mix(t), Eq_mix(t) =
  mean `oc_kpi_g2/barsum_s{0..3}` equity at the last bar <= t
  (ffill; same indexed units as the oc_cashcarry margin check). Check
  at the max-C_idx bar AND at the oc_utamargin worst hour's containing
  4h bar (2025-09-25 18:00 UTC). If barsum files are missing, state
  analytic-only (C_idx vs 1.0), never a silent fallback.
- BORROW_NEEDED iff max C_idx > 1.0 OR C_live > 1.0 at either checked
  bar (spot cost exceeds the account -> USDT must be borrowed;
  interest unmodelled). The oc_utamargin reference (base f = 0.25 alone
  peaks at 95.8% spot-cost/Eq, headroom +4.2%) is cited for context.

## Verdict rule (fixed, from the assignment)

USEFUL iff (a) yearly sum_ret_alloc > 0 after fees in >= 4 of the 5
anchor years on EACH venue (Binance proxy AND Bybit inverse), AND (b)
no borrow is needed on either venue stack (max C_idx <= 1.0 and both
C_live checks <= 1.0). Else CLOSE (direction closed, no follow-up
sizing/threshold work). Report expected %/month added (at f = 0.125)
and any DD impact regardless.

## Leakage / scope notes (fixed)

- Entry uses only 4h closes <= entry close; settlement uses the
  delivery-bar spot close; truncate-before-entry leaves F_entry/S_entry
  unchanged; fee math hand-checked; results.json <-> REPORT.md
  consistency; script never references 1m/intraday paths.
- This is a tournament structural sleeve reusing the frozen base (not
  a vf feature module with compute()/events()); common.event_study is
  N/A. All five anchor years are research data (oc_cashcarry
  precedent: market data up to 2026-09-23 may be read); findings need
  the same prospective paper check as everything else (live venue is
  Bybit; delivery/settlement mechanics must be confirmed there).
- GIT IS READ-ONLY (OPENCODE_VF_COMMON.md 2026-10-06 rule): no
  stash/reset/checkout/clean/commit. Writes ONLY to
  `research/tournament/oc_carrytopup/` + `tests/test_oc_carrytopup.py`.

## Deliverables (fixed)

- `research/tournament/oc_carrytopup/`: THIS PLAN.md (written first),
  `analyze_carrytopup.py`, `results.json`, `REPORT.md` (per-year table
  per venue + stacked cash table + one-line verdict).
- `tests/test_oc_carrytopup.py`: threshold respected; fee math
  hand-check; entry causal spot-check (truncate-before-entry);
  settlement = delivery-bar spot close; year sums match trades;
  no-1m in script source; results.json <-> REPORT.md consistency
  (verdict string + key numbers present).

(End of PLAN — frozen before outcomes.)

## Post-hoc amendment log (2026-10-06, before REPORT/test writing)

1. Live-scaled cash formula corrected: PLAN first wrote
   C_live(t) = C_idx(t) / Eq_mix(t). That double-deflates once BOT
   equity has compounded (indexed cost is in start-units; dividing by
   ~14x equity late-sample fakes headroom). Correct convention is the
   oc_carrycombo/oc_utamargin one: legs are sized f x mix equity at
   each pair's ENTRY hour, so
   C_live(t) = sum_open f*Eq_mix(entry_k)/Eq_mix(t).
   Borrow rule unchanged (max C_idx > 1.0 OR max C_live > 1.0).
   The verdict inputs (0/5 positive years, indexed max 1.125 > 1.0)
   already forced CLOSE before this fix; the fix only makes the live
   leg honest. No threshold, window, fee, or verdict-rule change.
