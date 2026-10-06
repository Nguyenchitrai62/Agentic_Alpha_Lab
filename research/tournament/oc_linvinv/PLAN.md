# oc_linvinv PLAN (pre-registered BEFORE any outcome is computed)

Question: does the same-expiry linear-vs-inverse quarterly dislocation on
Bybit lock a convergence profit (long cheap / short rich, hold to delivery)
without a funding leg? Mechanism (IDEAS3_20261006 idea 1): same-expiry
BTC/ETH linear (USDT-M) and inverse (coin-M) quarterlies must converge to
one settlement; margin-segmentation dislocates them; long cheap / short
rich locks convergence, delta ~ 0, no funding leg.

## Data (fixed here, read-only, 4h only, LIGHT, no re-download)

- Bybit hourly klines under `data/raw/bybit_quarterly_20261006/` (gitignored):
  `spot_BTCUSDT_1h.parquet`, `spot_ETHUSDT_1h.parquet`,
  `inv_BTCUSD*_1h.parquet` / `inv_ETHUSD*_1h.parquet` (inverse quarterly
  H/M/U/Z chain), `lin_BTCUSDT_*_1h.parquet` / `lin_ETHUSDT_*_1h.parquet`
  (linear USDT dated). `lin_BTC_*` / `lin_ETH_*` (USDC weekly) files are
  NOT used.
- Expiries/deliveries are FIXED by `research/data_fetch/bybitq/inventory.json`
  (`deliveryTime` exact ms from the venue, instruments-info). No parsing of
  date codes for delivery.
- Same-expiry pair = one linear-USDT contract and one inverse contract on
  the SAME coin whose `deliveryTime` is the SAME millisecond. From the
  inventory that is exactly 8 deliveries per coin (BTC: `BTCUSDT-27JUN25` =
  `BTCUSDM25`, `...-26SEP25` = `...U25`, `...-26DEC25` = `...Z25`,
  `...-27MAR26` = `...H26`, `...-26JUN26` = `...M26`, `...-25SEP26` = `...U26`,
  `...-25DEC26` = `...Z26`, `...-26MAR27` = `...H27`; same pattern for ETH).
  Linear USDT quarterlies only exist on Bybit since 2025-02-18, so pairs
  exist only for 2025+ deliveries. Coins: BTC + ETH only.
- Spot 4h grid: Bybit spot hourly -> 4h bars on the 00/04/08/12/16/20 UTC
  grid; bar close = hourly close of hour 4k+3; a 4h bar is valid ONLY if
  all 4 hours are present (else NaN). Futures 4h: same grid per contract;
  resampled F(t) = last futures 4h close with futures close_time <= spot
  bar close_time (strictly causal, same code path as
  `research/data_fetch/bybitq/analyze_bybit_carry.py`).
- No 1m data is loaded. No statistic from any test/walk-forward year feeds
  any choice below (single fixed threshold, no tuning).

## Roll / entry rule (fixed, causal, one opportunity per pair)

