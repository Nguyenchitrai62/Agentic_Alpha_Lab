# v151 + v152 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v151_v152_audit/` and `tests/test_v151_v152_audit.py`.
Base: your v144 replication and your v150 replication (v150_audit; if unfinished, build v150 from OPENCODE_V150_AUDIT.md).
Do NOT open v151/ or v152/ until part A is saved (`replication.json`).
A1 (v151): books = 0.5 * (v144 books) + 0.5 * (v150 books) on the union index (missing -> 0), then the v144 engine (rows
0.15 ungoverned, 0.20 and 0.25 with the 20% governor, 10 bps 1m execution). Report monthly, yearly, full-path DD.
A2 (v152): v144 books and engine but governor g = clip((0.30 - DD)/0.15, 0, 1) and targets 0.30, 0.35, 0.40 (cap 2).
Save `replication.json`, compare with v151/v152 result JSONs (explain return diff > 1pp or DD diff > 0.5pp), audit both
scripts for look-ahead (v152 edits the governor constants via source replacement - verify the executed engine), write
COMPARISON.md. Do not edit leader files.
