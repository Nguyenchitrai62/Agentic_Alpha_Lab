# v95 + v96 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v95_v96_audit/` and `tests/test_v95_v96_audit.py`.
Base: your audited replications `v92_audit/replicate_5asset_leader_run.py` and `v93_v94_audit/replicate_v93_v94.py`.
Do NOT open v95/ or v96/ until A is saved.
A1 (v96): combined weights = 0.5 * W_v92 * s_v92 + 0.5 * W_v94_longshort * s_v94 (each book's own causal 20% vol
 target, cap 2, NaN->1), simulated with v92 execution/costs (fee 0.0002, long funding 0.00005/bar on long gross).
 Report yearly normal net/DD.
A2 (v95): to the v92 feature panel add (i) at each bar across the five majors: pct-rank of ret42, ret180, snr42;
 ret42 - BTC ret42; share of majors with daily ribbon == +1; mean snr42; (ii) per asset f7 z-score vs trailing
 180-day (min 30-day) mean/std of f7; (iii) market context from
 `agentic_alpha_lab.patterns.{breadth,positioning,macro,implied_vol}.compute(load_bars("4h", include_opened_year=True))`
 prefixed `ctx_`, keeping columns with > 20% non-NaN, merged on 4h open_time. Train the v92 HGB on all features;
 report per-anchor IC and yearly normal net/DD of the v92 long-only book. Also check whether the context features
 are causal at the bar close (reuse assert_causal on a 3000-bar slice).
Save `replication.json`; then compare with v95/v95_result.json and v96/v96_result.json (explain IC diff > 0.01 or
return diff > 1pp), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
