# oc_lots PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis
The deployment pick R2B1D17BF (registry v411, phase s=0 replica in
research/tournament/oc_ddanat17) is placeable on Bybit at large account sizes,
but at small account sizes a material share of book orders (BTC first) and a
smaller share of dip rungs fall below the Bybit lot / 5 USDT minimums, so the
unplaceable subset carries a non-trivial share of simulated P&L.

## Inputs (fixed)
- research/tournament/oc_ddanat17/events_s0.parquet (20183 events, one engine
  phase s=0, live 2021-09-24..2026-09-23+12h; 1m read to 2026-09-24 00:00 UTC).
- research/tournament/oc_ddanat17/rungs_s0.parquet (5466 dip rungs, same run).
- Bybit public GET /v5/market/instruments-info (category=linear) for the 5
  majors at run time; hardcoded fallback snapshot
  BTC 0.001 / ETH 0.01 / SOL 0.1 / BNB 0.01 / XRP 0.1, min notional 5 USDT
  (identical to the live values on 2026-10-05; source recorded in results.json).
- No 1m data, no refit, no selection, one process, RAM < 1 GB. All five years
  are research data (assignment override); findings need prospective validation.

## Exact causal definitions (fixed before running)
- Book orders (primary): every `order_issue` event with |weight| > 0 (the
  resting limit the trader must place; weight==0 close-orders place nothing).
  Sensitivity row: `book_fill` events only (actually filled entries).
  `book_add`/`book_reduce`/SL/TP moves are position management, not new orders.
- Dip rungs: every row of rungs_s0.parquet (= every `rung_fill`).
- Phase equity: account sizes A = 1000 / 2000 / 5000 / 10000 / 20000 USDT,
  one sub-book per clock => phase equity E = A / 4.
  Notional N = |weight| * E. Raw qty q = N / price, with price = order_issue
  price (book) or fill_price (dip).
- Bybit placeability: let step = qtyStep, m = minOrderQty. Floored qty
  qf = floor(q / step) * step (plus 1e-9 eps). Placeable iff
  qf >= m - 1e-9 AND qf * price >= 5.0 - 1e-6. No rounding-up (no over-fill).
- Count share: placeable orders / all orders, per coin and overall,
  per account size, separately for book orders and dip rungs.
- P&L share: dip rungs use rungs_s0.loss (= weight*ret, fraction of bar-start
  equity): net share = sum(loss of placeable) / sum(loss of all); gross share
  = sum(|loss| of placeable) / sum(|loss| of all). Book P&L uses FIFO matching
  per symbol of entry lots (book_fill + book_add, signed weight w, entry price
  p0) against exits (book_close / book_reduce / book_stop / book_tp, exit
  price p1): each exit consumes oldest open lots proportionally; realized
  lot P&L = matched_|w| * side * (p1 - p0) / p0 with side = +1 for long
  (w>0) and -1 for short (w<0). Entry-lot P&L is attributed to the placeability
  of the corresponding book order: primary mapping matches each book_fill to
  its order_issue (same symbol/price/weight, nearest earlier issue); book_add
  lots map to themselves at their own price/weight. Book net/gross P&L shares
  are defined analogously to dips. Leftover open inventory at the end is
  reported as unmatched notional (no mark-to-market in the share).
- Anchor-year rule is not applied (single pooled phase s=0 by design);
  per-anchor-year count-share columns are reported descriptively only.

## Decision / verdict rule
- Default tournament rule recalled for context: PROMISING only if the effect
  has the same sign in >= 4 of 5 anchor years AND holds leave-one-year-out in
  >= 4 of 5. This study makes no PROMISING claim by design.
- Verdict = one deployment-note sentence: the smallest account size at which
  >= 99% of book orders and >= 99% of dip rungs (and of their gross P&L) are
  placeable, and which coin is the bottleneck below it.

## Outputs
- run_oc_lots.py (single light process); results.json (lot rules, per-account
  per-coin count shares, dip/book net+gross P&L shares, FIFO diagnostics);
  REPORT.md (tables + one-line verdict). Test: tests/test_oc_lots.py.
