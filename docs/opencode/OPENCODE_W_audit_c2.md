# OpenCode task audit_c2 - BLIND audit of the Chronos C2 result (independent re-implementation) + pretraining-contamination check
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/audit_c2/` and `tests/test_audit_c2.py`.
Print progress every 10 minutes. Engine via heavy_slot (one job at a time; RAM is tight).

## Blind rule
Read research/tournament/oc_chronos/PLAN.md (the frozen spec) and the INPUT files only. Do NOT read oc_chronos's REPORT.md, results.json or
its scripts until your own numbers are written to audit_c2/replication.json (then compare in COMPARISON.md). Model the audit on
research/tournament/audit_k2 (read its PLAN.md / REPORT.md for the format; not its numbers).

## Tasks
1. Re-derive the per-anchor C2 fits from chronos_features_4shift.parquet + research/tournament/harness.py on your own (t_exit < A - 7 d,
   shift-0 join on (sym, T), Spearman sign, q20 / q80) and re-implement the multiplier assignment; re-run REF and C2 in the engine (4-phase,
   G2) for dev4 and the post-release year. Compare to oc_chronos: fits, multiplier vectors, yearly %/month, DD, full-path DD.
2. Leakage checklist (explicit, with code citations): feature timing (recompute 200 random rows of ch_q10 from bars with every bar after the
   context deleted - must match), label windows, fit windows, fill timing; check no statistic from a test year feeds a choice.
3. Contamination: from the Chronos-Bolt model card / the chronos-forecasting package docs (HF cache README, pylib metadata) and the Chronos
   paper's training-corpus list, state whether ANY crypto or exchange-price series is in the pretraining data, and what that means for the
   dev4 years 2021-2024.
Verdict: PASS / PASS-WITH-NOTES / FAIL, Vietnamese 3 lines.
