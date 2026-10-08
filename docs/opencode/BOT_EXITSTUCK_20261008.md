# BOT_EXITSTUCK 2026-10-08: time-exit markets re-sent for hours, never filling

Cause: cancel-before-fill livelock. Paper/mock fills an order only in a bar
starting after placement (paper.py `_minute`, mock `process_bar`), and the
soak replays bars after the cycle check, so a market needs ~2 min to fill --
exactly EXIT_INFLIGHT_MIN. The runner then re-sent a new X-link and, with
have() polled after the exits loop and the cb14cb7 filter keeping only the
newest exit_link, cancelled the predecessor before its fill bar: every 2 min
for 5 h (soak 3532 exit_resend_overflow; paper d3SOL 27 sends). Size, kline
feed and positionIdx ruled out (reduce-only caps fill sequentially).
The per-cycle dust_skip for the 0.11 ETH piece is its 0.01 float remainder
(0.12-0.11 < 0.01 lot, rounds to 0), not the protected open piece.
Fix (bot/run.py only): poll have() before the exits loop; while the exit_link
still rests log exit_wait and never re-send/cancel (Bybit V5: a market fills
immediately or is rejected -- never cancel one that may be filled); keep all
state-known reduce links of open pieces. Re-send only when the old exit is
gone. paper.py/mock/soak harness untouched. 2 exitsoak tests updated (they
mandated the buggy cancel); 7 new tests in tests/test_bot_exitstuck.py.
Soaks (deployment flags, 4320 x 20 s cycles): flush 2025-10-10: 3532 -> 0
violations, 363 fills, 32/32 exits completed, restart ok, ~949 ms/cycle
(~1048 before); calm 2025-07-05: 0 violations, 85 fills, restart ok.
GO for testnet (exit path strictly safer: no cancel of a live market, no
double-send; reduce-only caps any duplicate). Paper runners: restart after
this fix is deployed (running processes use code on disk only at restart);
no state migration needed (old multi-X resting states are kept, never
cancelled, and fill normally).
Nghien cuu da tim ra vong lap huy-tat-mo-lai market exit moi 2 phut.
Ban sua chi doi, khong huy market dang nghi: soak sach 0 vi pham.
De nghi restart paper runner sau khi deploy de nhan ban sua nay.
