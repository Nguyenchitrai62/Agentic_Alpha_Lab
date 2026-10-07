# OpenCode task bot_exitsoak - regression soak for bot-side market exits (time exits, close5 stops) + review of the leader fix
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/bot_exitsoak/`, `tests/test_bot_exitsoak.py` and
`docs/opencode/BOT_EXITSOAK_20261007.md`. bot/ is READ-ONLY for you (propose diffs in the doc; the leader applies them). Never touch
artifacts/bot/* or running processes; paper / mock exchange only, never testnet or live keys.

## The bug the leader just fixed (uncommitted, bot/run.py)
Since commit 1c0469a the market-exit link is registered in state["links"]. The paper exchange (bot/paper.py) fills a market order at the open
of the next 1m bar, so in the cycle that sends it, `Runner.have()` lists it and `mirror.diff(want, have)` cancelled it (not a wanted resting
order). Result in the paper runners (2026-10-07 03:00 UTC on): every time exit was sent, cancelled 20 ms later, re-sent after
EXIT_INFLIGHT_MIN = 2 min, forever; 20-24 pieces per runner stayed open with no stop/TP. Fix: `_acts_without_exit_cancel(acts, led)` drops
cancels of the confirmed exit_link of any open piece, applied after `_acts_without_carry_cancel` at both diff sites (main cycle and the
protection-only path). Unit tests: tests/test_bot_exit_keep.py. Why the existing soaks missed it: find out (did tests/soak_bot.py or the soak
tests ever produce a time exit or close5 stop on the paper/mock exchange after 1c0469a?).

## Tasks
1. Read bot/run.py (cycle, exits loop, `_guard_phantom_cancels`, `_acts_without_exit_cancel`), bot/mirror.py (exits, `_market_inflight`,
   diff), bot/paper.py and the existing soak tooling (tests/soak_bot.py, tests/test_bot_soak*.py, research/tournament/bot_soak*).
2. Build a deterministic soak (mock or paper exchange fed with recorded 1m klines - reuse the existing soak harness) that forces: (a) dip pieces
   reaching their 4h time exit, (b) close5 stop-outs, (c) a book exit, (d) a runner restart between sending a market exit and its fill,
   (e) a partially filled market exit (mock exchange reports PartiallyFilled for one cycle). Run it on the CURRENT working tree (with the fix)
   and on a copy of bot/ from `git show HEAD:bot/run.py` (without the fix) placed under your folder's tmp/ (never modify bot/). Expected:
   without the fix, exits never complete; with the fix, every exit completes within <= 2 cycles, no piece is left without protection for
   longer than one cycle, no double exit (position never goes below zero / reduce-only never over-sells).
3. Review the fix for live / testnet: can a confirmed exit link that will never fill (rejected, expired IOC) now block a re-send forever or keep
   a stale order? Can the kept market order and a re-sent one both fill (reduce-only caps it - verify on the mock)? Propose diffs if needed.
4. `docs/opencode/BOT_EXITSOAK_20261007.md`: what was tested, results table (with / without fix), any new bug, proposed diffs, verdict for
   testnet readiness. Tests in tests/test_bot_exitsoak.py must pass on the current tree.
