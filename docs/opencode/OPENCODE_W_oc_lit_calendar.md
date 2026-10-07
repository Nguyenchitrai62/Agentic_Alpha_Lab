# OpenCode task oc_lit_calendar - literature book gates: H1 (turn-of-month risk window), H2 (overnight 21-23 UTC session filter) and H7 (halving-clock regime) - calendar-known gates
Read docs/opencode/OPENCODE_W_COMMON_20261007.md and docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md first (the engine protocol,
controls and selection rule are there). Write ONLY `research/tournament/oc_lit_calendar/` and `tests/test_oc_lit_calendar.py`.
Implement exactly the variants of H1 (turn-of-month risk window), H2 (overnight 21-23 UTC session filter) and H7 (halving-clock regime) - calendar-known gates as written in docs/opencode/IDEAS4_20261007.md section C (data sources, windows, thresholds and
leakage notes listed there are binding; if a listed data source does not cover 2021-09-24 .. 2025-09-23, say so and skip that variant).
Write PLAN.md (variants, controls, fixed settings) BEFORE any engine run.
