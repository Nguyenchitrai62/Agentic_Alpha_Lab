# OpenCode task oc_dvolbook: implied volatility (DVOL) for the BOOK
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under research/tournament/oc_dvolbook/
(+ tests/test_oc_dvolbook.py); no commits; no edits of leader files; data up to 2026-09-24 00:00 UTC; one light process.
Data: research/tournament/oc_dvol/dvol_hourly.parquet (BTCDVOL / ETHDVOL hourly closes; t = hour start), the deployed BOT book
(forward_v205.research_books_d2 as research/diagnostics/r2_decompose5/r2_decompose5.py builds it; 4h opens from eu.er.v154_books()).
PLAN.md first (fixed definitions; DVOL known strictly before the bar: last hourly close ending at or before T): z90 (vs trailing 2160 hours),
24h change, DVOL - realised 30d vol. Questions per anchor year 2021..2025: (1) Spearman IC of each feature with the next 42-bar (7-day) and
next 6-bar (1-day) open-to-open return of each major (pooled, and BTC / ETH with their own DVOL); (2) the book's gross vectorised P&L (weight x
next-bar return) split by DVOL z90 tercile (tercile cut-offs from PREVIOUS years only) - long and short legs separately; (3) does high DVOL
predict larger book losses (crash risk) or better book returns? Decision rule: a book rule is PROMISING only if the same sign holds in >= 4 of
5 years AND leave-one-year-out in >= 4 of 5. REPORT.md + results.json; one-line verdict and at most one proposed rule with an economic reason.
