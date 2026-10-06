# oc_calendar PLAN (pre-registered BEFORE any outcome is computed)

Question (IDEAS3_20261006 idea 4): does a near-vs-far quarterly roll-down
spread (long near quarterly / short far quarterly, adjacent contracts, no
spot leg, no funding) add an independent convergence yield on top of the
oc_cashcarry base carry sleeve?

## Fixed rule (frozen here, single threshold, no tuning, no variants)

- At each oc_cashcarry roll date, per coin, let near = the next quarterly
  contract C_k and far = the one after C_{k+1} (adjacent quarterlies).
  Compute annualised bases ann_near, ann_far from 4h closes available at or
  before the entry bar close (strictly causal, definitions below).
- ENTER the spread iff ann_far - ann_near >= 0.02 (2 pp/yr, fixed).
  Else SKIP that pair (no position). The threshold, the roll dates and the
  hold-to-near-delivery are frozen here; no variant is tested.
- Position per ENTERED pair: LONG near + SHORT far in EQUAL USD notional,
  each leg = f x Eq_entry with f = 0.125 per coin per pair and Eq_entry = 1.0
  indexed unit (returns scale linearly; ret_alloc = P&L / f is independent
  of f). If BTC and ETH spreads are both open, total spread gross is up to
  4f. Overlapping pairs (consecutive near contracts overlap ~7 days by
  construction: T_{k+1} falls ~7d before D_k) are sized ADDITIVELY and never
  netted ex post.
- Hold to the NEAR delivery D_near. No early exit, no stop (the spread is
  delivery-anchored; MtM is tracked for information only). At D_near the
  near leg settles via delivery and the far leg is closed at market (taker)
  in the same hour (same delivery bar, definition below).
- Fees (assignment-fixed): taker 0.00055 per leg per side on every market
  fill, delivery settlement 0.0002. Per pair: entry 2 x 0.00055 (both legs
  taker) + exit 0.0002 (near delivery) + 0.00055 (far taker close).
  Fee drag per allocated unit = 0.00055 x 3 + 0.0002 = 0.00185.
  No funding leg (quarterly delivery futures pay no funding; there is no
  spot or perp leg).
- Per-trade net P&L (per Eq_entry = 1, per allocated unit):
  gross = (S_del - N_entry) / N_entry + (F_entry - F_far_del) / F_entry,
  ret_alloc = gross - 0.00185,
  where N_entry / F_entry = near / far futures 4h closes at the entry bar,
  S_del = settlement spot 4h close of the near-delivery bar,
  F_far_del = far contract resampled 4h close at the same near-delivery bar.

## Venues / data (fixed, read-only, 4h only, one process, RAM < 2 GB)

Two series, same rule, reported side by side:

- BINANCE proxy: quarterly delivery 4h closes from
  `data/raw/qbasis_20261003/um_BTCUSDT_*_1h.parquet` and
  `um_ETHUSDT_*_1h.parquet` (Binance USDT-margined quarterly delivery
  contracts; `cm_*` coin-margined files are NOT used). Resampled to 4h by
  taking, for each spot 4h bar, the last 1h close with 1h open_time < spot
  bar close_time (strictly causal; identical to oc_cashcarry). Spot majors
  4h: `data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet` and
  `ETHUSDT_spot_4h.parquet` (Binance SPOT 4h; open_time-indexed).
  Delivery D is exact and known from the code at entry: 08:00 UTC on the
  code date (matches every manifest `last_open_time`).
- BYBIT inverse: quarterly 1h closes from
  `data/raw/bybit_quarterly_20261006/inv_BTCUSD*_1h.parquet` and
  `inv_ETHUSD*_1h.parquet` (Bybit-native coin-margined quarterly H/M/U/Z
  chain; `lin_*` weekly/USDT-dated files are NOT used). Spot Bybit hourly
  `spot_BTCUSDT_1h.parquet` / `spot_ETHUSDT_1h.parquet` resampled to 4h on
  the 00/04/08/12/16/20 UTC grid (close = hourly close of hour 4k+3; a 4h
  bar is valid only if all 4 hours are present), then F(t) = last futures
  4h close with fut close_time <= spot close_time (causal; identical to
  `research/data_fetch/bybitq/analyze_bybit_carry.py`). Delivery D is the
  exact ms `deliveryTime` from `research/data_fetch/bybitq/inventory.json`
  (venue-supplied, not parsed codes).
- Coins: BTC + ETH only on both venues (the only majors with quarterly
  chains in both datasets). No 1m data is loaded. No re-download. Market
  data up to 2026-09-23 may be read (all five anchor years are research
  data; findings need prospective validation like everything else).
- Inverse note (same approximation as the Bybit carry recompute):
  coin-margined inverse prices are in USD at the same scale as USDT spot,
  so the ln(F/S) basis and the price-return P&L formula apply unchanged;
  coin-settlement convexity is noted, not modelled (second order next to
  the fee drag and the spread).

## Roll / entry (fixed, causal, mirrors oc_cashcarry)

- Per coin per venue, sort expiries ascending: C_0..C_{N-1} with deliveries
  D_0..D_{N-1}.
