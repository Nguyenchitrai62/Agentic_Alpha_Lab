# v184 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v184_audit/` and `tests/test_v184_audit.py`. Use
relative paths without quoting. Do NOT open v184/ until part A is saved (`replication.json`). Base: your v183 audit
(`v182_v183_audit/`).
A: v183 plus an hourly ladder. For each 4h holding bar T and hour h = 0..3: base = 1m open of minute 60h of T;
sigma_1h = std of 1h open-to-open returns (hourly opens = 1m opens at minutes 0/60/120/180 of every holding bar, in time
order) over the 1440 hours ending with the last hour of the PREVIOUS holding bar (min 480). Rungs k 2.5/3/3.5/4:
L = base (1 - k sigma_1h); live minutes 16..57 for h = 0, else 60h+4 .. 60h+57; fill at L on 1m low < L (maker);
TP = L (1 + sigma_1h), exit at TP in the first minute m > fill and < 60(h+1) with high > TP (maker both sides);
else exit at the open of minute 60(h+1) (h = 3: next 4h open, pays funding at T+4h) by taker with slippage
max(2 bps, 0.25 (high-low)/open of that minute). One shared budget with the v183 4h ladder: all fills of the bar in
(minute, 4h ladder before hourly, rung, asset) order, taken iff (open rungs at that minute + 1) * rn <= 1/6.
Vol leg: unbudgeted sum of both ladders shifted 2 bars. Normal and stress rows: monthly, 4h DD, 1m DD, counts.
Save `replication.json`.
B: compare with `v184/v184_result.json`; check that sigma_1h uses only hours before T; write COMPARISON.md.
Do not edit leader files.
