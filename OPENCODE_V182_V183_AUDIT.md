# v182 + v183 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v182_v183_audit/` and `tests/test_v182_v183_audit.py`.
Do NOT open v182/ or v183/ until part A is saved (`replication.json`). Base: your v179 re-audit (`v179_reaudit/`, total-
only cap 1/6) and v180 audit (`v180_audit/`, minute f-1 gate features).
A1 (v182): candidates = ladder rung fills (k 2.5/3/3.5/4) of 11 assets: the five majors and DOGE/ADA/LINK/LTC/AVAX/TRX
(1m data in data/raw/alts_intraday_20260926; 4h opens/funding from xs_universe). Target = normal-cost net rung return.
Features at minute f-1 exactly as v180 EXCEPT: no asset code; breadth = number of the FIVE MAJORS with (close/open(T)-1)
/sigma <= -2 at minute f-1 (same for every candidate, including the candidate itself if it is a major); btc_depth =
BTC's depth at f-1. HGB (max_depth 3, lr 0.03, 300 iters, min_samples_leaf 50, l2 1.0, random_state 0) per anchor on
pooled candidates with T + 4h < anchor - 1 d and T >= 2020-03-02; majors' test rungs live iff pred > 0; then the v179
loop (total cap 1/6), normal and stress rows. Report IC on majors' test fills, kept, monthly, 4h and 1m DD.
A2 (v183): ladder as v179 but after a fill at minute f a take-profit sell rests at TP = L (1 + sigma); exit at TP in the
first minute m > f with 1m high > TP (maker fee both sides, no funding); else the usual next-4h-open taker exit. Budget:
fills in (minute, rung, asset) order; take a fill iff (number of taken rungs of this bar still open at that minute, i.e.
exit minute > fill minute, + 1) * rn <= 1/6; rn = s*g*0.25/4/1.657. 1m mark: rung marked from fill minute to exit minute,
locked after. Normal and stress rows: monthly, 4h DD, 1m DD, worst bar, taken, TP exits. Save `replication.json`.
B: compare with `v182/v182_result.json` and `v183/v183_result.json`; check look-ahead (TP only after the fill minute;
budget uses only exits already happened); write COMPARISON.md. Do not edit leader files.
