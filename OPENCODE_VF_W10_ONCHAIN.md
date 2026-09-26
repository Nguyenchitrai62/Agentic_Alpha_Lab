# vf W10: on-chain and stablecoin supply for BTC (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/onchain.py`, `tests/test_vf_onchain.py`,
`research/vf/onchain_study.py`, `artifacts/research/vf/onchain/*`,
`data/raw/onchain_20260924/*` (all downloads/temp here; never write outside the workspace).
Data: Coin Metrics Community API (free, no key):
`https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=<comma list>&frequency=1d&start_time=2019-01-01&page_size=10000`
(follow `next_page_url`). Try metrics: CapMVRVCur, CapMrktCurUSD, AdrActCnt,
TxCnt, HashRate, FeeTotUSD, SplyExNtv (may be unavailable; skip missing), and for
stablecoins `assets=usdt,usdc` metric `CapMrktCurUSD` (or SplyCur). Record which
metrics were actually returned, row counts, hashes in a manifest.
Availability: a daily on-chain value for date D is known only after D ends; use
D+1 02:00 UTC as the availability time (as-of join to BTC bar close).
compute(): MVRV level and z-score vs 365d, MVRV 30d change, active addresses and
tx count 30d growth and z-score, hash-rate 30d growth, fee z-score, stablecoin
(USDT+USDC) market cap 30d and 90d growth, stablecoin cap / BTC cap ratio change.
events(): MVRV z > 2 -> -1 (overheated), MVRV < 1 -> +1 (undervalued), stablecoin
30d growth z > 1.5 -> +1 (liquidity inflow), hash-rate 30d drop > 10% -> -1.
Event study on 4h and 1d BTC bars (horizons 6/12/42 on 4h also useful: pass
horizons=(6, 12, 42, 90) to common.event_study for 4h and (3, 7, 14, 30) for 1d).
