# v153 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v153_audit/` and `tests/test_v153_audit.py`.
Base: your v144, v150 (WITH the v142 xs/xr features: the options columns are joined before the v142 xs step, and only the
options columns themselves have no xs versions) and v139 replications. Do NOT open v153/ until part A is saved.
A: A = v144 books; B = v144 builder with the five options-flow columns merged on t into the v114 and v103 panels before the
xs step (vol models exclude them); C = v144 builder with the eight v139 positioning columns merged into the v103 panel only
(vol models exclude them). Books = (A + B + C)/3 on the union index; v144 engine rows (0.15 ungoverned, 0.20/0.25 governed,
10 bps 1m execution). Report monthly, yearly and full-path DD.
Save `replication.json`, compare with v153/v153_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v153_three_info_ensemble.py for look-ahead, write COMPARISON.md. Do not edit leader files.
