# OpenCode task oc_cboostpre - does B7 work in the UNSEEN pre-sample years 2017-2020?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_cboostpre/` and `tests/test_oc_cboostpre.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine via scripts/heavy_slot.py (RAM tight: one engine job at a
time). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or folders outside the workspace.

## Context
research/tournament/oc_cascadeboost: B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move, definition of
oc_cascadedelay) is the dev4 robust pick (mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION: the idea was
formed after oc_cascadedelay's replica had covered all five years incl. the post-release year, so post-release numbers are labelled
diagnostics and new evidence must come from controls, unseen years, frictions and prospective paper.

## Method
Use the pre-sample dip replica of research/tournament/oc_presampletilt (bars_4h_presample.parquet, its D0+B1 ledger builder; 2017 .. 2020-09-23)
and the cascade-bar definition of oc_cascadedelay (frozen) computed on the pre-sample 4h closes. Apply B7 and B3 (x1.5 for 7 / 3 days) and
report per pre-sample year: n fills, base sum, B7 / B3 sum, normalised gain, timing placebo pct (1000 permutations of the boost windows within
the year, same count and length) and block pct. Also report the share of boosted fills that hit the stop vs the base rate (crash risk).
Verdict (Vietnamese 3 lines): does the post-cascade boost help in years nobody looked at when the idea was formed?
