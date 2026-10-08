# OpenCode task docs_maps20261008 - refresh the frontier map and the hand-off docs with the 2026-10-08 results
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (docs task): you may edit `docs/FRONTIER_MAP_VI.md`, `docs/NEXT_AGENT.md` and
`docs/CONTINUOUS_RESEARCH.md` (add dated sections / rows; do not delete older content except to mark it superseded). Copy every number from
docs/CLOSED_DIRECTIONS.md (rows dated 2026-10-08) and the REPORT.md files they name; no new numbers.

## Content
1. FRONTIER_MAP_VI.md: a new dated table "Bybit + carry (oc_levfrontier)" with all 8 rows (5y, full DD, worst dev year, recent year labelled,
   bootstrap median and P(DD>20)), the Binance C2 / B7 frontier points (oc_c2frontier, oc_cascadeboost, oc_b7c2, oc_b7frontier), and plain
   Vietnamese notes: C2 is a nearly clean timing overlay; B7 is ~70 % extra exposure (oc_cboostctrl) and contaminated; the gross cap 2.0 is what
   keeps B7 inside DD 20; no row reaches 5 %/month in the most recent year on Bybit.
2. NEXT_AGENT.md: current state (deployed G2 + carry paper; 11 paper runners and 3 shadow feeds incl. d17bfg2ch / b7 / b7c2 since 2026-10-08
   04:52 UTC on bot fix 83a466a; restart_all.ps1 covers all), the prospective evaluation schedule (scripts/fm_paper_eval.py --all weekly), the
   OpenCode operating rules learned today (opencode_queue.sh, retry wrapper, snapshot=false, after_jobs, RAM limits), and the open research
   threads (IDEAS8 book batch running; anything still RUNNING in CLOSED_DIRECTIONS).
3. CONTINUOUS_RESEARCH.md: one dated paragraph of lessons (vectorised replica vs engine divergence for exit ideas; exposure controls are
   mandatory for any sizing idea; pre-sample 2017-2020 is the only clean test set left for ideas derived from 2021-2026 results).
