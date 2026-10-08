# OpenCode task ops_reconscript - weekly live-vs-replay reconciliation script (metric H1 of docs/LIVE_RAMP_VI.md)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/paper_recon.py`, `tests/test_paper_recon.py`, and <= 10 appended lines in `docs/LIVE_RAMP_VI.md`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome (tool tasks: a short design note instead). Heavy work via
scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.
artifacts/bot/* and running processes are READ-ONLY.

## Task
Turn the one-off research/diagnostics/oc_paperrecon (read its replay_paper.py and REPORT.md) into a reusable script:
`scripts/paper_recon.py --runner artifacts/bot/paper_<tag> --days 28 [--venue bybit]` that fetches public Bybit linear 1m klines for the
window (cache under artifacts/research/paper_recon/), replays the runner's own placed orders / plans with the engine rules (trade-through
fills, stop-first, gate costs), and prints: paper return vs replay return over common uptime (geometric %/month on 28 days), the divergence
(the H1 halt metric), mismatch classes with counts and P&L impact, and outage / stale-plan gaps excluded. JSON output too. Tests on synthetic
fixtures (no network). Document the weekly command in LIVE_RAMP_VI.md.
