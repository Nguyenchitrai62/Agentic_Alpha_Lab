# v200 + v201 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v200_v201_audit/` and `tests/test_v200_v201_audit.py`.
Use relative paths without quoting. Do NOT open v200/ or v201/ until part A is saved (`replication.json`). Base: your
v199 replication (engine_user conventions after the v188 audit: intrabar peaks, stop wins same-minute ties).
A1 (v200): v197 pipeline with book stop/target (SL, TP) in daily sigma = (2, 4), (2.5, 2.5), (3, 2), plus the reference
(4, 8). Report dev4, 5y, last year, gate DD, book stops/TPs, mean and max gross book exposure (sum |target weight|).
A2 (v201): v197 pipeline plus an hourly ladder: per hour h of the holding bar, base = 1m open of minute 60h, sigma_1h =
std of 1h open-to-open returns (hourly opens = minute 0/60/120/180 opens of every holding bar in time order) over the
1440 hours ending with the last hour of the previous holding bar (min 480); rungs 2.5/3/3.5/4 sigma_1h; bids live minutes
16..57 (h=0) else 60h+4..60h+57; TP L(1+sigma_1h), SL L(1-5 sigma_1h), exits strictly after the fill minute and before
minute 60(h+1), else market at the open of minute 60(h+1) (h=3: next 4h open, funding if settlement). One shared
stop-risk budget over both ladders (rn (5 sigma + 0.02) with each rung's own sigma), fills ordered (minute, ladder 4h
first, rung, asset). Variants: hourly off (must equal v197 5.562/19.72), on with budget 0.12, on with 0.18.
Selections as in the scripts (first four years only). Save `replication.json`.
B: compare with `v200/v200_result.json` and `v201/v201_result.json`. Write COMPARISON.md. Do not edit leader files.
