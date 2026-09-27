# v103 + v104 + v105 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/` and `tests/test_v103_v105_audit.py`.
Base: your audited v92 / v93_v94 / v98_v99 / v100_v102 replications. Do NOT open v103/, v104/ or v105/ until part A is
saved (`replication.json`).

A1 (v103): v92 panel (5 majors, spot prefix, v92 features, BTC context) plus flow features per asset from the same 4h
klines, tbr1 = clip(taker_buy_quote_volume / max(quote_volume,1), 0, 1), qv = max(quote_volume, 1):
 tbr_k = rolling-k mean(tbr1) - 0.5 for k = 1, 6, 42; flow_k = rolling-k sum((2*tbr1-1)*qv) / rolling-k sum(qv), k = 6, 42;
 tbr_z = (rolling-6 mean tbr1 - rolling-180 mean tbr1) / rolling-180 std tbr1;
 tsize_z and ntr_z = 180-bar z-scores of log(qv / max(num_trades,1)) and log(max(num_trades,1));
 rng6 = rolling-6 mean log(high/low) / vol42; clv6 = rolling-6 mean((close-low)/(high-low), 0 range -> NaN) - 0.5.
 Targets y6, y18 = clip(log(open[t+1+h]/open[t+1]) / (vol42*sqrt(h)), -4, 4). Embargo 78 bars: cutoff = anchor - 78*4h,
 rows need t + (h+1)*4h < cutoff (per horizon). One HGB per horizon (v92 hyperparameters) on all features (v92 + flow, the
 y columns excluded); prediction = mean of the two. Book = audited v94 weights_ls(shorts=True), v94 vol_target_scale
 (20%, cap 2), v92.simulate. Report per-anchor IC vs y6/y18/y42 and yearly normal net/DD for LS, long-only
 (weights_ls shorts=False) and 0.5*v96 books + 0.5*v103 scaled book (scale 1 for the blend).
A2 (v104): the v99 wrapper (your v99 replication, leader carry convention carry_exp[t]*carry[t]) with books =
 0.5*v96 books + 0.5*(v103 LS weights * v103 vol scale). Report yearly normal/fee/execution net/DD. Hidden-year execution:
 per nonzero weight change at t, T = t+4h; if the T 1m bar is missing -> taker 0.0005 with fill = open*(1 +/-0.0002);
 else p0 = 1m open at T; maker 0.0002 at p0 if any 1m bar with open_time in [T+2m, T+14m] has low < p0 (buy) / high > p0
 (sell); else taker 0.0005 at the T+15m 1m open (p0 if missing) with 0.0002 adverse. Report net/DD/maker rate.
A3 (v105): (i) A1 without the ten flow features (LS book); (ii) the v92 7-day model + long-only book with v92 + flow
 features on the v103 panel, v92 embargo and vol target. Report ICs and yearly normal net/DD.

Save `replication.json`, then compare with v103/v103_result.json, v104/v104_result.json, v105/v105_result.json (explain
IC diff > 0.01 or return diff > 1pp), audit the three scripts for look-ahead (especially flow features and the 1m fill
rule), write COMPARISON.md. Do not edit leader files.
