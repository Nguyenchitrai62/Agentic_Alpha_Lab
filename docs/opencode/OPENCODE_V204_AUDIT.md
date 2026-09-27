# v204 blind audit (read AGENTS.md (2026-09-27, incl. the robust selection criterion), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v204_audit/` and `tests/test_v204_audit.py`. Use
relative paths without quoting. Do NOT open v204/ until part A is saved (`replication.json`). Base: your v199 replication.
A: v197 pipeline; the rung notional per filled rung = rn * m where m = m_long if the asset's book target weight at the
decision is > 0 else m_other; (m_long, m_other) = (1, 1), (1.5, 0.5), (2, 0) (m = 0 -> the rung is not taken); the
stop-risk budget sums each open rung's own notional * (5 sigma_4h + 0.02). Report dev4, worst first-four-year monthly
return, 5y, last year, gate DD, rungs; selection = robust criterion in AGENTS.md. Save `replication.json`.
B: compare with `v204/v204_result.json`; check the book direction used is known at the decision. Write COMPARISON.md.
Do not edit leader files.
