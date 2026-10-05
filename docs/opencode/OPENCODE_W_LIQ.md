# OpenCode task oc_liq: first look at the live liquidation stream
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under the folder named below (+ tests/test_<folder>.py); no commits; no edits of leader files or other folders; market data up to 2026-09-24 00:00 UTC may be read (all years are research data; findings need prospective validation). Load 1m data one coin at a time in float32; RAM < 1.5 GB; one process. Write PLAN.md (hypothesis, exact definitions, decision rule) BEFORE computing outcomes; then scripts, results.json, REPORT.md with tables and a one-line verdict. Folder: research/tournament/oc_liq/.
Data: data/raw/liquidations_live/{binance,bybit}/<SYM>/<date>.parquet written by backend/liquidations.py since 2026-10-04 (read the module to
learn the schema; do not modify it). Report: rows per day / venue / coin, gaps (coverage files in _coverage), the size distribution, the
largest liquidation minutes and the 1m price path around them (Bybit / Binance public klines for those minutes only), and whether liquidation
bursts coincide with dip-ladder level touches (rung levels need the 4h open and sigma_4h - compute from public 4h klines). This is a data
quality + descriptive note only (too little history for any test); list what to measure once 3 months exist.
