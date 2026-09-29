# v285 blind audit + D2 robustness report (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v285 D2 (C4 books x 0.8 + 0.2 x the Coinbase-premium member D, annual + quarterly) is the FIRST deterministic configuration that passes the
whole gate (5y 5.725, most recent year 5.167, no losing year, DD 18.39). Audit it with extra care.
Write only under `research/parallel/rounds/parallel-20260906-r2/v285_audit/`, `research/diagnostics/d2c_robustness/` and
`tests/test_v285_audit.py`. Use relative paths without quoting. Do NOT open v285/v285_result.json or its logs until part A is saved
(`replication.json`).
A (audit): read `v285/v285_coinbase_member_c4.py`, `v206/*.py` (how members_quarterly_D was built), `v154` (member D: the Coinbase premium
model set) and the builders it uses. Check member D's LEAKAGE carefully: feature timing of the Coinbase premium (Coinbase and Binance
closes aligned at the bar close, no later bar), the target windows and the fit windows of both D schedules (annual anchors and v202
quarterly, embargo >= horizon), that the cached D files are replayable (rebuild at least one annual and one quarterly anchor and compare);
confirm C4 reproduces 6.026; run D1 / D2; robust selection; most recent year only for the selected row. B: compare with the result JSON;
COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill timing.
C (robustness, after B): copy `research/diagnostics/m1_robustness/m1_robustness.py` and run every row for C4 (M1) and D2 (books = 0.8 C4 +
0.2 (D + Dq)/2, same engine arguments): cost stress, latency 15 / 30 / 60, band / cool / sleeve / offset shifts, bootstrap (P(>=5%/month),
P(loss year), P(DD>20)), 2000-USDT placeability. Write `research/diagnostics/d2c_robustness/d2c_robustness.py`, its json and a SUMMARY.md
(<= 25 lines) with a plain verdict: is D2 at least as robust as C4? Do not edit leader files.
