# v275 + v276 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v275_v276_audit/` and `tests/test_v275_v276_audit.py`. Use relative paths
without quoting. Do NOT open v275/v276 result JSONs or logs until part A is saved (`replication.json`). Read `v275/v275_hourly_close_stops.py`
(hourly=True ladder with the candle-close stop rules; check that hourly rungs rest minutes 4..57 of each hour, use sigma_1h known before the
holding bar, and exit by TP / close stop / backstop / the hour's end) and `v276/v276_rung_size_close4.py` (size_mult 2.0 / 2.25), both on
v269 M1 (reference dev4 6.026). Report dev4, worst first-four monthly, gate DD, rung counts; robust selection; most recent year only for
each selected row. Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly
checking fill / exit timing. Both ran after their pre-registration commits (41363a7, the v276 commit) but before the registry rotation -
confirm the committed scripts equal the run scripts. Do not edit leader files.
