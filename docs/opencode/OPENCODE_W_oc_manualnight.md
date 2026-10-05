# OpenCode task oc_manualnight
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md. Write ONLY under research/diagnostics/oc_manualnight/ (+ tests/test_oc_manualnight.py). No commits, no registry edits. HEAVY: ONE engine process at a time; wait until free RAM > 4 GB before each run (PowerShell FreePhysicalMemory check, sleep 300).
MANUAL diagnostic (pre-register rows in PLAN.md). Base = research/diagnostics/oc_manualcap/oc_manualcap.py harness (M5_human: 15-minute reaction, night bar skipped, 4 phases, agents on, 5 research years, reset metric + full-path DD) - copy it. Rows (fixed):
  M5_human            reference (must reproduce oc_manualcap: 3.73 / maxDD 17.9).
  M5_human_night      the night bar (start (20+s) UTC) is NOT skipped for dips: before sleeping the human pre-places that bar's dip limits with levels computed from the PREVIOUS bar's open and sigma4 (known 4h earlier: level = O_prev x (1 - k sigma4_prev), same rungs/sizes/TP/stop multiples), valid for the night bar only; book orders still skipped at night.
  M5_human_K13G15     dip sizes x1.3 and the risk budget x1.3, plus the placement-time gross cap G = 1.5 exactly as oc_manualcap's G15 (static bar cap + sleeve_gross_cap).
  M5_human_night_K13G15  both.
Report per row: 5y %/month, worst year, max yearly DD, full-path DD, book win per year and pooled (MANUAL goal >= 5 %/month, DD < 20, book win >= 55 %). Plain verdict. REPORT.md + results.json.
