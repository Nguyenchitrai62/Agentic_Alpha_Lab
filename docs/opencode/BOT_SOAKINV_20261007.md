# BOT_SOAKINV_20261007: exit-completion invariant (proposal P2 of BOT_EXITSOAK_20261007)
The soak exempted every piece with exit_sent < 2 min old while the exit-cancel bug
(fixed in cb14cb7) re-sent the exit every 2 min: an exiting piece was perpetually
exempt while its stop/TP stayed cancelled. New `check_exit_completion` in
tests/soak_bot.py (wired into `check_invariants`, counted in the soak summary) flags,
per piece with qty > 0: `exit_stuck` (first market_exit older than 3 x
EXIT_INFLIGHT_MIN = 6 min whose exit link neither rests nor filled) and
`exit_resend_overflow` (> 3 exit sends without any fill). Only exchange-ACCEPTED
sends count (a rejected dust place never registers a state link, so the 444
rejected dust_closes in the flush window are not counted); a partial fill counts
as progress; flat pieces prune their history. bot/ stayed READ-ONLY.
6h flush window 16:00-22:00Z 2025-10-10, WITH fix: 0 exit_completion violations
(174 fills; 84 close5_stop sends, 28 filled). Same window PRE-fix
(tmp/run_nofix.py = HEAD~2:bot/run.py, note: also predates 1c0469a): 1428
exit_completion, all exit_stuck, on 28 pieces - the invariant fires as specified.
10h window 12:00-22:00Z (shortest with time_exit 284 + close5 164 sends), WITH fix:
0 exit_stuck; 2092 exit_resend_overflow only - a harness race, not the bug (below).
Residual 444 protection hits in every run: 4 SOL dust pieces (qty 0.0999 < 0.1 lot
minimum, unplaceable protection, rejected dust_close qty 0) - pre-existing dust edge,
out of scope for this invariant.
MINUTE-BOUNDARY VERDICT: harness clock artifact, NOT a bot/paper.py issue. The
`o["t_ms"] < t_ms` rule (bot/paper.py `_minute`, same in the mock) is correct - no
fill in the placement minute, as live. The soak clock DOES advance past the order
minute (170 fills after the 19:00 cancel). The race: soak runs runner.cycle()
BEFORE process_bar, so a market sent exactly on a minute boundary (all time exits:
t_exit is an exact hour) becomes fillable on bar M+1 only after sim passes M+2:00,
but the 2-min resend (inflight age exactly 2.0 -> resend) cancels it in the same
M+2:00 cycle first. Evidence: d0ETH25hgr50Xhgrbo sent 19:00:00, cancelled 19:02:00,
never fillable again; close5 sent off-trigger (condition lapses, no resend) fills
fine. Repro: tmp/repro_minute_boundary.py. Live/paper.py fills markets in < 60 s via
streaming step(), so the resend never triggers there. Proposed HARNESS-ONLY diff
(not applied, bot/ never touched): in run_soak, replay due 1m bars BEFORE
runner.cycle() so cycle N decides on already-filled state, as live.
Fast: tests/test_bot_soakinv.py, 6 tests (5 synthetic incl. rejected-dust +
flat-prune + ledger-fallback, 1 live 1h slice 21:00-22:00Z asserting 0
exit_completion with fills > 0), ~115 s total. Full: `pytest tests -q -k bot` =
239 passed. 6h soak ~15 min (< 20 min budget). Manual long runs:
.venv/Scripts/python.exe research/diagnostics/bot_soakinv/tmp/probe_window.py 6 "2025-10-10 16:00:00+00:00" <tag> (with fix; 10h from 12:00 for both exit types)
.venv/Scripts/python.exe research/diagnostics/bot_soakinv/tmp/probe_nofix.py 6 "2025-10-10 16:00:00+00:00" <tag> (pre-fix proof)
