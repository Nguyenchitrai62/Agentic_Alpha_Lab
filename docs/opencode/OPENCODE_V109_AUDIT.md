# v109 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v109_audit/` and `tests/test_v109_audit.py`.
Base: your audited v103_v105 replication of v104 (books b_lo = v92 LO weights * v92 vol scale, b94 = v94 LS * v94 scale,
b103 = v103 LS * own scale; v104 wrapper). Do NOT open v109/ until part A is saved (`replication.json`).

A: For each book's OOS predictions (v92: label y, h=42; v94 ensemble: label y42, h=42; v103: label y6, h=6) and each
daily decision bar tau (every 6th row of the union 4h index of the three weight frames), IC_tau = Spearman(pred,
label) pooled over rows with t >= tau - 60 days and t + (h+1)*4h <= tau (rows with NaN pred/label dropped). m_tau =
clip(IC_tau/0.10, 0, 1.5); m = 1 if fewer than 200 rows or IC not finite; forward-fill to 4h bars. Primary: v104
wrapper where the portfolio scale s is computed exactly as v104 from the UNGATED books (0.25 b_lo + 0.25 b94 + 0.5 b103
plus carry) and Wt = 0.8 * s * (0.25 b_lo m_lo + 0.25 b94 m94 + 0.5 b103 m103); carry exposure 0.6*s (ungated); net as
v104. Report mean gates per anchor year and yearly normal/fee/execution net/DD for gated and ungated. Secondary: v92
book alone with scale = v92 vol scale * m_lo through v92.simulate.

Save `replication.json`, compare with v109/v109_result.json (explain gate mean diff > 0.02, return diff > 1pp), audit
v109_ic_gate.py for look-ahead (especially label realization timing in the gate), write COMPARISON.md. Do not edit
leader files.
