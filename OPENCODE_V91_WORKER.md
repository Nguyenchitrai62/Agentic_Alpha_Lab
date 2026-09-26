# v91 worker (track C): 3-book portfolio execution audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
You are the WORKER for registry version v91 (round parallel-20260906-r2). Write ONLY under
`research/parallel/rounds/parallel-20260906-r2/v91/` and `tests/test_v91_*.py`. Never edit the registry,
CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, other versions, ../Kronos or git state.
Frozen portfolio: `artifacts/research/advisor_shadow/portfolio_v1.json` (read it) and its advisor
`src/agentic_alpha_lab/signals/portfolio_advisor.py`; OOS program in `research/frontier_combo.py`,
`src/agentic_alpha_lab/oos_streams.py`, `scripts/carry_lab.py` (read, do not edit).
Task: for the hidden year 2025-09-24..2026-09-23 only (parameters frozen as of 2025-09-14: re-run the same
selection code with anchor 2025-09-24, do NOT use portfolio_v1.json params which were fitted to 2026-09):
1. Rebuild the 3-book target weights per 4h bar for BTC/ETH/SOL/BNB/XRP (perp weight, spot weight).
2. Execute every weight change on real 1m bars (`data/raw/btc_intraday_20260924/klines_1m_*`,
   `data/raw/majors_intraday_20260924/{SYM}_1m_*`): limit at the 4h open price, filled only if a later
   1m bar trades THROUGH it within 15 minutes (maker 0.0002), else market at minute 15 open with taker
   0.0005 + 0.0002 slippage. Spot legs same rule on spot 4h opens (`data/raw/spot_majors_20260925`) with
   the fill test on perp 1m bars as proxy (state this). Actual funding on perp legs both signs.
3. Report: vectorized (no-execution-model) result vs execution-realistic result: net %, monthly geometric,
   max DD on 4h marks, fees, funding, turnover, fill-rate; per book contribution.
4. Write `result_manifest.json` in your folder with: experiment_id v91, track C, status "audited",
   parent_commit 1ecf947baddd5ef78444670330e9db62128dad50, scenarios {normal, fee_stress, execution_stress}
   each with monthly_geometric_net_percent, max_drawdown_percent, fills, months; independent_test false;
   live_approved false; audit {passed: false, replay_complete: false, notes: "worker self-report; awaiting leader audit"}.
Tests: causality of weights (prefix invariance) and the fill rule on a synthetic path. Stop when done.
