# OpenCode task oc_liqfirst - liquidation / top-of-book collector: coverage audit + first descriptive event table (no trading rule)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_liqfirst/`. backend/ and data/raw/liquidations_live,
data/raw/topbook_live are READ-ONLY; never start / stop the backend.

## Tasks
1. Coverage since 2026-10-04 per venue (Bybit allLiquidation, Binance forceOrder) and for top-of-book: hours with data / wall-clock hours, gaps
   > 5 min (start, end, length), and whether the backend process has run continuously since its last start (compare with
   artifacts/web/*.log if present). This decides when the dataset becomes research-grade (rule: >= 95 % coverage for >= 3 months).
2. Descriptive only (no rule, nothing selects anything): for every 4h bar since 2026-10-04 with full coverage, total liquidation notional per coin
   (long vs short liquidations) and the bar's dip-ladder activity from the G2 paper runner artifacts/bot/paper_d17bfg2 (fills, stops, TPs per
   coin and bar, from actions.jsonl). A table and two plots (PNG) - liquidation notional vs dip fills / stops per bar. State plainly that the
   sample is days, not years.
3. A short README for future researchers: file schema, timestamps (event vs receive), dedup rules, known gaps. Vietnamese 3-line summary.
