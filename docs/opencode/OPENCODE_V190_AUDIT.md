# v190 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v190_audit/` and `tests/test_v190_audit.py`. Use
relative paths without quoting. Do NOT open v190/ until part A is saved (`replication.json`).
A: v103 panel p103 (from v144 `books_v142()`), features f103 = columns except y*, t, open, sym, bar. Labels per (t, sym)
from the asset's 4h bars (`v92.load_asset` as used by the panel): entry = open(t+1); sigma_d = std(360 4h open pct
changes ending at t, min 120) * sqrt(6); long: SL = e(1 - 4 sd), TP = e(1 + 8 sd), scan bars t+1..t+42 (low <= SL
first, else high >= TP; SL first if both in one bar), else exit open(t+43); ret - 0.00075 - 0.0001 * bars_held/2;
short mirrored (no funding); target = ret / sd clipped [-4, 8]. HGB(max_depth 4, lr 0.03, 400 iters, min_samples_leaf 300,
l2 1, random_state 0) per anchor and side on rows with t + 43 bars < anchor - 78 bars; pred = p_long - p_short on the
anchor year. Book E = v125.phased(v125.raw_ls(frame), 6 phases) with the v129 vol forecast replacing vol42, times
ext.v94.vol_target_scale. Rows under engine_user (SL/TP m = 4, sleeve): v151 = (A+B)/2 members, E alone, 0.5 v151 + 0.5 E.
Report IC per anchor, monthly_dev4, 5y, DD. Save `replication.json`.
B: compare with `v190/v190_result.json`; check label leakage (labels use future bars only as targets; the training
filter guarantees label completion before anchor - embargo; sigma uses bars <= t). Write COMPARISON.md.
Do not edit leader files.