- For near index k (0 <= k <= N-2, a far contract k+1 must exist):
  candidate entry E_k = round_UP(delivery(k-1) - 7 days) to the next spot
  4h open_time for k >= 1 ("enter the next-quarter pair when the current
  near has <= 7 days left"); for k = 0, E_k = first availability.
- Actual entry bar T_k = the oc_cashcarry roll bar for the NEAR contract k:
  E_k as above, then the first spot 4h bar >= E_k with a spot close AND a
  resampled NEAR-4h close available at its close (near + spot only, exactly
  the oc_cashcarry T_k for contract k). The FAR leg is evaluated at that
  same bar: if no resampled far-4h close is available at T_k close, the pair
  is NO_FAR_AT_ROLL (counted separately, no P&L imputed, no slipped entry).
  Rationale: the assignment says "at each oc_cashcarry roll date" — the
  entry date is fixed by the near contract's roll, not moved to suit far
  availability. Exactly one entry opportunity per (near, far) pair.
- All information used (N_entry, F_entry, S_entry) comes from 4h closes
  with close_time <= T_k close. Annualised bases at entry:
  ann_near = ln(N_entry / S_entry) x 365 / DTE_near_days,
  ann_far = ln(F_entry / S_entry) x 365 / DTE_far_days,
  DTE = (D - close_time(T_k)) / 86400s per leg.
- ENTER iff ann_far - ann_near >= 0.02. No other filter, no carry-threshold
  interaction (the spread is evaluated standalone even when the base carry
  filter skips the same quarter).

## Settlement / exit (fixed)

- Settlement S_del = spot 4h CLOSE of the spot bar containing D_near
  (first spot bar with open_time <= D_near < close_time; its close).
- Far-leg close F_far_del = resampled far-contract 4h close at that same
  delivery bar (last far 4h close with close_time <= delivery-bar
  close_time on Bybit; last 1h close with 1h open_time < delivery-bar
  close_time on Binance; both strictly causal and use no post-delivery
  information). "Closed in the same hour" = this same delivery bar.
- If D_near is beyond the last spot bar, or S_del / F_far_del is missing,
  the trade is INCOMPLETE and excluded (counted separately, no P&L
  imputed). No other settlement model.

## Per anchor year reporting (fixed)

- Anchors A_k = 2021..2025-09-24, year Y_k = [A_k, A_k + 365d), grouped by
  ENTRY bar open_time. Incomplete and no-pair entries are listed but
  excluded from year stats.
- Per venue per coin per year and per venue per year total: n_considered
  (pairs with both legs available), n_entered, mean spread
  (ann_far - ann_near) at entry, mean DTE_near, mean ret_alloc,
  sum ret_alloc (total return on allocated).
- Contribution to the ACCOUNT at f = 0.125:
  contrib_acct(f) = f x (sum of ret_alloc over spreads entered in Y_k),
  reported as total % over the year and as %/month = total / 12 (indexed
  equity, ignores intra-year compounding; linear in f).
- Worst mark-to-market of the spread: at each 4h close t in (T_k, D_near]:
  mtm_alloc(t) = (N(t)/N_entry - 1) + ((F_entry - F(t))/F_entry) - 0.0011
  (entry fees paid: 2 x 0.00055; exit fees not yet paid).
  Per-trade worst = min_t mtm_alloc; year worst = min over trades; account
  units = f x worst with f = 0.125.
- 5-year summary per venue: same stats pooled + geometric-mean %/month
  equivalent of the spread sleeve alone at f = 0.125 (compounded from
  yearly contrib_acct factors), for context only (the verdict uses yearly
  signs, not the mean).
- Correlation with the base carry returns (both causal, realised returns
  only, no lookahead): base series are `oc_cashcarry/results.json` trades
  (Binance) and `bybitq/results_bybit_carry.json` inverse trades (Bybit),
  ret_alloc per delivery. (a) Per-year sums: Pearson r between the spread
  yearly sum_ret_alloc and the base yearly sum_ret_alloc (n = 5, reported
  with this caveat). (b) Per-trade matched on the same coin + near
  delivery (= base delivery where both entered): Pearson r over matched
  pairs + n_matched. Both rows are descriptive; neither enters the verdict.

## Verdict rule (fixed)

- USEFUL iff the spread yearly net on allocated (sum_ret_alloc, sign is
  f-independent) is > 0 in >= 4 of the 5 anchor years on BOTH venues
  (Binance proxy AND Bybit inverse); else CLOSE. The f = 0.125 account
  contribution and worst-MtM rows are reported regardless.

## Deliverables (fixed)

- `research/tournament/oc_calendar/`: THIS PLAN.md (written first),
  `analyze_calendar.py` (one process, 4h/hourly data only, peak RAM < 2 GB),
  `results.json`, `REPORT.md` (per-year tables for both venues + margin-free
  MtM context + correlations + one-line verdict). `tests/test_oc_calendar.py`.
  No commits. No edits outside these two paths.
- Causality tests: entry uses only 4h closes <= entry close (truncate
  check); settlement is the delivery-bar spot close and the far close at
  the same bar (hand check); fee math spot-checked by hand (0.00185 drag);
  threshold respected on every trade (spread >= 0.02); results.json <->
  REPORT.md consistency; script never references 1m/intraday paths.

## Post-hoc correction log (2026-10-06, after first script run, before REPORT)

- CORR-1 (entry timing): the first draft defined T_k as the first bar with
  spot + near + far all available. The first run showed this slipped
  entries ~80-90 days past the roll date on Binance (far quarterlies list
  only ~3 months before their own delivery, i.e. ~7d before the near
  delivery), producing 3-10d DTE_near holds with annualised bases divided
  by a few days (spreads up to 17 pp, pure short-DTE noise) — not "at each
  oc_cashcarry roll date" as the assignment orders. Corrected to: T_k is
  the oc_cashcarry roll bar for the near contract (near + spot only); a
  missing far leg at that bar is NO_FAR_AT_ROLL, never a slipped entry.
  No threshold, fee, holding or verdict rule was changed; only the entry
  date definition was brought back to the assignment text.

(End of PLAN - frozen before outcomes.)
