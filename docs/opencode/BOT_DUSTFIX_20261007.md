# BOT_DUSTFIX_20261007: SOL 0.0999 dust cause + F2 min-lot close (bot/ READ-ONLY)

Cause (repro 6h flush 16:00Z 2025-10-10, 1080 cyc): entry 0.9 amended to 0.7
(dip-gross-cap) + remainder 0.2 fill 0.7+0.2=0.8999.. (float); protection
round_step DOWN sizes TP/S at 0.8; TP fill leaves 0.09999999999999987 bit-for-bit.
Its S/T round to 0 (skipped_below_minimum) and dust_close qty 0 is rejected
110094 every cycle (444x) - exit_sent never set, piece unprotected forever.
Not a partial entry fill nor corr-size rounding: entries were whole-lot.
Shortest window: 5.5h from 16:00 (1h@21, 2h@20, 2.5h@19 stay clean).
Live relevance: YES - limit partial fills happen; same float/round-down truncation
applies to any TP remainder landing just under a lot step.
Proposed diff (NOT applied, tmp/run_fixed.py:1710, mirror untouched): dust_close
qty = max(round_step(qty), min_qty), i.e. 0.1 reduce-only market. Safe: Bybit V5
auto-reduces a reduce-only order exceeding the position (never flips; mock caps
at have), so 0.0999 fills 0.0999 flat. F1 entry-quantize rejected (would not have
prevented this); F3 sibling-merge unneeded double-spend risk.
Tests: tests/test_bot_dustfix.py 4 passed (exact-float chain, pre-fix qty-0
reject, no-cause-no-close, F2 accept/fill-flat/no-flip incl. same-minute no-fill).
Soak proof (fixed copy, 5.5h): 0 dust pieces (were 4), 0 protection/exit violations,
4 dust_close @0.1 accepted, 0 errors, all 4 pieces end 0.0, no negative qty.
Evidence: research/diagnostics/bot_dustfix/ (PLAN.md, dust_pieces.csv, SUMMARY.md).
Leader: apply the 12-line F2 hunk to bot/run.py dust fallback; consider the same
max() for market_exit/unprotected_close (F2 backstops them today).
