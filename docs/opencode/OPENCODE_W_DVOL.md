# OpenCode task oc_dvol: Deribit implied vol (DVOL) as dip-rung context
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under the folder named below (+ tests/test_<folder>.py); no commits; no edits of leader files or other folders; market data up to 2026-09-24 00:00 UTC may be read (all years are research data; findings need prospective validation). Load 1m data one coin at a time in float32; RAM < 1.5 GB; one process. Write PLAN.md (hypothesis, exact definitions, decision rule) BEFORE computing outcomes; then scripts, results.json, REPORT.md with tables and a one-line verdict. Folder: research/tournament/oc_dvol/ (raw downloads to data/raw/deribit_dvol_20261005/ with manifest.json of URLs + sha256).
Fetch Deribit public get_volatility_index_data for BTC and ETH, resolution 1h (or 1D if 1h is not available for the whole span), 2021-04..2026-09.
Features at a dip rung's bar open T (data strictly before T): DVOL level z-score vs trailing 90 days, DVOL 24h change, DVOL minus realized
30-day vol (variance risk premium). Join to research/tournament/ext/fills_U_ext.parquet majors R2 rungs (T = t_fill - f minutes). Report per
anchor year 2021..2025 the Spearman IC of each feature with y1.0 and the mean y1.0 by feature tercile (tercile cut-offs from the PREVIOUS
years only). Decision rule: PROMISING only if the IC sign is the same in >= 4 of 5 years AND the leave-one-year-out tercile spread has the
same sign in >= 4 of 5 held-out years.
