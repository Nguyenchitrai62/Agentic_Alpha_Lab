# BOT_EXITSOAK_20261007: regression soak for bot-side market exits

## Baseline note (deviation from the assignment text, disclosed)
The assignment assumed the leader fix was uncommitted and `git show HEAD:bot/run.py`
lacked it. In fact the fix is already committed as cb14cb7 ("bot: never cancel a
confirmed market exit of an open piece"). `git diff HEAD` is empty, so the without-fix
baseline used here is `research/diagnostics/bot_exitsoak/tmp/run_nofix.py`, byte-exact
`git show HEAD~1:bot/run.py` (0 `exit_cancel` refs). The HEAD~1->HEAD diff on
`bot/run.py` is purely additive (the `_acts_without_exit_cancel` function + 2 call
sites), therefore the current tree with that filter patched to identity is
behaviour-identical to the copy; `test_identity_patch_matches_nofix_module` locks this
equivalence. Pre-registered plan: `research/diagnostics/bot_exitsoak/PLAN.md` (written
before any outcome); machine-readable outcomes: `research/diagnostics/bot_exitsoak/results.json`.

## What was tested
Deterministic soak in `tests/test_bot_exitsoak.py` (10 tests, all pass on the current
tree) over an in-process exchange implementing the `bot/paper.py` matching rules
(markets fill at the next 1m bar open, limits only on strict trade-through after the
placement minute, conditional stops with stop-first, reduce-only capped at the
position, PostOnly cross rejected). One runner drives the full `Runner.cycle()` on
both drivers (current tree = WITH fix, tmp copy = WITHOUT). Forced scenarios:
(a) 2 dip pieces past 4h `t_exit`; (b) 1 dip piece with scripted 5m close 74800 <=
`stop5` 74880 (close time after `opened`); (c) 1 book piece with (phase, symbol)
absent from the plan and `plan_gone_since` 10 min old (> GRACE 3 min);
(d) runner rebuilt from persisted `state.json` + same exchange between exit send and
fill; (e) exchange reports a half fill of the market exit. Live-review probes: stale
exit (accepted, then lost, never fills), re-send replacing a still-resting exit, and
two resting reduce-only markets filling in one bar.

## Results table

| scenario | WITH fix (current tree) | WITHOUT fix (tmp copy) |
|---|---|---|
| (a) time exit x2 | both complete, send cycle + 1 fill-sync cycle (<= 2) | sent then cancelled same cycle, never fills, pieces stay open |
| (b) close5 stop | completes in <= 2 cycles (`dip_cool` path intact) | cancelled same cycle, never completes |
| (c) book divergence | completes in <= 2 cycles | cancelled same cycle, never completes |
| protection bound | 0 snapshots with an open piece lacking both S/T and a resting exit | all 3 pieces BARE (no S/T, no resting exit) indefinitely |
| (d) restart | exit survives restart, no duplicate send, completes next bar | exit already gone pre-restart; piece stays open |
| (e) partial fill | remainder survives, no re-send, completes; filled == qty exactly | n/a (exit never lives to be filled) |
| stale exit re-send | re-sends after EXIT_INFLIGHT_MIN; replaced old link cancelled by diff | n/a |
| double market, one bar | position floors at 0, total filled == piece qty (cap holds) | n/a |
| equivalence | identity-patched tree == tmp copy (cancel/place sets match) | — |

## Why the existing soaks missed it
1. `tests/soak_bot.py` runs 24h but its invariant checker (`check_invariants`) skips
   every piece with `exit_sent` < 2 min old, and the bug re-sends the exit every
   2 min — an exiting piece is perpetually "in flight" and therefore perpetually
   exempt, while S/T stay cancelled. No assertion on exit *completion* exists anywhere
   in the soak.
2. The pytest 2h smoke (`test_bot_soak_smoke.py`) cannot produce a time exit by
   construction (`t_exit` = bar + 4h > 2h window), and its 00:00-02:00 UTC slice of
   2025-10-10 precedes the ~21:19 flush, so no close5 either.
3. All `FakeExchange`-based runner unit tests (`test_bot_resilience.py` etc.) stub
   `klines() -> []` (no 5m signal, hence no close5), pin `t_exit` into the future, and
   never fill a Market order (`place` only rests). They assert single-cycle
   "protected-or-closing" (`test_1`, `test_6`), which the buggy cycle satisfies at send
   time — the same-cycle cancel lands after the assertion point.
4. Mechanism (verified): pre-1c0469a only `exit_sent` was stored, so `have()` never
   listed the exit. 1c0469a added `pc["exit_link"]` + `state["links"][link]`, after
   which `have()` lists the still-open market order while `desired()` (correctly)
   emits no S/T for the in-flight piece — `mirror.diff` then cancels the exit itself.

## New bugs found
None blocking. One non-blocking observation (verified by
`test_resend_replaces_stale_resting_exit`): on re-send the replaced old link is
cancelled by `diff` only because `keep` tracks the *latest* `exit_link`. Link ids
embed `t36(now-minute)`, so a re-send >= 2 min later never collides with the old id
in production (the in-test collision from backdating within one wall minute was
worked around by renaming). Closed pieces (`qty` 0) are already excluded from `keep`,
so no stale link can suppress a cancel forever.

## Proposed diffs (bot/ untouched; for the leader to apply)
```diff
# P1 (hygiene): clear exit markers once a piece is flat, in Runner.sync_fills,
# right after apply_fill reduces qty to 0:
+                if float(pc.get("qty", 0.0) or 0.0) <= 0:
+                    pc.pop("exit_sent", None)
+                    pc.pop("exit_link", None)
# Rationale: nothing reads them for flat pieces today (keep-set already excludes
# qty 0), but lingering markers confuse restart audits and the next adopt-fresh.
# P2 (soak gap that hid this bug): in tests/soak_bot.py check_invariants, track
# market_exit sends and flag a piece with exit_sent older than 3 x
# EXIT_INFLIGHT_MIN whose qty is still > 0 and whose exit link no longer rests
# (exit neither filled nor resting = the exact signature of this bug).
# P3 (optional hardening, live only): on re-send, the old link is cancelled by
# diff in the same cycle, but cancel-then-fill races a bar boundary; consider
# reusing one link id per (piece, exit-attempt-minute) is already the case --
# no change needed unless a double-rest is ever observed on testnet.
```

## Verdict for testnet readiness
GO for testnet (exits complete, no double-spend, stale exits self-heal via re-send +
reduce-only cap), with P1+P2 recommended before live scale. The paper runners'
20-24 unprotected pieces symptom is explained and covered by regression tests that
fail without the fix and pass with it.
