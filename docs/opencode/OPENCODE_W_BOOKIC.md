# OpenCode task oc_bookic: where does the book earn and lose (5 years)?
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under the folder named below (+ tests/test_<folder>.py); no commits; no edits of leader files or other folders; market data up to 2026-09-24 00:00 UTC may be read (all years are research data; findings need prospective validation). Load 1m data one coin at a time in float32; RAM < 1.5 GB; one process. Write PLAN.md (hypothesis, exact definitions, decision rule) BEFORE computing outcomes; then scripts, results.json, REPORT.md with tables and a one-line verdict. Folder: research/tournament/oc_bookic/.
Data: the deployed BOT book = forward_v205.research_books_d2 (see research/diagnostics/r2_decompose5/r2_decompose5.py for how it is built:
eu.er.v154_books() index, fw.research_books_d2(eu)); 4h opens from eu.er.v154_books(). Compute per anchor year 2021-09-24..2025-09-24 and per
coin: the book weight's Spearman IC vs the next 42-bar (7-day) open-to-open return, the vectorised gross P&L of the book (weight x next-bar
return, no costs) split into long and short legs and into regimes (BTC above / below its 1200-bar 4h mean; 30-day vol above / below its
1-year median), and the P&L of the book during the drawdown windows 2022-07-20..2022-11-10, 2023-04-17..2023-06-14, 2022-01-13..2022-01-22,
2024-01-03. Verdict: which leg / regime / coin carries the losses; propose (do not test) at most 2 rules with an economic reason.
