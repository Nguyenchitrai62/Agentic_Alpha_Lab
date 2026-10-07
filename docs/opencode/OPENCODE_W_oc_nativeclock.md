# OpenCode task oc_nativeclock - give the three shifted clocks their OWN fresh book signals instead of a forward-filled standard-grid book
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_nativeclock/` and `tests/test_oc_nativeclock.py`.
Print progress at least every 10 minutes. Engine runs via heavy_slot.

## Why
In the deployed 4-clock G2 (v376 harness, v421 run), the book target rows exist only on the STANDARD 4h grid (00/04/.. UTC); clocks shifted
by 1/2/3 h use the latest standard-grid row forward-filled (research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py docstring:
"before the shifted-clock forward fill"). So clocks 1-3 trade a book signal that is 1-3 h stale. oc_bookattrib showed the book's return is
TIMING; fresher signals may add timing value (or just add turnover). Never tested.

## Rule (fixed)
- NATIVE: for each shift s in {1, 2, 3}, compute the book members' predictions on that clock's own 4h bars (bars opening at s, s+4, ...;
  features recomputed from the 1m stores on the shifted grid with the SAME feature code; the frozen per-anchor member models are applied
  unchanged - no retraining), then build the blended book rows exactly as research_books_d2 does, apply the same bear filter, and feed them
  to phase s instead of the forward-filled standard rows. Phase 0 unchanged. Everything else = G2 (v421 RUNS rule inv, k 1.0, kd 1.7, bear
  True, G 2.0). Reproduce G2 5.41 / 16.91 / 16.82 first (with the forward-filled books).
- If a member's features cannot be computed on a shifted grid from the available stores (e.g. a member uses daily inputs), keep that member
  forward-filled and list it.
Score dev4 (4-phase reset metric, yearly DD, full-path DD, book turnover / fees per year) and the most recent year once. Also a per-phase table
(phase 0 must be unchanged). Verdict: does NATIVE beat G2 on dev4 mean AND worst year with DD <= G2 + 0.5 (then it becomes a registered
candidate)? Vietnamese 3 lines.
