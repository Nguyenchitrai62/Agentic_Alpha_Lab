# oc_carryfar PLAN (pre-registered BEFORE any outcome is computed)

Second and LAST variant of the carry direction. Base rule is frozen in
`research/tournament/oc_cashcarry/PLAN.md`: at each roll enter the NEXT
quarterly when the front has <= 7 d left, iff annualised basis >= 4 %/yr;
equal-notional spot long + quarterly short; hold to delivery; fees spot
0.1 %/side, futures 0.055 % entry, delivery 0.02 %.

## FAR variant (the only variant tested here; frozen)

- At the SAME roll times as the base rule, enter the SECOND-next quarterly
  (about 6 months to delivery) instead of the next one.
- Formally, per coin, sort expiries ascending C_0..C_{N-1} with deliveries
  D_0..D_{N-1}. Base roll times: for k >= 1,
  E_k = round_UP(D_{k-1} - 7 days) to the next spot 4h open_time; for k = 0,
  E_0 = first availability. FAR opportunity k (k = 0..N-2) evaluates
  contract C_{k+1} at time E_k (same E_k as the base opportunity for C_k).
- Actual FAR entry bar T^{FAR}_k = max(E_k, first spot 4h bar with BOTH a
  spot close AND a resampled quarterly-4h close for contract C_{k+1}
  available at its close). Exactly one FAR opportunity per k. All
  information used (F_entry, S_entry) comes from 4h closes with
  close_time <= T^{FAR}_k close (strictly causal).
- Annualised basis on its OWN contract:
  ann_basis^{FAR}_k = ln(F^{k+1}_entry / S_entry) * 365 / DTE^{FAR}_k,
  DTE^{FAR}_k = (D_{k+1} - close_time(T^{FAR}_k)) / 86400 s.
- ENTER iff ann_basis^{FAR}_k >= 0.04 (same fixed 4 %/yr threshold, no
  tuning). Else SKIP. Hold to delivery D_{k+1}. No early exit, no stop.
- Same fees and sizing as base: spot 0.001/side, futures 0.00055 entry +
  0.0002 delivery (drag 0.00275 per allocated unit); each leg = f x Eq_entry
  (Eq_entry = 1.0 indexed; rows f = 0.25 / 0.50 scale linearly); f is PER
  open pair, so overlapping pairs stack.
- Same P&L formula per entered pair:
  P&L = f * [ (S_del - S_entry)/S_entry + (F_entry - S_del)/F_entry
  - 0.00275 ], ret_alloc = P&L / f. Settlement = spot 4h close of the
  delivery bar (first spot bar with open_time <= D < close_time); if D is
  beyond the last spot bar the trade is INCOMPLETE (listed, excluded, no
  P&L imputed).
- Overlap expectation: FAR entries are ~90 d apart with ~185 d holds, so
  pairs overlap (about two open per coin; the script reports the actual
  maximum; any higher transient overlap is reported, not hidden).

## Data (fixed, read-only, 4h only, LIGHT RAM < 1.5 GB)

- Binance proxy: `data/raw/qbasis_20261003/um_BTCUSDT_*_1h.parquet` and
  `um_ETHUSDT_*_1h.parquet` resampled to the Binance spot 4h grid
  (`data/raw/spot_majors_20260925/{BTC,ETH}USDT_spot_4h.parquet`) exactly as
  `oc_cashcarry/analyze_cashcarry.py` does (last 1h close with
  1h open_time < spot bar close_time). Delivery D from the contract code
  (08:00 UTC on code date). BTC + ETH only (`cm_*` unused).
- Bybit inverse: `data/raw/bybit_quarterly_20261006/inv_BTCUSD*_1h.parquet`
  and `inv_ETHUSD*_1h.parquet` + `spot_{BTC,ETH}USDT_1h.parquet`, resampled
  to a 00/04/.. UTC 4h grid exactly as
  `research/data_fetch/bybitq/analyze_bybit_carry.py` does (valid 4h bar =
  all 4 hours present; F(t) = last futures 4h close with
  close_time <= spot close_time). Delivery D = exact `deliveryTime` from
  `research/data_fetch/bybitq/inventory.json` (inverse quarterlies only;
  linear/USDC contracts unused). Inverse prices are in USD; the ln(F/S)
  basis + price-return P&L formula is applied unchanged (coin-settlement
  convexity noted, not modelled — same approximation as the bybitq report).
