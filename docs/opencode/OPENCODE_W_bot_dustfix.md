# OpenCode task bot_dustfix - analyse the residual unprotectable dust pieces (SOL qty 0.0999 < 0.1 lot) and propose a fix (bot/ READ-ONLY)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/bot_dustfix/`, `tests/test_bot_dustfix.py` (tests of
your proposed logic against copies under your folder) and `docs/opencode/BOT_DUSTFIX_20261007.md`. Never edit bot/, never touch artifacts/bot/*
or running processes; paper / mock only.

## Context
docs/opencode/BOT_SOAKINV_20261007.md: in every soak run of the 2025-10-10 flush window, 4 SOL dip pieces end with qty 0.0999 (< the 0.1 lot
minimum): their protective stop / TP cannot be placed (Bybit rejects qty below the minimum) and dust_close with qty 0 is rejected -> the
health check reports them unprotected. Commit 40e5fdf added "dust skip/close" (read bot/run.py and bot/mirror.py for dust / min-qty logic,
and docs/opencode/BOT_SOAK_20261006.md, BOT_SOAKFIX_20261006.md).

## Tasks
1. Reproduce with the soak harness (tests/soak_bot.py; shortest window that produces the dust) and explain exactly how a 0.0999 SOL piece
   arises (partial fill of an entry? rounding of corr-size / dip-mult sizes? a partial TP leaving a remainder?), with the action log lines.
2. Live relevance: can this happen on Bybit (partial fills of limit entries do happen), and what does the real exchange do with a 0.0999
   position (it can be closed with a reduce-only market order of qty 0.1? Bybit allows closing the whole position with reduceOnly and a
   qty >= the position - check the V5 docs for "close position" / closeOnTrigger / qty rules).
3. Propose a minimal fix as a diff (do not apply): e.g. round entry quantities so that remainders stay >= the lot minimum, or merge a dust
   remainder into the protection of the same-symbol position, or close dust with a reduce-only order of the minimum lot. Prove it on copies of
   bot/run.py / bot/mirror.py under your tmp folder with tests (no dust pieces left unprotected in the reproduction; no position flip; no
   over-sell). Doc (<= 40 lines): cause, live relevance, proposed diff, test results.
