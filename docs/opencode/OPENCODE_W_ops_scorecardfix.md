# OpenCode task ops_scorecardfix - correction windows in the prospective scorecard + the two carry runners
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION to the common write scope (leader-assigned implementation task): you may edit
`scripts/prospective_scorecard.py` and `scripts/paper_report.py`, create `artifacts/research/advisor_shadow/paper_corrections.json`, and write
`tests/test_ops_scorecardfix.py`. Nothing else (bot/, backend/, artifacts/bot/* stay read-only; never start / stop processes).

## Why
docs/opencode/PAPERFIX_20261007.md (+ research/diagnostics/ops_paperfix/paperfix.json, pieces.csv): a bot bug (fixed in commit cb14cb7) and an
outage distorted every paper runner between 2026-10-06 20:10 and 2026-10-07 07:35 UTC (stuck time exits closed late; paper P&L overstated by
0.16-0.35 % of equity). Recommendation accepted by the leader: EXCLUDE that window from the main prospective evidence, keep the raw numbers as a
side row. Also, the scorecard's BOT_DIRS lacks the two G2 + carry runners (artifacts/bot/paper_d17bfg2c, paper_g2k20c).

## Implement
1. `artifacts/research/advisor_shadow/paper_corrections.json`: a list of windows {start, end (UTC ISO), runners: [...] or "all", reason,
   source doc, per-runner pnl_overstatement_usdt (from paperfix.json)}. One entry for the window above.
2. `scripts/prospective_scorecard.py`: read the corrections file (missing file -> no correction, unchanged behaviour). For each bot runner,
   compute the MAIN live return with the excluded windows removed: chain the equity-curve returns of the hourly points outside the windows
   (the return across a window is replaced by 0, i.e. the window's P&L is removed), and report days = live days minus excluded days for the
   bootstrap horizon. Keep the raw (uncorrected) return as an extra field `raw_*`. Add d17bfg2c ("G2 + carry f 0.25 (paper)") and g2k20c
   ("G2K20 + carry f 0.25 (paper)") to BOT_DIRS / NAMES / RESEARCH_EXPECT (research expectations: G2 + carry 5.634 %/month, max yearly DD
   16.75 (research/tournament/oc_carrycompound/REPORT.md); G2K20 + carry 6.097 / 17.64 (research/tournament/oc_g2k20compound/REPORT.md) -
   check the numbers in those reports and cite them in comments).
3. `scripts/paper_report.py`: optional `--corrections <path>` (default = the file above if it exists) that prints a line per runner with the
   excluded window and the raw vs corrected return; output unchanged when no file.
4. Tests (tests/test_ops_scorecardfix.py): synthetic equity curve with a window -> corrected return equals the hand-computed chain; missing
   corrections file -> identical output to before; the two new runners appear. Run the existing tests that touch these scripts too
   (`.venv/Scripts/python.exe -m pytest tests -q -k "scorecard or paper_report"`), all must pass.
5. Run both scripts once (read-only on bot state) and paste the before/after table into `docs/opencode/SCORECARDFIX_20261007.md` (<= 40 lines).
