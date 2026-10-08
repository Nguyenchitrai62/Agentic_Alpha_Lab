# OpenCode task oc_downshare - IDEAS5 #3: Downside-share dip tilt (D1 6d downside-RV share; D2 HAR-RS daily/weekly blend 0.6/0.4)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_downshare/` and `tests/test_oc_downshare.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine / heavy 1m work via scripts/heavy_slot.py (RAM is tight on
this host: one engine job at a time, load one coin at a time, float32). Long jobs: nohup + a log file under your tmp/, poll the log; never
inspect /proc or folders outside the workspace (auto-rejected, ends your session).

## Task
Implement idea #3 of docs/opencode/IDEAS5_20261008.md EXACTLY as written there (mechanism, causal rule, the two pre-registered variants and
their frozen thresholds, data, harness, leakage notes) - read the whole file and the CLOSED rows it cites first. If the data it names does not
cover an anchor year, disclose and skip that year for that variant (never impute). Dip-side ideas: dip replica + placebo gate first (all
PROMISING legs + dSum5y >= +0.273 as in the IDEAS5 header); run the 4-phase engine only for variants that pass the gate. Book-side ideas:
4-phase engine vs G2 (v421 R2B1D17BFG2; reproduce 5.41 / 16.91 / 16.82 to the digit first) plus the exposure-matched control where IDEAS5 asks.
MANUAL idea: the MANUAL 4-phase harness of research/tournament/oc_k2manual (reproduce M5_human 3.728 / 17.94 / 17.79 first).

## Report
Per year table (dev years 2021-2024, then the post-release year 2025-09-24..2026-09-23 scored ONCE for the dev4 robust pick and the
reference only, labelled), dev4 robust pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST year, ties -> mean), 5y, full-path DD,
win rates, the leakage checklist (feature timing, label windows, fit windows, fill timing), and a Vietnamese 3-line verdict.
