# v123 + v124 + v125 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v123_v125_audit/` and `tests/test_v123_v125_audit.py`.
Base: your audited v115, v118 and v113_v114 replications. Do NOT open v123/, v124/ or v125/ until part A is saved.
A1 (v123): on the v114 panel add per asset: r4_50/r4_200 = log(close/SMA50|SMA200) on 4h closes; rib4 = +1 if close >
SMA50 > SMA200, -1 if close < SMA50 < SMA200, else 0 (NaN while SMA200 is NaN); from daily closes: w50 = log(close /
SMA350), w50_slope = diff(log SMA350, 5), ribw = +1/-1/0 with SMA350 and SMA1400 (0 while SMA1400 NaN, NaN while SMA350
NaN), joined to 4h bars asof backward on close_time; rib_agree = rib4 + rib + ribw. Retrain v92 LO and v94 LS with these
extra features (all non-target columns), portfolio as v115 primary; secondary v96 blend (0.5 b_lo + 0.5 b94, scale 1).
A2 (v124): v115 books, target 0.15, held weights with band 0.05 applied from the first index row (held = target where
|target - held| > 0.05 per asset); orders = diff of held weights; hidden-year v104 strict 1m fill rule and v104 cost path
(carry, long funding on held weights). Report hidden-year net/DD/maker rate/orders.
A3 (v125): for each book's un-subsampled weight frame (audited formulas without the keep step) take the mean over phase
= 0..5 of (keep rows with position % 6 == phase, ffill, fillna 0); own vol scales on the tranched weights; v115 primary
portfolio. Reference phase 0 only (= v115).
Save `replication.json`, compare with v123/v124/v125 result JSONs (explain IC diff > 0.01, return diff > 1pp, DD diff >
0.5pp), audit the three scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
