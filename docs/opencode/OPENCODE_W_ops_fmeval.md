# OpenCode task ops_fmeval - weekly prospective evaluation of the K2 and C2 paper runners (one script, both tilts)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/fm_paper_eval.py`, `tests/test_fm_paper_eval.py`, and append a
section to `docs/BOT_RUNBOOK_VI.md` (Vietnamese, <= 15 lines). artifacts/* READ-ONLY. Do not touch running processes.

## Task
Generalise scripts/k2_paper_eval.py (read it fully) into scripts/fm_paper_eval.py --feed {kronos, chronos} that, for the matching runner
(paper_d17bfg2k2 / paper_d17bfg2ch, feeds artifacts/research/kronos_shadow / chronos_shadow) and its twin paper_d17bfg2 (no tilt):
(1) realised prospective comparison runner vs twin (return, DD, dip fills, win rate) over common uptime only; (2) the counterfactual on the
twin's own dip fills: sum(mult x rung P&L) / mean(mult) vs sum(rung P&L), using only rows with mode prospective/late and is_prospective;
(3) a bootstrap CI over weeks; (4) data-quality counters (missing feed rows, k2_missing ops, outage gaps, stale_plan periods). Output JSON +
a short text summary. Tests on synthetic fixtures. Keep scripts/k2_paper_eval.py working (do not delete or change its CLI).
