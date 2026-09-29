# v244 + v247 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v244_v247_audit/` and `tests/test_v244_v247_audit.py`. Use relative paths
without quoting. Do NOT open v244/v244_result.json, v247/v247_result.json or their logs until part A is saved (`replication.json`); read
`v244/v244_cross_venue_flow.py`, `v247/v247_o1_sleeve_budget.py`, `scripts/fetch_bybit_flow.py`, `v236/flow_features.py`.
A: (v244) (1) for 2 random days (BTC, XRP) download the Bybit public trades file (public.bybit.com/trading/<SYM>/<SYM><date>.csv.gz, ONE
request per file, pause between requests - the CDN blocks bursts), rebuild taker orders independently (same timestamp and side) and
aggregate per UTC 4h bar and tier; compare with data/raw/bybitflow_20260929/<SYM>_flow_4h.parquet; check the manifests. (2) truncation
tests on the Bybit and venue-summed flow features. (3) verify one anchor of member_A_Y1_add_bybit against a rebuild; run O1 (5.690), Y1, Y2.
(v247) run the O1 books with sleeve_risk_budget 0.15 (5.690), 0.16, 0.17, 0.18. Report dev4, worst first-four monthly, gate DD; robust
selection per version; most recent year only for each selected row. Save `replication.json`. B: compare with the result JSONs
(return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature timing, label windows, fit
windows and fill timing. Do not edit leader files.
