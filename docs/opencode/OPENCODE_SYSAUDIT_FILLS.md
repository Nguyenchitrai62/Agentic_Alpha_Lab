# OpenCode assignment: SYSTEM AUDIT 1 - independent trade-level check of the simulation engine against raw 1m data

Goal: verify, independently of the engine code, that every simulated order of two deployed pipelines obeys the execution rules
of AGENTS.md when replayed on the raw Binance 1m klines. You do NOT run or import the engine
(`research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py`); you may READ it only AFTER part A is saved.

## Write scope (nothing else)
- `research/diagnostics/system_audit/fills_opencode/` (scripts, CSV, `replication.json`, `SUMMARY.md`)
- `tests/test_system_audit_fills.py`
Do not edit any other file (engine, backend, scripts, ledgers, NEXT_AGENT.md, CONTINUOUS_RESEARCH.md, ../Kronos, git state).
Run tests with `.venv/Scripts/python.exe -m pytest tests/test_system_audit_fills.py -q`.

## Inputs (read-only)
- Events: `artifacts/research/system_audit/events_v367.parquet` (pipeline M5) and `events_v321.parquet` (pipeline R2).
  Columns: t (UTC timestamp of the event minute = holding-bar start + minute), symbol, kind, side, price, weight, plus optional
  sl, tp, offset, issued_bars_ago, scale, ret, rung, why. Kinds: order_issue, order_cancel, order_expire, book_fill, book_add,
  book_reduce, book_close, book_stop, book_tp, sl_move, rung_fill, rung_tp, rung_sl, rung_timeout.
- Bars: `artifacts/research/system_audit/bars_v367.parquet`, `bars_v321.parquet`: one row per 4h holding bar t (bar start), columns
  open_<SYM> (engine's bar-start price), sig_d_<SYM> (daily sigma; sigma_4h = sig_d / sqrt(6)), sl_<SYM>, tp_<SYM>, qty_<SYM>, ...
- Raw 1m klines: BTC `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`; others
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet` (columns open_time, open, high, low, close; drop duplicate open_time).
- Reference results: `artifacts/research/system_audit/result_v367.json`, `result_v321.json`.

## Rules to verify (exact definitions; minute m of a holding bar = the 1m kline opening at bar start + m minutes, m = 0..239)
Fees: maker 0.0002, taker 0.00055. Price tolerance: relative 1e-6 (the engine stores 1m data as float32: allow 1e-6 relative).
1. Bar alignment: for 500 random (bar, symbol) rows, `open_<SYM>` == the raw 1m open at the bar start.
2. Book entry orders (order_issue rows WITHOUT a `scale` value, kind book entries): the resting limit is filled (book_fill) at the
   FIRST minute where low < price (buy) / high > price (sell), strictly; the first eligible minute is 5 in the bar where the order was
   issued (issued_bars_ago == 0) and 0 in later bars; fill price == order price. Count fills that happen too early, fills at a minute
   where the trade-through condition is false, and orders that should have filled earlier.
3. Book exits: book_stop: for a long the minute's low <= SL and price == min(SL, minute open) (short: high >= SL, price == max(SL, open)),
   where SL is the level in force (from the latest book_fill / book_add `sl` or sl_move `price` of that position); book_tp: high > TP
   strictly (long) / low < TP (short), price == TP. No earlier minute since the level was set may satisfy either condition; if the stop
   and the take-profit are both satisfied in one minute the event must be the stop (stop-first).
4. Dip rungs (rung_fill): fill minute in [16, 238]; price == bar open * (1 - k * sigma_4h) with k in {3.0, 4.0} for v367 and
   {2.5, 3.0, 3.5, 4.0, 5.0} for v321; it is the first minute in [16, 238] with low < price.
5. Rung exits. v367 (touch stops): rung_sl at the first minute x > fill minute with low <= price_fill * (1 - 8 sigma_4h), exit price
   min(stop, open of x); rung_tp: high of x > the exit price (TP) and no minute in (fill, x) touched the stop; rung_timeout: exit at the next
   bar's open (bar start + 240 min) when neither happened. v321: stop triggers when a 5-minute block close (minutes m with (m+1) % 5 == 0)
   is <= price_fill * (1 - 4 sigma_4h) -> exit at the next minute's open; plus a native touch backstop at price_fill * (1 - 8 sigma_4h)
   (fills at min(level, open)) which wins ties. `ret` must equal exit/fill - 1 - 0.0002 - (0.00055 for stops and timeouts, 0.0002 for
   take-profits) - 0.0001 for timeouts whose exit is at 00:00, 08:00 or 16:00 UTC (funding).
6. Report separately (not an error, a known engine convention): rung fills whose FILL minute low is already <= the touch stop / backstop
   (the engine checks rung exits from the minute after the fill).

## Procedure
A. Write your own replay checker from the rules above, run it on BOTH event files, and save `replication.json` (counts of checked
   events and mismatches per rule and pipeline, 10 examples each) BEFORE reading engine_user.py.
B. Then read engine_user.py; for every mismatch class decide: (i) engine bug, (ii) rule ambiguity in this assignment, (iii) your bug.
   Record in COMPARISON-style `SUMMARY.md` (<= 30 lines): checked counts, mismatch counts, classification, and the estimated effect on
   PnL if any (sum of the affected trades' return difference x weight).
C. Tests: synthetic hand-made minute paths for rules 2, 3 (incl. a stop/TP tie), 4 and 5, plus one assertion that part A found the files.
Stop when done.
