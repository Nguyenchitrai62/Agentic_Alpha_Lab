# OpenCode task oc_cboostbybit - does B7 keep its edge under frictions and on BYBIT prices (S5)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_cboostbybit/` and `tests/test_oc_cboostbybit.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine via scripts/heavy_slot.py (RAM tight: one engine job at a
time). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or folders outside the workspace.

## Context
research/tournament/oc_cascadeboost: B7 = dip budget x1.5 for 7 days after a cascade bar (> 4 sigma 4h close-to-close move, definition of
oc_cascadedelay) is the dev4 robust pick (mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION: the idea was
formed after oc_cascadedelay's replica had covered all five years incl. the post-release year, so post-release numbers are labelled
diagnostics and new evidence must come from controls, unseen years, frictions and prospective paper.

## Rows
Copy research/tournament/oc_c2bybit's friction harness. Reproduce oc_cascadeboost's REF and B7 numbers to the digit first. Then REF and B7
under: base, S1 cost stress, S2 latency 15, S3 latency 30, S4 stop slip, S5 Bybit prices. Report dev4, the post-release year (labelled
diagnostic), 5y and full-path DD (and the worst 1m-marked episode). Verdict (Vietnamese 3 lines): B7 - REF > 0 under every friction and on
Bybit prices with full-path DD <= 20?
