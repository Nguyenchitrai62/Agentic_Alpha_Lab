# OpenCode task oc_clockweights - IDEAS6 #6: Adaptive 4-clock capital share (yearly weights)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_clockweights/` and `tests/test_oc_clockweights.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) BEFORE any outcome. Engine / heavy 1m work via scripts/heavy_slot.py (RAM is tight:
one engine job at a time, one coin at a time, float32). Long jobs: nohup + a log under your tmp/, poll the log; never inspect /proc or folders
outside the workspace (auto-rejected, ends your session).

## Task
Implement idea #6 of docs/opencode/IDEAS6_20261008.md EXACTLY as written there (mechanism, causal rule, the two pre-registered variants,
data, harness, leakage notes) - read the whole file and the CLOSED rows it cites first. User trade rules (AGENTS.md) still bind: limit entries,
every position has a stop (market, taker 0.00055) and a take-profit (limit, maker 0.0002), no fills in minutes 0-4 after the 4h close, stop-first
when stop and TP touch in one 1m bar, unfilled entry limits expire (no market fallback for entries). Dip-side ideas: replica + placebo gate
first (all PROMISING legs + dSum5y >= +0.273), engine only for variants that pass. Book / account ideas: 4-phase engine vs G2 (v421
R2B1D17BFG2; reproduce 5.41 / 16.91 / 16.82 to the digit first).

## Report
Per year table (dev 2021-2024; post-release year 2025-09-24..2026-09-23 scored ONCE for the dev4 robust pick and REF only, labelled), dev4
robust pick (DD <= 20, no losing year, prefer mean >= 5, highest WORST, ties -> mean), 5y, full-path DD, win rates, fee / funding split,
the leakage checklist (feature timing, label windows, fit windows, fill timing), and a Vietnamese 3-line verdict.
