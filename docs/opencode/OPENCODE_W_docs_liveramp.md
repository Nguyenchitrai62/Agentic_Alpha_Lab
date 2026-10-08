# OpenCode task docs_liveramp - IDEAS10 #2: Graduated capital ramp with pre-registered halt rules (paper -> testnet -> live)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/LIVE_RAMP_VI.md` and `research/diagnostics/docs_liveramp/`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome (docs task: a short PLAN section at the top of your folder's notes).
Heavy work via scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
DOCS + ANALYSIS TASK: write docs/LIVE_RAMP_VI.md (Vietnamese, <= 80 lines) and research/diagnostics/docs_liveramp/ (bounds computation). Halt bounds from DEV drawdown statistics only (research/tournament/oc_ddanat4p, oc_underwater, oc_mcdd where available; never the most recent year): size ladder V1 5% -> 25% -> 100% of intended capital at 4 / 8 / 12 weeks with halt if the 4-week live-vs-replay divergence > 0.5 %/month or the sleeve DD at small size exceeds a dev-derived bound; V2 = V1 + strategy-DD halving rule. Include the exact metrics (computed by scripts/fm_paper_eval.py / oc_paperrecon-style replay), who checks what weekly, and the owner actions (keys, testnet first). No live orders, no keys handled.

## Report
Per year table where applicable (dev 2021-2024; post-release year scored ONCE for the dev4 robust pick and REF only, labelled), dev4 robust
pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST, ties -> mean), 5y, full-path DD, the leakage checklist, Vietnamese 3-line verdict.
