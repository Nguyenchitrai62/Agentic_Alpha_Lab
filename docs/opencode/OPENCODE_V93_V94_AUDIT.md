# v93 + v94 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v93_v94_audit/` and `tests/test_v93_v94_audit.py`.
Base: your audited v92 replication `research/parallel/rounds/parallel-20260906-r2/v92_audit/replicate_5asset_leader_run.py`
(5 assets BTC/ETH/SOL/BNB/XRP, spot prefix for BTC/ETH/BNB/XRP only). Do NOT open v93/ or v94/ until A is saved.
A1 (v94, from spec): three HGB models (same hyperparameters as v92) trained on targets clip(log(open[t+1+h]/open[t+1])
 / (std42 * sqrt(h)), -4, 4) for h = 18, 42, 84 bars; training cutoff = anchor - 4h*(84+60); each model trains on rows
 whose own label is realised before the cutoff; prediction = mean of the three. Weights per asset: long = min(max(p,0)/0.5,1)
 zeroed if daily ribbon == -1; short = min(max(-p,0)/0.5,1) zeroed if ribbon == +1; raw = (long - short)/(std42*sqrt(2190));
 divide by sum|raw| (when > 0) and multiply by min(1, count(raw != 0)/5); daily rebalance (every 6th bar, ffill). Vol
 target and execution exactly as v92 (target 0.20, cap 2, fee 0.0002, long funding 0.00005 per bar on long gross only).
 Report per-anchor IC of the mean prediction vs the 42-bar target and yearly normal net/DD.
A2 (v93, from spec): v92 long-only weights W (your v92 replication) at 70% of capital + carry sleeve 30% x 3 using
 the carry OOS 4h returns file `artifacts/research/carry/carry_oos_fee0.0004.parquet` (column carry; aligned to the
 4h index, NaN->0). Unscaled realised portfolio return at t = 0.7 * sum_i W_{i,t-2}*(open_{i,t}/open_{i,t-1}-1)
 + 0.9 * carry_{t-1}; vol = std over 360 bars (min 120) * sqrt(2190); s = min(0.15/vol, 2), NaN->1. Model net =
 sum(0.7*s*W * fwd return) - turnover(0.7*s*W)*0.0002 - 0.00005*long gross; carry net = 0.9*s*carry - |diff(0.9*s)|*2*0.0004/1.2.
 Report yearly normal net/DD.
Save `replication.json`. B: then compare with v93/v93_result.json and v94/v94_result.json (explain IC diff > 0.01 or
return diff > 1pp) and audit both scripts for look-ahead. Write COMPARISON.md. Do not edit leader files.
