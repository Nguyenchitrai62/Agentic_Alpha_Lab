# OpenCode task oc_confirmgate - IDEAS10 #1: Binance-select -> Bybit / pre-sample confirm gate
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_confirmgate/` and `tests/test_oc_confirmgate.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome (docs task: a short PLAN section at the top of your folder's notes).
Heavy work via scripts/heavy_slot.py (RAM tight: one job at a time). Long jobs: nohup + log under tmp/; never inspect /proc or folders outside the workspace.

## Task
RETROSPECTIVE META-STUDY (no new strategy fits): apply both confirm legs to every candidate that won a dev4 robust pick in docs/CLOSED_DIRECTIONS.md rows dated 2026-10-07 / 2026-10-08 (e.g. C2, K2, D1, fundclock W2, lsratio, vpinveto V1, decayexit V2, shortmember AS18, B7, ...), using only stored runs (Bybit S5 rows where they exist, pre-sample replica results where they exist; run missing Bybit S5 rows via the oc_c2bybit harness only for at most 6 candidates). Report per candidate: passed confirm leg 1 (Bybit dev4 robust vs REF), leg 2 (pre-sample), and whether its post-release-year number beat REF. Does the 2-leg gate separate the candidates that transferred from those that did not? Write the protocol as docs/opencode/CONFIRM_GATE.md (<= 30 lines) if it does.

## Report
Per year table where applicable (dev 2021-2024; post-release year scored ONCE for the dev4 robust pick and REF only, labelled), dev4 robust
pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST, ties -> mean), 5y, full-path DD, the leakage checklist, Vietnamese 3-line verdict.
