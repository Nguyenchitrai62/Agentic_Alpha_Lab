# OpenCode task ops_weeklyreport - one-command weekly owner report (health + prospective comparison + reconciliation + DD vs halt bounds)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/weekly_report.py`, `tests/test_weekly_report.py` and `docs/weekly/README.md`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Task
Write `scripts/weekly_report.py [--out docs/weekly/YYYY-MM-DD_VI.md]` that collects, read-only: bot_health for every runner, backend /health
and plan age, scripts/fm_paper_eval.py --all (import, do not shell out if avoidable), scripts/paper_recon.py if present (skip gracefully if
not), carry ledger status, each runner's equity / 28-day DD / 90-day DD versus the LIVE_RAMP bounds (H2 17 %, V2 19 %), feed freshness
(kronos / chronos / cascade shadow parquet lag), and writes a short Vietnamese markdown report (<= 60 lines) with a clear HALT / OK line per
runner. Tests on synthetic fixtures. README: how the owner runs it every Sunday.
