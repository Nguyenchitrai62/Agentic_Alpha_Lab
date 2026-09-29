# v269 M1 robustness report (4-sigma candle-close dip stops + 8-sigma native backstop) - bounded task for OpenCode

Leader: Claude Code owns all decisions; you produce ONE diagnostic report (nothing is selected on it). Read AGENTS.md. Write ONLY
`research/diagnostics/m1_robustness/m1_robustness.py`, its `m1_robustness.json`, a `SUMMARY.md` (<= 25 lines) and `tests/test_m1_robustness.py`.
Do not edit any other file.
Copy `research/diagnostics/b1_robustness/b1_robustness.py` (same rows, same bootstrap, same small-account check) and run every row for
(a) O1 B18 and (b) M1 = the same plus `sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0`. The M1 base row must give dev4
6.026, gate DD 18.27, 5y 5.749, most recent year 4.645 (assert). B1-style extra rows for M1: outage_backstop_only (touch stops with
m_sleeve_sl=8.0) and close_1m (close1 + backstop 8, m_sleeve_sl 4). SUMMARY.md: the O1 vs M1 table, bootstrap comparison (P(>=5%/month),
P(loss year), P(DD>20)), small-account placeability at 2000 USDT, and a plain verdict: is M1 at least as robust as O1 (DD <= 20 in more
or equal stress rows)? Run `.venv/Scripts/python.exe -m pytest tests/test_m1_robustness.py -q`. Stop when done.