- Per coin, sort the 8 same-delivery pairs ascending: D_0..D_7.
- For pair k >= 1: candidate E_k = round_UP(D_{k-1} - 7 days) to the next
  spot 4h open_time ("enter the next pair when the front pair has <= 7 days
  left", the oc_cashcarry roll cadence applied to this pair chain). For
  k = 0: E_k = first availability.
- Actual entry bar T_k = max(E_k, first spot 4h bar with a spot close AND a
  resampled linear-4h close AND a resampled inverse-4h close for pair k
  available at its close). Exactly one entry opportunity per pair. All
  information used (F_lin, F_inv, S_entry) comes from 4h closes with
  close_time <= T_k close.
- DTE_days = (D_k - close_time(T_k)) / 86400. Annualised bases at entry:
  ann_lin = ln(F_lin_entry / S_entry) * 365 / DTE_days,
  ann_inv = ln(F_inv_entry / S_entry) * 365 / DTE_days.
- ENTER the spread iff |ann_lin - ann_inv| >= 0.03 (3 pp/yr, fixed, no
  tuning). Else SKIP that pair. Side: LONG the cheaper (lower futures
  price / lower basis), SHORT the richer, in EQUAL USD entry notional
  f = 0.125 per coin per leg (total spread gross 2f per entered pair).
  The threshold, f, the 7-day roll and hold-to-delivery are frozen here;
  no variant is tested.

## Position / hold / fees / P&L (fixed)

- Hold BOTH legs to the shared delivery D_k. No early exit, no stop (the
  hedge is delivery-locked; MtM tracked for information only). Pairs never
  overlap for the same coin by construction (deliveries ~84 days apart).
- Settlement: both contracts settle to one index, modelled as the Bybit
  SPOT 4h CLOSE of the spot bar containing D_k (first spot bar with
  open_time <= D_k < close_time; its close). If D_k is beyond the last
  spot bar, the pair is INCOMPLETE: listed but excluded from all P&L
  stats (no P&L imputed). No other settlement model.
- Fees (assignment-fixed): taker 0.055% per leg at entry + 0.02% per leg
  at delivery, both computed on entry notional (delivery-notional scaling
  is second order next to the spread; stated as an approximation).
  Fee drag per entered pair = f * (0.00055 + 0.0002) * 2 = f * 0.0015.
- Inverse P&L in coin, converted at the delivery price (assignment rule):
  for USD entry notional N = f, inverse long of N USD at F_entry holds
  N / F_entry coins; at delivery worth N / S_del coins short of ... :
  P&L_coin(long) = N * (1 / F_entry - 1 / S_del),
  P&L_usdt = S_del * P&L_coin = N * (S_del / F_entry - 1),
  identical to the linear price-return formula. CONVEXITY NOTE (stated in
  REPORT.md): converting the coin P&L at the contemporaneous/delivery
  price makes the USDT economics exactly linear (same formula as the
  linear leg); the 1/F convexity lives only in the coin-denominated path
  (a long gains fewer coins per point up than it loses per point down).
  USDT net per entered pair with cheap leg c and rich leg r:
  P&L = f * [S_del * (1 / F_c - 1 / F_r)] - f * 0.0015,
  gross is mathematically > 0 whenever F_r > F_c (locked convergence);
  net > 0 iff the spread covers the 0.15% drag.
- Return on ALLOCATED: ret_alloc = P&L / f (per-pair capital unit; follows
  the oc_cashcarry convention where each leg = f and ret_alloc = P&L / f;
  fee drag on allocated = 0.0015). Total account contribution of year Y
  at allocation f is f * (sum of ret_alloc over pairs entered in Y).

## MtM (fixed, information only)

- At each 4h close t in (T_k, D_k], with F_c(t), F_r(t) the resampled
  marks (inverse mark converted at the contemporaneous mark, hence the
  same linear formula per the convexity note):
  mtm_alloc(t) = (F_c(t) / F_c_entry - 1) + (1 - F_r(t) / F_r_entry)
  - 0.0011 (entry fees paid: 2 x 0.00055; exit fees not yet paid).
  Per-pair worst = min_t mtm_alloc; year worst = min over entered pairs;
  account units = f * worst.

## Per anchor year reporting (fixed)

- Anchors A = 2021..2025-09-24, year Y = [A, A + 365d), grouped by ENTRY
  bar open_time. Incomplete pairs listed separately, excluded from stats.
- Per coin per year and per year total: n_pairs (same-expiry pairs with
  their entry opportunity in Y), n_entered, n_skipped, mean |basis diff|
  at entry, mean DTE, mean ret_alloc, sum ret_alloc, worst mtm_alloc.
- 5-year pooled: same stats pooled (entries are expected almost only in
  the 2024/2025 window because linear USDT quarterlies start 2025).

## Verdict rule (fixed, assignment text)

- USEFUL only if net > 0 on EVERY entry year AND >= 3 entries total;
  else the data is too short and the direction is CLOSED (verdict: NOT
  USEFUL / data too short, close). Reported regardless: pairs per year,
  entries, net return on allocated, worst MtM.

## Deliverables (fixed)

- `research/tournament/oc_linvinv/`: THIS PLAN.md (written first),
  `analyze_linvinv.py` (one process, 4h data only), `results.json`,
  `REPORT.md` (per-year table + one-line verdict). Plus
  `tests/test_oc_linvinv.py`. No commits. No edits outside these two
  paths. GIT IS READ-ONLY (never stash/reset/checkout/clean/commit).
- Causality tests: entry uses only 4h closes <= entry close;
  truncate-before-entry leaves F/S entries unchanged; settlement uses the
  delivery-bar spot close; fee math spot-checked by hand; results.json
  <-> REPORT.md consistency; script never references 1m/intraday paths.

(End of PLAN — frozen before outcomes.)
