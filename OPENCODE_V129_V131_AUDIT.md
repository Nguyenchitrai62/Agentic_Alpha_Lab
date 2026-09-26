# v129 + v130 + v131 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/` and `tests/test_v129_v131_audit.py`.
Base: your audited v126 (phase runs of the v115 portfolio) and v103_v105 replications. Do NOT open v129/, v130/ or v131/
until part A is saved (`replication.json`). All three report the PHASE MEAN over rebalance phases 0..5 (v126 method).
A1 (v129): per panel (v114 panel with v92 features; v103 panel with v103 features) fv = log(rolling-42 std of diff(log
open)) shifted by -43 (std of returns t+2..t+43); HGB (v92 params) per anchor, cutoff = anchor - 102*4h, rows need
t + 44*4h < cutoff and finite fv; pvol = exp(pred). Replace vol42 by pvol (where available) in the OOS prediction frames
of v92 LO / v94 LS (v114-panel pvol) and v103 LS (v103-panel pvol) before the weight formulas; own vol scales unchanged
in form. Report Spearman(pvol, realized) and Spearman(vol42, realized) per anchor, phase mean with pvol and with vol42.
A2 (v130): per asset join USD-M perp 4h and spot 4h (data/raw/spot_majors_20260925/{SYM}_spot_4h.parquet) on open_time;
share = log(max(spot qv,1)/max(perp qv,1)); sp_share_z = (share - roll180 mean)/roll180 std; sp_share_chg = roll6 mean -
roll42 mean; tbr = clip(taker_buy_qv/max(qv,1),0,1); tbr_gap6/42 = roll6/roll42 mean of (spot tbr - perp tbr); basis =
1e4*log(perp close/spot close); basis6 = roll6 mean; basis_chg = basis6 - roll42 mean; basis_z = (basis6 - roll180
mean)/roll180 std; left-join on (t, sym) to the v103 panel; retrain v103 with them; v115 portfolio phase mean.
A3 (v131): per book strength_t = mean over assets at t of max(pred,0)*(rib != -1) (v92 LO) or |pred| (v94, v103);
k = clip(strength / (rolling-2160-row median shifted 1, min 360 rows), 0.5, 2), NaN -> 1, sampled on the phase's daily
rows and ffilled; book = weights * own vol scale * k; v115 portfolio phase mean.
Save `replication.json`, compare with v129/v130/v131 result JSONs (explain return diff > 1pp, DD diff > 0.5pp, IC or
spearman diff > 0.01), audit the three scripts for look-ahead (especially the fv shift and the strength median), write
COMPARISON.md. Do not edit leader files.
