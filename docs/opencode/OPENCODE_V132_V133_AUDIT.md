# v132 + v133 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v132_v133_audit/` and `tests/test_v132_v133_audit.py`.
Base: your audited v126/v129_v131 (phase mean, vol forecast) and v127 (tranched deployment) replications. Do NOT open
v132/ or v133/ until part A is saved (`replication.json`).
A1 (v132): universe of 8 traded assets (BTC ETH SOL BNB XRP + DOGEUSDT TRXUSDT ADAUSDT, the new ones from
data/raw/xs_universe_20260924 with no spot prefix, asset ids 5..7 in that order); every place that used 5 assets
(panel build, v92 partial exposure n_active/N, v94/v103 LS active/N, v103 panel) uses the 8 assets; carry unchanged;
v115 portfolio phase mean (v129 method). Report per-asset OOS IC per book and the phase mean.
A2 (v133): v127 tranched books but with vol42 replaced by the v129 forecast pvol (v114-panel pvol for v92 LO / v94 LS,
v103-panel pvol for v103 LS) before the weight formulas; three scenarios (v110 engine, target 0.15) and the hidden year
with the v104 strict fill rule. Report scenarios, full-path DDs, hidden net/DD/maker rate.
Save `replication.json`, compare with v132/v132_result.json and v133/v133_result.json (explain return diff > 1pp, DD diff
> 0.5pp, IC diff > 0.01), audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
