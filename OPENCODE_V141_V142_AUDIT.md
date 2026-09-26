# v141 + v142 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v141_v142_audit/` and `tests/test_v141_v142_audit.py`.
Base: your audited v133, v135 (1m bar stats, 10 bps rule), v110 (governor) replications. Do NOT open v141/ or v142/ until
part A is saved (`replication.json`).
A1 (v141): v133 books; sequential loop over the 4h index; live = [2021-09-24, +1825 days); s = min(target/vol, 2), NaN vol ->
s = 1; governor (targets 0.20, 0.25): g_i = clip((0.20 - (1 - E_{i-2}/max E over the 540 bars ending at i-2))/0.10, 0, 1),
g = 1 for i < 2 and for the ungoverned 0.15 row; w = 0.8*s*books*g (0 outside live), c = 0.6*s*g (0 outside live);
dw = w - w_prev; per asset: buys use fee 0.0002 & rel -0.0010 if the bar's minutes 2..14 low < p0*(1-0.0010) else fee 0.0005
& rel p15/p0-1+0.0002; sells symmetric with high > p0*(1+0.0010), rel +0.0010 or p15/p0-1-0.0002; missing p0 -> taker with
rel +/-0.0002; cost = sum(|dw|*fee + dw*rel); net = sum(w*(open[t+2]/open[t+1]-1)) - cost - 0.00005*sum(max(w,0)) +
c*carry - |c - c_prev|*2*0.0004/1.2; E_i = E_{i-1}(1+net_i). Report monthly, yearly (with mean g), full-path DD per row.
A2 (v142): add per bar t: xs_c = c - mean_t(c), xr_c = percentile rank of c among majors at t (pandas rank(pct=True)), for
c in ret42 ret180 snr42 snr180 d50 d200 vol_ratio volz f7 on the v114 panel (v92/v94 models use all columns) and additionally
tbr_6 flow_42 tbr_z on the v103 panel; vol forecasts use the original feature sets; v133 pipeline otherwise.
Save `replication.json`, compare with v141/v142 result JSONs (explain IC diff > 0.01, return diff > 1pp, DD diff > 0.5pp),
audit both scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
