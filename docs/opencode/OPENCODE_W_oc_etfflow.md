# OpenCode task oc_etfflow - spot-ETF net-flow data (2024-01+) and an outflow book-long throttle screen (idea B2 of IDEAS_20261007c.md)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `data/raw/etf_flows_20261007/`, `research/tournament/oc_etfflow/` and
`tests/test_oc_etfflow.py`.

## Data
Daily US spot BTC and ETH ETF net flows (US$m) from a free public source (idea D7 points to https://farside.co.uk/btc/ and /eth/; verify the
page is reachable with a single GET, respect robots / terms, no heavy scraping: one request per page). If the pages are not machine-readable
or blocked, try one alternative free source and stop if none works (report). Save `btc_etf_flows_daily.csv`, `eth_etf_flows_daily.csv`
(date, total net flow) + manifest.json (source URL, fetch time, sha256). Availability: flows for US trading day D are published after the US
close (~21:00-23:00 UTC D or D+1 morning) -> treat a day's value as known from D+1 08:00 UTC (conservative).

## Screen (POST-span: only 2024-01-11 .. 2026-09-23 exists; NO dev4 selection is possible - label everything SHORT-SPAN, descriptive)
- Signal: S5 = sum of BTC+ETH net flows over the last 5 published trading days (known as of the bar), z = S5 vs its trailing 250-trading-day
  distribution (min 120). Rule T1: halve BOOK long weights while S5 < the trailing p5; T2: while S5 < the trailing p10.
- Judge with the 4-phase engine exactly like research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py (per (T, sym) long-weight
  multiplier on standard rows, after the bear filter, before the shifted-clock forward fill) on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear
  True G 2.0); reproduce G2 first. heavy_slot. Report per anchor year that overlaps (2023-09-24 year partially, 2024-09-24, 2025-09-24) R /
  DD vs G2, number of gated weeks, and an exposure-matched constant control.
- Verdict (Vietnamese 3 lines): at best "log prospectively"; no deployment from a short span.
