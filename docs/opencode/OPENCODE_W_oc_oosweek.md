# OpenCode task oc_oosweek - clean forward evidence, week 2 (OOS scorer + paper runners + outage)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_oosweek/` and
`docs/opencode/OOS_WEEK2_20261007.md` (the OOS scorer in step 1 also writes its own outputs in research/diagnostics/oc_bookoos/ by design;
that is allowed). All bot / backend files and artifacts/bot/* are READ-ONLY for you; never start, stop or restart any process.

## Steps
1. Read the docstring of `research/diagnostics/oc_bookoos/score_oos.py`, then run (heavy -> heavy_slot)
   `.venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py --fetch --run`. Before running, copy the existing
   results.json / REPORT.md of oc_bookoos into your folder as `prev_*` so the previous week is kept. Report the new window, daily returns,
   cumulative return, DD and its percentile vs the research bootstrap, exactly as the script prints them.
2. Run read-only status tools and save their outputs (stdout -> files in your folder): `scripts/daily_status.py`, `scripts/bot_health.py`
   (all runners), `scripts/paper_report.py`, `scripts/prospective_scorecard.py` (read each tool's --help first; use only read-only options).
3. Outage note: all seven paper runners (artifacts/bot/paper, paper_d17bf, paper_d13bf, paper_d17bfg2, paper_g2k20, paper_d17bfg2c,
   paper_g2k20c) and the paper_carry loop stopped writing at about 2026-10-07 03:24 UTC and were restarted by the leader at 07:01 UTC
   (state.json backups `state.json.bak_20261007T07*`). From their stdout.log / state files: which 4h cycles were missed, did any open position
   or resting order lose protection during the gap, did the restart adopt the state correctly (look at the first cycle after 07:01)? Also list
   earlier gaps since each runner started.
4. Liquidation / top-of-book collector (`data/raw/liquidations_live`, `data/raw/topbook_live`): coverage since 2026-10-04 = hours with data /
   wall-clock hours, per venue; longest gaps.
5. `docs/opencode/OOS_WEEK2_20261007.md` (Vietnamese, <= 60 lines): tables for (1)-(4), plain verdict "paper vs research: consistent /
   inconsistent / too early", and the list of runner gaps. No recommendations about live money.
