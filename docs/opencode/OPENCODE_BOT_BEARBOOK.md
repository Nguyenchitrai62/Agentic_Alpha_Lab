# OpenCode task: bear-regime book filter in the order-mirror bot (read AGENTS.md, OPENCODE_VF_COMMON.md, docs/BOT_EXECUTION.md)

Scope: edit ONLY bot/mirror.py, bot/run.py, bot/bybit_v5.py (if needed) and tests/test_bot_mirror.py. Default behaviour unchanged (option off
-> identical orders; all existing tests pass unchanged). No live trading, no keys, no commits, do not touch the backend.

Research result (registry v410, R2B1D18BF): book LONG targets are halved while BTC trades below its 200-day mean, defined EXACTLY as: the
latest BTCUSDT 4h bar OPEN (bars start 00/04/08/12/16/20 UTC) < the simple mean of the last 1200 4h opens including it (min 600). Book shorts
and dip rungs are unaffected.
1. bybit_v5.py: `klines_4h_opens(symbol, n=1200)` paging the public kline endpoint (interval 240, limit 1000, `end` cursor) and returning the
   last n 4h opens oldest-first (closed and current bars; the current bar's open is known).
2. mirror.py: `desired(..., bear_book=False, bear=False)`: when bear_book and bear, book ENTRY and ADD orders with a LONG side get qty x 0.5
   (short side unchanged; reduce / close / tp / stop unchanged; dips unchanged). Pure function `is_bear(opens) -> bool`.
3. run.py: flag `--bear-book` (default off); each cycle (cache 10 minutes) compute bear from klines_4h_opens('BTCUSDT') and pass it; log
   op='bear_state' when it changes.
4. tests: is_bear on synthetic series (600 / 1200 bars, above / below); desired with bear_book on/off (long qty halved, short unchanged,
   dips unchanged); default-off identity.
Run `.venv/Scripts/python.exe -m pytest -q tests/test_bot_mirror.py`; add a CHANGES line to docs/BOT_EXECUTION.md.
