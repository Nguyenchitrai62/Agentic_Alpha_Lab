# oc_recent PLAN (pre-registered BEFORE any new outcome is computed, 2026-10-06)

DIAGNOSTIC task only (no selection, no PROMISING rule, no verdict threshold).
Question: what changed in the most recent research year (anchor 2025-09-24 ..
2026-09-23, R2B1D17BF 5.06 %/mo) vs the four earlier years, esp. vs 2024-25
(11.27 %/mo), and what does it imply for live expectations?

## Data (fixed, read-only; nothing else is read)
- research/tournament/oc_kpi/events_s{0..3}.parquet (R2B1D17BF engine replicas,
  s=0..3 phase sub-accounts, each 1/4 capital; pooled counts = sums).
- research/tournament/oc_kpi/barsum_s{0..3}.parquet (book-open counts only).
- research/tournament/oc_kpi/results.json (+ results_equity.json): monthly
  calendar path, yearly reset rows, pooled win rates (cross-check source).
- Market data window: everything used has t < 2026-09-24 00:00 UTC. All five
  anchor years are research data; findings need prospective validation.
- LIGHT: one process, shifts processed sequentially, no 1m data, RAM < 1 GB.

## Exact causal definitions (frozen here)
- Anchor years: A = (2021-09-24, ..., 2025-09-24), A_5 = 2026-09-24 (UTC).
  Year bucket of a trade = ENTRY time: book episode entry_t (book_fill t),
  rung fill_t; year k iff A_k <= t < A_{k+1}. No exit-time bucketing.
- Book episodes: exact copy of oc_kpi compute_kpi.book_episodes (v213 loop):
  book_fill opens (side=+1 long if side=='buy' else -1 short; cost=|weight|),
  book_add/reduce/partial folded, episode ends at first book_stop/book_tp/
  book_close; net = (side*(proceeds-cost)-fees)/cost, maker 0.0002
  entries/TP/close, taker 0.00055 stops, funding excluded. Positions still
  open at the live end are excluded (counted as a check).
- Rungs: FIFO per-symbol fill->exit pairing (rung_fill -> rung_sl/rung_tp/
  rung_timeout); ret = engine ret (already net of rung maker/taker fees and
  timeout funding); fill weight recorded. Unpaired exits counted as a check.
- Sleeves: book_long (episode side +1), book_short (side -1), dip (rungs).
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (no grouping).
- Dip per calendar month M (fill month): fills, win rate, mean ret, exit
  shares (sl/tp/timeout), mean fill weight, gross fill notional proxy
  sum(fill weights). Per anchor-year x sleeve x coin: n, win, mean net/ret,
  exit shares (rungs), mean weight.
- Monthly path: taken verbatim from oc_kpi results.json equity.monthly
  (calendar months, continuous 4-phase mix); year slices are calendar months
  2024-10..2025-09 (year 3) vs 2025-10..2026-09 (year 4); top-carry months =
  largest log(1+R) contributors; concentration = share of year log-return.
- No equity re-attribution by sleeve (would need a sleeve on/off replay);
  trade-level means are returns on position notional, reported alongside
  counts/win/exit-mix; the equity path comes only from the frozen monthly mix.

## Outputs (fixed)
- analyze_recent.py (this PLAN's definitions verbatim), results.json
  (per-year x sleeve x coin, dip per-month, book per-side, monthly slices,
  year3-vs-year4 comparison, checks), REPORT.md (tables + one-line
  descriptive verdict; no PROMISING/REJECT). Test tests/test_oc_recent.py.
- Checks in results.json: year partitions sum to pooled totals; rung exits
  add up; max event t < 2026-09-24; monthly slice compounding matches the
  yearly narrative; PLAN.md mtime <= results.json mtime.
