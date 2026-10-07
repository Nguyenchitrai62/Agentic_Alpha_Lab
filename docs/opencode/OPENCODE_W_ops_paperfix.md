# OpenCode task ops_paperfix - quantify how the 2026-10-07 exit bug + outage distorted the paper evidence
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/ops_paperfix/` and
`docs/opencode/PAPERFIX_20261007.md`. artifacts/bot/* is READ-ONLY (never edit state.json / actions.jsonl / exchange.json); never start / stop
processes.

## Facts
- Paper runners (artifacts/bot/paper, paper_d17bf, paper_d13bf, paper_d17bfg2, paper_g2k20, paper_d17bfg2c, paper_g2k20c) run bot code
  1c0469a since ~2026-10-06 20:10 UTC. A bug (market exits cancelled in the same cycle, see docs/opencode/OPENCODE_W_bot_exitsoak.md) meant
  no bot-side market exit (time exit at the next 4h open, close5 stop) ever executed. First stuck exits: 2026-10-07 03:00 UTC.
- All runners stopped ~03:24 UTC and were restarted 07:01 UTC (still buggy), then restarted with the fix at ~07:29 UTC; the stuck pieces
  exited at market around 07:30-07:35 UTC.
- Grep `"op": "market_exit"` and `"op": "cancel"` in each runner's actions.jsonl (the stdout.log mirrors it) to see the loop.

## Tasks
1. Per runner: list every piece whose bot-side exit was due (time exit at t_exit, or a close5 stop condition - recompute from the piece's
   stop5 level vs Bybit 1m closes in 5-minute blocks exactly as bot/mirror.exits does) between 2026-10-06 20:10 UTC and the fix, the time it
   SHOULD have exited and the price it would have got (market at the open of the first minute after the due time, taker 0.00055), versus the
   time and price it actually exited. Use Bybit public 1m klines (GET https://api.bybit.com/v5/market/kline, category=linear, public, no key)
   or the runners' shared kline cache artifacts/bot/_kline_cache (read-only).
2. Per runner: actual P&L vs corrected P&L (difference in USDT and in % of equity), number of affected pieces, max extra exposure held while
   stuck, and whether any piece breached its 8-sigma backstop level during the stuck window.
3. Also check: during 03:24-07:01 (outage) which resting TP / entry fills were missed or booked late (from oc_oosweek: the 04:00 cycle was
   missed).
4. `docs/opencode/PAPERFIX_20261007.md` (Vietnamese, <= 50 lines): table per runner (actual vs corrected P&L, pieces affected), and a
   one-line recommendation for how the prospective scorecard should treat the window 2026-10-06 20:10 .. 2026-10-07 07:35 UTC (exclude /
   correct / keep). No edits to any scorer.
