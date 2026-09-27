# v178 + v179 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v178_v179_audit/` and `tests/test_v178_v179_audit.py`.
Do NOT open v178/ or v179/ until part A is saved (`replication.json`). Base: your v175/v176 audit replications.
A1 (v178): ladder of resting bids at k in (2.5, 3, 3.5, 4) sigma below open(T), minutes 16..238, maker 0.0002 at the
bid on 1m trade-through, taker exit at open(T+4h) with crash-aware slippage, funding; per bar sleeve = sum over assets
and rungs of 0.25/4 * r. Sleeve inside the portfolio vol target as v176 BUT the vol leg uses sleeve_unit shifted by 2
bars (the v176-audit causality fix). Rows: normal costs and stress (books maker 0.0004 / taker 0.0007 + 5 bps on taker
fills; sleeve maker 0.0004, exit taker 0.0007 + 5 bps). For each: monthly, yearly, 4h-close full-path DD, and the
1m-marked full-path DD (books positions and open rungs from their fill minute marked on every 1m close; minute
equity = prev close equity * (1 + R_b(m) + R_s(m) - exec + min(funding, 0))), and the worst bar.
A2 (v179): as A1, but per holding bar the rung fills are taken in order (fill minute, shallower rung, column order
BNB, BTC, ETH, SOL, XRP) while cumulative open notional (rung notional = s*g*0.25/4/1.657) <= 0.05/0.30; later fills
cancelled; the vol leg still uses the uncapped sleeve unit shifted by 2. Same rows and DD measures plus taken/cancelled
rung counts. Save `replication.json`.
B: compare with `v178/v178_result.json`, `v178/v178_diagnostics.json` and `v179/v179_result.json`; check look-ahead in
the budget (only fills known at their minute) and in the 1m mark; write COMPARISON.md. Do not edit leader files.
