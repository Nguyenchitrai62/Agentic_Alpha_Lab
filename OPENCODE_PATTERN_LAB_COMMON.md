# pattern_lab_r1 common worker rules (read with your own assignment)

Leader: Claude Code. User request 2026-09-24: test candlestick patterns, chart
patterns and indicators, mainly as model features. Protocol:
`configs/pattern_lab_r1_protocol.json` (read it). Contract and helpers:
`src/agentic_alpha_lab/patterns/common.py` (read it; do NOT edit it).

Hard rules
- Read AGENTS.md. No live orders, credentials, cloud uploads, heavy training.
- Load data ONLY with `common.load_bars(tf)` / `common.load_funding()` using the
  default (opened year hidden). Never pass include_opened_year=True, never read
  data/raw/ma_ribbon_20260924 parquet files directly, never read
  artifacts/research/ma_ribbon_r1 or any result for dates >= 2025-09-24.
- Write ONLY the files named in your assignment. Other workers run in parallel
  in the same repo: do not touch their files, common.py, configs, ledgers,
  NEXT_AGENT.md, ../Kronos, or git (no commit/stash/checkout/reset).
- Your module exposes `compute(bars) -> DataFrame` (float features, same index
  as bars, NaN allowed during warm-up, column prefix given below) and
  `events(bars) -> DataFrame` (int8 in {-1,0,1}, the directional hypothesis the
  pattern is traditionally said to imply; one column per pattern, same prefix).
  Both must work for 1h, 4h and 1d bars (columns open_time, open, high, low,
  close, volume, quote_volume, taker_buy_volume, ...). Vectorized pandas/numpy;
  the full 1h history (~52k rows) must finish in under 60 s.
- Row t may use only bars[:t+1]. Test with `common.assert_causal` on REAL
  `load_bars("1h"/"4h"/"1d")` (a 3000-row slice for 1h is fine) plus a
  synthetic hand-checked case per pattern family. No centered windows, no
  shift(-k), no global normalization, no future-dependent pivots.
- Study script: run `common.event_study` on 1h, 4h, 1d; write CSV + SUMMARY.md
  to your artifacts folder. Report honestly: how many patterns are
  stable_significant after FDR, effect sizes in bps vs ~4-8 bps round-trip cost.
  Do not tune pattern definitions to improve results; fix textbook definitions
  first, record parameters, then run once. If you change a definition after
  seeing results, log it in SUMMARY.md as a post-hoc change.
- Run `.venv/Scripts/python.exe -m pytest <your test file> tests/test_pattern_lab_common.py -q`.
- Finish with a <= 15 line SUMMARY.md and stop.
