# OpenCode task oc_btcresid - IDEAS8 #1: BTC-residual idiosyncratic book
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_btcresid/` and `tests/test_oc_btcresid.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine / training via scripts/heavy_slot.py (RAM is tight: one job
at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace. CPU training only (no heavy local GPU).

## Task
Implement idea #1 of docs/opencode/IDEAS8_20261008.md EXACTLY as written (rule, the two pre-registered variants and frozen constants, data,
harness, leakage notes) - read the whole file and the CLOSED rows it cites first. Book ideas run in the 4-phase engine vs G2 (v421
R2B1D17BFG2; reproduce 5.41 / 16.91 / 16.82 to the digit first); every idea that changes average book exposure also gets an exposure-matched
constant control (book target x the variant's realised mean scale per year). Retraining ideas: per-anchor walk-forward training on data before
A - embargo only, exactly like the existing member builders (cite them), with a builder check that the unchanged pipeline reproduces the
cached members before any change.

## Report
Per year table (dev 2021-2024; post-release year 2025-09-24..2026-09-23 scored ONCE for the dev4 robust pick and REF only, labelled), dev4
robust pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST, ties -> mean) among REF and the variants (controls reported, not
eligible), 5y, full-path DD, book episode win rate, fee split, the leakage checklist, and a Vietnamese 3-line verdict.
