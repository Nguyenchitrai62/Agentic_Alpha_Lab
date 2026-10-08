# OpenCode task oc_cboostctrl - is B7 timing or just more exposure? (exposure-matched controls in the ENGINE)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_cboostctrl/` and `tests/test_oc_cboostctrl.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine via scripts/heavy_slot.py (RAM tight: one engine job at a
time). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or folders outside the workspace.

## Context
research/tournament/oc_cascadeboost: B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move, definition of
oc_cascadedelay) is the dev4 robust pick (mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION: the idea was
formed after oc_cascadedelay's replica had covered all five years incl. the post-release year, so post-release numbers are labelled
diagnostics and new evidence must come from controls, unseen years, frictions and prospective paper.

## Rows (pre-registered)
REF (G2, reproduce 5.41 / 16.91 / 16.82 first), B7 (copy oc_cascadeboost), CTRL_C = constant dip budget multiplier equal to B7's realised
mean dip-budget multiplier per year (computed from B7's own engine run, i.e. same average exposure, no timing), CTRL_R = random 7-day x1.5
windows with the same count per year as B7's cascade windows (20 random seeds; report mean, p5, p95 of each metric). Dev4 per year / mean /
WORST / DD, 5y, full-path DD, worst 1m-marked episode. Verdict (Vietnamese 3 lines): what share of B7's gain over REF is timing (B7 - CTRL)
vs exposure (CTRL - REF), and is B7 above the p95 of the random-window distribution in each year?
