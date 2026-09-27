# v179 budget re-audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v179_reaudit/` and `tests/test_v179_reaudit.py`.
Reuse your `v178_v179_audit/` replication. The previous audit read the budget as per-asset 0.05 + total 0.30; the
leader's rule is different and is stated here precisely: there is ONE cap, on the TOTAL open sleeve notional of the
bar across all assets and rungs: N_MAX = 0.05 / 0.30 = 0.1666667 (a fraction, i.e. one sixth of equity). There is NO
per-asset cap. Rung notional rn = s[i] * g[i] * (0.25 / 4) / 1.657. Fills of the bar are sorted by (fill minute, rung
index 0..3 for k 2.5/3/3.5/4, asset column index BNB, BTC, ETH, SOL, XRP) and taken while used + rn <= N_MAX + 1e-12
(whole rungs; a rejected rung does not stop later smaller... all rungs of a bar have the same rn, so the first rejection
ends the bar). Report normal and stress rows (monthly, 4h DD, 1m-marked DD, taken/cancelled) and compare with
`v179/v179_result.json` (4.141 / 18.24 / 19.81, 2055 taken / 3129 cancelled). Write COMPARISON.md with a verdict.
Do not edit leader files.