- No 1m data is loaded. No re-download. Base is RECOMPUTED in-script on both
  venues with the frozen base rule for a like-for-like comparison, and must
  reproduce `oc_cashcarry/results.json` (pooled sums) and
  `results_bybit_carry.json` inverse sums within 1e-6; otherwise the run
  fails.
- Market data up to 2026-09-23 may be read (all five anchor years are
  research data; findings need prospective validation like everything else).

## Per anchor year reporting (fixed; base vs FAR on BOTH venues)

- Anchors A = 2021..2025-09-24, year = [A, A + 365 d), grouped by ENTRY bar
  open_time. Per venue (binance / bybit_inv), per arm (base / far), per year:
  n_entered, n_skipped, mean entry ann_basis, mean DTE, sum ret_alloc (carry
  return on allocated capital), mean ret_alloc, worst 4h-close MtM on
  allocated (same MtM definition as the base PLAN: entry fees paid only).
- Max simultaneous allocation: max over the spot 4h grid of open-pair count
  (total and per coin), reported as multiples of f and in equity units at
  f = 0.25 (sum of open pairs' f).
- Account-level add at f = 0.25: contrib(f) = f * sum_ret_alloc per year
  (year % and %/month = /12), plus 5-year pooled total and geometric-mean
  %/month (compounding yearly factors 1 + f*year_sum).
- Per-year head-to-head: FAR sum_ret_alloc minus base sum_ret_alloc, counted
  separately on each venue.

## Margin interaction (fixed; oc_utamargin rule)

- Bybit UTA rule from `research/tournament/oc_utamargin` (frozen inputs,
  nothing refit): IM = (G2 gross + carry short) / 5 (5x runbook minimum);
  margin balance = total equity - 0.05 x spot value (BTC/ETH 95% base tier;
  account < 10k stays base); BLOCKED iff IM > 95% of balance; liquidation
  iff balance < MM with per-instrument TIERED MM (live Bybit tiers fetched
  2026-10-06, frozen in `oc_utamargin/results.json`; tier-1 BTC/ETH
  MMR = 0.33% is the binding tier at this size, reused here as the MM bound).
- Checked on the spot 4h grid over 2021-09-24..2026-09-23 at f = 0.25 with
  the FAR carry short/spot series on BOTH venues' legs (Binance-proxy legs
  on the Binance spot grid AND Bybit-inverse legs on the Bybit spot grid;
  both reported): G2 gross envelope = book_gross(t) + 2.0 dip cap per phase
  (same conservative time-varying envelope as the oc_cashcarry margin
  section; `oc_kpi_g2/barsum_s{0..3}.parquet` book_gross + equity), carry
  short added time-varying, worst-case overlap, carry unreal added to
  equity. Report max IM/balance per phase, blocked 4h closes (must be 0 on
  both venues to pass), max MM/balance, max spot cost / equity (cash
  headroom), and the worst-hour G2 + carry-short decomposition.
  STATED LIMITATION: 4h proxy only (no hourly replay, no 1m wicks); the
  hourly UTA replay would be tighter, so a 4h pass is necessary but not
  sufficient — reported as such.

## Verdict rule (fixed)

- FAR BETTER only if (a) per-year carry return on allocated (sum ret_alloc)
  is higher for FAR than base in >= 4/5 anchor years on BOTH venues
  (Binance proxy AND Bybit inverse, counted separately), AND (b) the margin
  check shows zero blocked 4h closes at f = 0.25 on both venues' FAR legs.
  Otherwise the base rule stays and the carry direction closes
  (no further variants).

## Deliverables (fixed)

- `research/tournament/oc_carryfar/`: THIS PLAN.md (written first),
  `analyze_carryfar.py` (one process, 4h data only, peak RAM < 1.5 GB),
  `results.json`, `REPORT.md` (per-year base-vs-FAR tables for both venues
  + margin table + one-line verdict). `tests/test_oc_carryfar.py`.
  No commits. No edits outside these two paths.
- Causality tests: FAR entry uses only 4h closes <= entry close;
  truncate-before-entry leaves F_entry/S_entry unchanged; fee math
  spot-checked by hand; results.json <-> REPORT.md consistency; script never
  references 1m/intraday paths; base recomputation matches frozen results.

(End of PLAN — frozen before outcomes.)
