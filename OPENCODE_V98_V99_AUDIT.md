# v98 + v99 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v98_v99_audit/` and `tests/test_v98_v99_audit.py`.
Base: your audited replications (v92_audit, v93_v94_audit, v95_v96_audit). Do NOT open v98/ or v99/ until A is saved.
A1 (v98): v92 HGB trained with sample_weight = 0.5 ** (age_years / H), age = (training cutoff - row open_time) in
 years of 365.25 days, for H = 2 (primary) and H = 1 (secondary); everything else as v92 (long-only book, causal 20%
 vol target). Report per-anchor IC and yearly normal net/DD for both.
A2 (v99): books = 0.5*W92*s92 + 0.5*W94ls*s94 (your v96 replication). Portfolio: unscaled realised return at t =
 0.8 * sum_i books_{i,t-2}*(open_{i,t}/open_{i,t-1}-1) + 0.6 * carry_{t-1} (carry = column `carry` of
 artifacts/research/carry/carry_oos_fee0.0004.parquet aligned to the 4h index, NaN->0); vol = std over 360 bars
 (min 120) * sqrt(2190); s = min(0.15/vol, 2), NaN->1. Trend weights Wt = 0.8*s*books; net = sum(Wt*fwd) -
 turnover(Wt)*0.0002 - 0.00005*long gross(Wt) + 0.6*s*carry - |diff(0.6*s)|*2*0.0004/1.2. Report yearly normal net/DD.
 Hidden-year execution (2025-09-24..): for every nonzero weight change the order is a limit at the next bar's open;
 filled at that open (maker 0.0002) if a 1m bar within minutes 2..15 trades through it in the order's favour, else
 at the minute-15 open plus 0.0002 adverse slippage with taker 0.0005. Report hidden-year net/DD and maker rate.
Save `replication.json`; compare with v98/v98_result.json and v99/v99_result.json (explain IC diff > 0.01 or return
diff > 1pp), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
