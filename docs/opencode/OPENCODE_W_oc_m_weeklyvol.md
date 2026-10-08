# OpenCode task oc_m_weeklyvol - IDEAS9 #5 (MANUAL product): Weekly-frozen vol distance table
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_m_weeklyvol/` and `tests/test_oc_m_weeklyvol.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine via scripts/heavy_slot.py (RAM tight: one job at a time).
Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
Implement idea #5 of docs/opencode/IDEAS9_20261008.md EXACTLY as written (rule, the two pre-registered variants, Bybit order types, leakage
notes) in the MANUAL 4-phase harness of research/tournament/oc_k2manual / oc_c2manual with the M5_human schedule (15-minute reaction, night bar
skipped) - reproduce M5_human 3.728 / 17.94 / 17.79 bit-exact first. Everything not named by the idea stays exactly M5_human.

## Report
Rows M5_human, V1, V2: dev4 per year / mean / WORST / DD / full-path DD / win rates (book and all), robust pick on dev4 ONLY (DD <= 20, no losing
year, prefer mean >= 5, highest WORST, ties -> mean), post-release year scored ONCE for the pick and M5_human (labelled), 5y. How much of the
MANUAL gap to 5 %/month (1.272 pp on 5y) does it close? Vietnamese 3-line verdict.
