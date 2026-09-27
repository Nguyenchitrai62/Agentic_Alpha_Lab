# v198 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v198_audit/` and `tests/test_v198_audit.py`. Use
relative paths without quoting. Do NOT open v198/ until part A is saved (`replication.json`). Base: your v197 replication
(`v197_audit/`) or v193 replication plus the v197 spec (rung size x1.5, stop-risk budget 0.12).
A: TSMOM book T: for each major j and decision t on the 4h opens panel (artifacts/research/engine_real/opens_v154.parquet,
sorted): signal = mean over L in (180, 540, 1080) of sign(open_t / open_{t-L} - 1); vol = std of 42 4h open pct changes *
sqrt(2190); T = clip(signal * 0.20 / vol / 5, -0.5, 0.5), reindexed to the books index (missing -> 0). Pipelines:
v151 = (A+B)/2, 0.75 v151 + 0.25 T, 0.5 v151 + 0.5 T, each with the v197 sleeve under engine_user (book SL/TP m = 4,
10 bps limits resting minutes 2..238). Report dev4, 5y, last year, gate DD, first-four yearly nets; selection = best dev4
with DD <= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v198/v198_result.json`; check TSMOM uses only opens <= t. Write COMPARISON.md. Do not edit leader files.
