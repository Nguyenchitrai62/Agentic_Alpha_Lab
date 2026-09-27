# v177 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v177_audit/` and `tests/test_v177_audit.py`.
Do NOT open v177/ until part A is saved (`replication.json`). Base: your v176 audit replication (if not finished,
the v175 audit replication plus the v176 spec in OPENCODE_V176_AUDIT.md).
A: v176 exactly, except the sleeve keeps only the first 2 limit fills per holding bar: fill minute = first minute
offset in 16..238 (0-based from 16) with 1m low < bid; order fills by (minute, column order BNB, BTC, ETH, SOL, XRP)
and drop fills ranked 3rd or later. k per anchor re-chosen (same grid and window) with the cap applied. Report k,
sleeve alone per anchor, primary monthly/yearly/full-path DD. Save `replication.json`.
B: compare with `v177/v177_result.json`, check that the cap uses only fills known at their minute, write COMPARISON.md.
Do not edit leader files.
