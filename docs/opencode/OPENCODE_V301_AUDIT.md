# v301 blind audit + G2 robustness (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v301 G2 = v296 J1 (CB books, C4 rules, pooled-experience dip size agent + X4 take-profit agent) with the dip-sleeve risk budget 0.26 (J1 0.18):
5y 6.318, most recent year 5.486, DD 17.52 - the new research best. Write only under `research/parallel/rounds/parallel-20260906-r2/v301_audit/`,
`research/diagnostics/g2_robustness/` and `tests/test_v301_audit.py`; relative paths without quoting; do NOT open v301/v301_result.json or
v301/run.log before `replication.json`.
A: reuse your v296 audit replica of the J1 agents; replicate J1_ref (6.268), G1, G2, G3 (dev4, worst dev year, dev DD, dev win rates), the
stepwise return-first rule exactly as the docstring (pool dev DD <= ref + 0.5, worst >= 3.0, no losing dev year; highest dev4; >= +0.05) and
the final score of G2 only. Confirm the budget is the only change and the risk-budget check still counts every open rung's stop risk.
B: compare with the JSON (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with "## Verdict" PASS/FAIL (feature timing, label windows,
fit windows, fill timing).
C (robustness, after B): research/diagnostics/g2_robustness/ (template research/diagnostics/s1_robustness/) - CB vs G2: base, cost stress,
latency 15 / 30 / 60, band / cool / offset shifts, sleeve budget 0.22 / 0.30, outage (backstop only), bootstrap (P(>=5%/month), P(loss
year), P(DD>20)), 2000-USDT placeability, and executability: G2 with every agent decision taken once at the bar open (state at the close of
minute 0 of the holding bar) and the size-only form (S1 size agent at the bar open, budget 0.26, no TP agent). SUMMARY.md (<= 25 lines)
with a plain verdict: is G2 at least as robust as CB, and which bar-open form keeps more of the edge? Do not edit leader files.
