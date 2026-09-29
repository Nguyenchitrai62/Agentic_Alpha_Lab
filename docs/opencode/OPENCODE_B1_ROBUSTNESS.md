# v266 B1 robustness report (candidate: 5m-close dip stops + 8-sigma native backstop) - bounded task for OpenCode

Leader: Claude Code owns all decisions; you produce ONE diagnostic report (nothing is selected on it). Read AGENTS.md. Write ONLY
`research/diagnostics/b1_robustness/b1_robustness.py`, its `b1_robustness.json`, a `SUMMARY.md` (<= 25 lines) and `tests/test_b1_robustness.py`.
Do not edit any other file.

Copy `research/diagnostics/o1_robustness/o1_robustness.py` (same rows, same bootstrap, same small-account check) and run every row twice:
(a) the deployed O1 B18 (as in that script) and (b) the candidate B1 = the same plus `sleeve_stop_mode="close5", sleeve_backstop=8.0` in the
engine call. The B1 base row must give dev4 6.13, gate DD 19.70, 5y 5.795, most recent year 4.464 (assert).
Extra rows for B1 only:
  outage_backstop_only   the bot is down: the close stop never fires, only the native 8-sigma touch stop protects the rung
                         (engine: sleeve_stop_mode="touch" with m_sleeve_sl=8.0 for the sleeve)
  close_1m               sleeve_stop_mode="close1" with the 8-sigma backstop (a bot watching 1m closes)
  latency_close_plus5    close5 trigger but the market exit fills 5 minutes later (approximate: use the close of minute k+5 as the fill
                         if you can implement it without editing the engine; otherwise skip and say so)
Report per row: dev4, every walk-forward year (net %, 1m DD), 5y, most recent year, gate DD, losing years, trade win rate. SUMMARY.md: the
side-by-side table (O1 vs B1), the bootstrap comparison, and a plain verdict: is B1 at least as robust as O1 under cost stress, latency and
a bot outage? Run `.venv/Scripts/python.exe -m pytest tests/test_b1_robustness.py -q`. Stop when done.
