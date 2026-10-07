# OpenCode task audit_k2 - BLIND replication of the Kronos K2 dip tilt on G2 (engine part; features given)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_k2/` and `tests/test_audit_k2.py`.
Print progress every 10 minutes. Engine via heavy_slot.

## Blind protocol
1. Read ONLY: docs/opencode/OPENCODE_W_oc_kronoshidden.md (the spec), research/tournament/kronos/PLAN.md (rule V1 definition),
   research/tournament/oc_kronoshidden/PLAN.md. Inputs you may use as GIVEN data (do not re-run Kronos): research/tournament/oc_kronoshidden/
   kronos_features_4shift.parquet. Do NOT open oc_kronoshidden's code (tilt_rule.py, run_engine.py), fits.json, ctrl.json, results.json,
   REPORT.md or tmp/, nor oc_k2placebo / oc_k2bybit.
2. Implement independently: per anchor A (2021..2025-09-24) fit on TRAINING rows = majors rows of research/tournament/harness.py load() with
   t_exit < A - 7 d joined to shift-0 low1 on (sym, T): direction = sign of Spearman(-low1, y_dep), edges q20 / q80 of -low1; K2 multiplier
   1.25 in the favourable outer quintile, 0.75 in the unfavourable, 1 else, missing -> 1; the anchor's fit applies to all four shifts in
   year A, each shift using its own rows. Apply it on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0) with the per-(coin, bar)
   dip-size multiplier mechanism of research/parallel/rounds/parallel-20260906-r2/v414/v414_dvol_tilt.py; reproduce G2 5.41 / 16.91 / 16.82
   first. Score dev4, the post-release year and the 5y path (4-phase reset metric, full-path DD).
3. SAVE part A `replication.json` (per-anchor direction / q20 / q80, per-year R / DD, dev4, Y4, 5y, full-path DD) BEFORE opening any
   oc_kronoshidden output. Then compare (R > 0.10 pp, DD > 0.5 pp, fit parameters > 1e-6 relative) and audit their code for look-ahead
   (feature timing per shift, training-row cut, the shift / phase mapping, multiplier application point), each with a test.
COMPARISON.md: PASS / FAIL / PASS-WITH-NOTES. Vietnamese 3 lines.
