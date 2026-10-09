# oc_ideascan4 — probe notes (scan only, no backtests, no downloads > 50 MB)

Scripts: `probe_sources.py` (6 probes). Outputs: `probes/*.json` (one small truncated
response each, total < 100 KB). Tests: `test_probes.py` (span + size + no-forward-data checks).
Run: `.venv/Scripts/python.exe research/tournament/oc_ideascan4/probe_sources.py`
Test: `.venv/Scripts/python.exe -m pytest research/tournament/oc_ideascan4/test_probes.py -q`

Purpose: verify that every H1-H8 pre-registration in `docs/opencode/IDEAS4_20261007.md`
has FREE data reaching back to >= 2021-09 (the first walk-forward anchor is 2021-09-24),
and document the ineligible items (H9). No returns are computed here; in particular NO
forward returns for dates >= 2025-09-24 are touched (the scan uses only literature numbers).

## Verified (HTTP 200 with real payload, saved in probes/)

| Probe | Endpoint | What it proves |
|---|---|---|
| p1 | `GET data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h&startTime=0&limit=1` | BTCUSDT 4h history starts 2017-08-17 (openTime 1502942400000) — covers all 5 anchors; H1-H5 need only klines+volume |
| p2 | `GET data-api.binance.vision/api/v3/klines?symbol=<ETH,SOL,BNB,XRP>USDT&interval=1d&startTime=1632441600000&limit=1` | All 5 majors have daily klines at 2021-09-24 (SOL lists 2020-08, BNB/XRP earlier) — 5-coin XS (H4/H5) computable from anchor 2021 |
| p3 | `GET fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=1632441600000&limit=1` | Perp funding history reaches 2021-09-24 (context for carry-family mapping #7; no new pull needed) |
| p4 | `GET api.alternative.me/fng/?limit=1&format=json` + `?date=2021-09-24&format=json` | Fear & Greed daily history reaches 2021-09-24 (supports the #27 TESTED-CLOSED mapping; F&G member already rejected, no new variant) |
| p5 | `GET api.blockchain.info/charts/market-price?timespan=1days&format=json` (fallback; `/charts/nvt` path unavailable from this host) | Free keyless on-chain-adjacent history reachable — the MVRV-z gate (H8) starts from the frozen `onchain_20260924` CSV; live/free vintage verification is the H8 worker's first step (anchor years without history are skipped, never imputed) |
| p6 | `GET query1.finance.yahoo.com/v8/finance/chart/BTC=F?interval=1d&range=5d` | CME BTC front-month daily reachable (re-confirms oc_ideascan3 d20; supports #21 TESTED-CLOSED mapping; mechanism expiring with CME 24/7) |

## Attempted / documented ineligible (no new pull — do not build selection on without re-probe)

- Google Trends: no official keyless API; `trends/api/explore` 429 from this host
  (oc_ideascan3 d16). H16/H9b stays log-only.
- X/Twitter + StockTwits message history: paywalled, no free history to 2021. H9a log-only.
- Spot ETF flows (Farside table): live page verified in oc_ideascan3 (d10) but history starts
  2024-01-11 — overlap screen + paper only (H9c), never a dev4 selection input.
- 15-min turn-of-the-candle (H9d): needs HFT execution incompatible with 4h decisions +
  the minute-5 fill ban — structurally ineligible, no variant.
- Upbit/Korean retail tape (Kimchi leg of #20): v230 Korean member already rejected; no new pull.

## History-span assessment (vs the 5 walk-forward anchors 2021-2025)

Full-span (>= 2021-09, all anchors): Binance klines+volume all 5 majors (p1-p2), perp funding
(p3), F&G daily (p4), free keyless BTC charts (p5, vintage check is H8's step 1), CME daily (p6).
Short-span (overlap + paper only, never selection): ETF flows (2024-01-11+), Hyperliquid/Coinbase-Intl
perps (2023+), Bybit options (~2022+), Google/Twitter (no free history).
