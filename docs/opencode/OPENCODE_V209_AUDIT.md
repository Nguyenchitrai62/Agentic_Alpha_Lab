# v209 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v209_audit/` and `tests/test_v209_audit.py`. Use
relative paths without quoting. Do NOT open v209/ until part A is saved (`replication.json`). Base: your v205/v208 replications.

A1 discrete trades (engine_user exec_policy and fixed_levels hooks; books and every other setting = v205). A book order
exists exactly when the engine already sends one. Policy per asset and bar (w = current drifted weight, tgt = target):
- if |w| < 0.012: open to tgt with a limit (open -/+ 0.10%) when |tgt| >= T_open, else skip;
- else if sign(tgt) != sign(w) and |tgt| >= T_open: flip to tgt (same limit);
- else (D1, D3 only) if |tgt| < 0.01: close to weight 0 (same limit);
- else skip (no adds, no trims).
With fixed_levels SL/TP use sigma_d of the bar the position was opened (or flipped). D1: T_open 0.05; D2: T_open 0.05 and no
weak-signal close; D3: T_open 0.10. Report dev4, worst first-four-year monthly, gate DD, fills; robust selection over
ref (v205) + D1..D3; the most recent year ONLY for the selected row.
A2 diagnostics of v205 (all years may be shown; nothing is selected on them): per-anchor book vs sleeve contribution;
book-only daily alpha/beta vs the equal-weight 5-coin open-to-open market return (OLS, Newey-West 5 lags); 40 circular
shifts of the books inside the live window (numpy default_rng(209).integers(1080, n-1080, 40), sleeve off, align off) with
the share of placebos >= the real book-only 5-year and dev4 monthly; long-only |books| and -books.
Check causality (weights, sigma_d, fills at t+1). Save `replication.json`.
B: compare with `v209/v209_result.json` (return > 0.01pp/month, DD > 0.05pp, counts exact, alpha t within 0.05). Write
COMPARISON.md with a PASS/FAIL verdict. Do not report the most recent year of non-selected rows. Do not edit leader files.
