# OpenCode task oc_presample - the G2 dip sleeve on data BEFORE the research window (2018-01 .. 2020-08), fixed rules, no tuning
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `data/raw/spot_1m_presample_20261007/`, `research/tournament/oc_presample/`
and `tests/test_oc_presample.py`.

## Why
Every rule of the deployed dip sleeve was chosen on 2020-08 .. 2026-09 data. Binance spot 1m klines exist from 2017-08 for BTC/ETH/BNB and
from 2018-05 for XRP (check), i.e. ~2.5 years that NO selection ever saw, including the 2018 bear market (-80 %) - the most dangerous regime for
a long-rebound ladder. A fixed-rule replay there is genuinely new out-of-sample evidence (labelled PRE-SAMPLE). oc_crash2020 replayed only
10-day crash windows (COVID 2020-03 is inside this span: compare).

## Data
Download Binance SPOT 1m klines from the public archive https://data.binance.vision/data/spot/monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip
(+ .CHECKSUM files, verify sha256) for BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT from the first month available to 2020-09 inclusive. Save one parquet
per symbol (open_time UTC, o, h, l, c, volume) + manifest.json (months, rows, sha256, gaps). SOL has no data before 2020-08: the replay uses the
four coins (state it; B1's n counts only coins present). Report gaps (Binance had outages, e.g. 2018-2019 maintenance windows).

## Replay (fixed rules - copy the dip-only replay of research/tournament/oc_crash2020, read its REPORT/PLAN/code first)
G2 dip sleeve exactly as oc_crash2020's G2 arm: B1 sizes 1/(1+n) x kd 1.7, R2 depths 2.5/3/3.5/4/5 sigma, risk budget 0.442 (gap 0.02), gross
cap 2.0 per phase sub-account, close5 4-sigma stop + 8-sigma backstop, TP 1 sigma, timeout at the next 4h open, stop-first, no fill in minutes
0..15 of a bar exactly as the live offsets of the replica, R2 agent size = 1 (no learned agent - it needs training data), gate costs (maker
0.0002 / taker 0.00055, longs pay 0.0001 per 8h settlement held). sigma = std of the last 360 4h open-to-open log returns (needs 60 days of
warm-up: start trading 60 days after each coin's first bar). Four clock phases (4h grid + 0/1/2/3 h), each 1/4 of the capital, equity
compounding within a year, reset per year.
Years (PRE-SAMPLE, labelled): 2018-01-01 .. 2018-12-31, 2019-01-01 .. 2019-12-31, 2020-01-01 .. 2020-08-31 (+ the first available months of
2017 if >= 60 days warm-up allows, as a separate row).
Reference rows for comparison: the same dip-only replay on the five research years 2021-09-24 .. 2026-09-23 (4-phase, same code) - reproduce
the oc_crash2020 harness numbers for one of its windows first (bit-for-bit) to prove the copy is faithful.

## Report
Per year and per phase: %/month geometric (dip sleeve alone, on full equity), max DD (1m-marked), fills, stops, win rate, worst day, worst
minute; the 4-phase mean. Compare with the research years. Key question in bold: was the dip sleeve profitable with DD <= 20 % in 2018 and
2019 under the fixed rules? Spot-vs-perp caveat (spot prices, perp costs). No parameter may be changed after seeing any pre-sample number;
any extra row must be labelled post-hoc. Vietnamese 3-line verdict.
