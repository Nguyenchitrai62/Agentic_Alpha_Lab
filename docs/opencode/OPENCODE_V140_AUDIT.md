# v140 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v140_audit/` and `tests/test_v140_audit.py`.
Base: your audited v132_v133 replication (v133 configuration). Do NOT open v140/ until part A is saved.
A: per asset (time order) r[k] = log(open[k]/open[k-1]); for horizon h: R = log(open[t+1+h]/open[t+1]); fv = rolling-h std
of r shifted by -(h+1) (= std of r[t+2..t+1+h]); s_h = clip(R/(fv*sqrt(h)), -4, 4), non-finite -> NaN. Targets: v92 model
on s42 (features = v92 features, v92 cutoff/embargo, rows need s42 and t + 43*4h < cutoff); v94 on s18/s42/s84 (v94
features = all non-target columns excluding y* and s<digits>, v94 embargo); v103 on s6/s18 (v103 features, embargo 78).
HGB v92 params; v94/v103 predictions = mean over horizons; then the v133 pipeline (pvol swap with the v129 vol models,
tranching, portfolio 0.15). Report v92 IC vs s42 and vs y per anchor and three scenarios with full-path DD.
Save `replication.json`, compare with v140/v140_result.json (explain IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp),
audit v140_forward_sharpe_target.py for look-ahead (target timing!), write COMPARISON.md. Do not edit leader files.
