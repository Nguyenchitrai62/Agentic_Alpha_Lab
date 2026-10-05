# OpenCode task oc_manualbf: MANUAL with the bear-regime book filter (honest human schedule)
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md. Write ONLY under research/diagnostics/oc_manualbf/ (+ tests/test_oc_manualbf.py); no
commits; no edits of leader files; market data up to 2026-09-24 00:00 UTC; ONE heavy process (Pool(1)), RAM < 2.5 GB.
Base: research/diagnostics/manual_human/manual_human.py (MANUAL pipelines on the four phases, agents on, human schedule: 15-minute reaction,
night bar skipped). Extend it to the FIVE years 2021-09-24..2026-09-23 (as research/diagnostics/r2_decompose5/r2_decompose5.py builds the full
index: phase_offset_full.prep_idx on books154.index + shift, v376/tables_hidden r2 tables) and add, per pipeline M4 (v362) and M5 (v367), a
'BF' row: book LONG targets x0.5 on standard book rows where the BTC 4h open < its 1200-bar mean (opens up to the row; transform before the
shifted-clock forward fill; shorts and dips unchanged) - the BOT result v410 improved the weak years with this filter.
Report per pipeline and row: per-year %/month (single clock, mean over the four phases as manual_human does), 5-year geometric mean, max yearly
DD (mean over phases and worst phase), book win rate and all-trade win rate (as v377 / phase_offset_full.book_win). PLAN.md first (rows fixed).
Verdict vs the base gate (>= 5 %/month, DD < 20, win > 55 %). REPORT.md + results.json.
