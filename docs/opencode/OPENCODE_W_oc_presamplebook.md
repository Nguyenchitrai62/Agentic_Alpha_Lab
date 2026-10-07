# OpenCode task oc_presamplebook - is the BOOK's directional skill general? A TV-indicator member trained and tested on 2017-2020 spot data
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presamplebook/` and `tests/test_oc_presamplebook.py`.
Print progress at least every 10 minutes.

## Why
oc_presample / oc_presample2 showed the dip sleeve generalises to never-used 2017-2020 data, and that the dip sleeve alone earns only
0.6-3 %/month in 2021-2026: the BOOK carries G2 (5.4 %/month). The book's skill has never been checked outside 2021-2026 (its training
windows start in 2017 for some members, but no test year before 2021-09). If the book's signal family has no skill before 2021, live risk
is higher than the research says.

## Data and member (descriptive generality test; NOT the deployed book)
- 4h spot bars from Binance spot 1m (data/raw/spot_1m_presample_20261007: BTC/ETH 2017-08.., BNB 2017-11.., XRP 2018-05..; build 4h
  OHLCV on the standard grid) and, for the reference years, the same features on 2020-08..2025-09 from the existing 4h data (find the T3/TV
  feature code: research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py, read its docstring; reuse it unchanged).
- Member: pooled HistGradientBoostingRegressor exactly like the v231 A member's model settings (read v231 / v233 scripts for max_depth,
  learning rate, iterations, min_samples_leaf; copy them), target = next 42-bar (7-day) vol-normalised forward return as in v92/v231 (copy the
  label definition), features = the 17 TV features only (no flow, no premium - those data do not exist pre-2020).
- Walk-forward anchors (each test year [A, A+365 d), training rows with label end < A - 7 d): A = 2019-03-01 (train 2017-10..2019-02),
  2019-09-24, 2020-03-01 (overlaps COVID). Reference: the same member, same code, anchors 2021-09-24 .. 2024-09-24 trained on everything before
  (dev years; this is NOT the deployed book, so state its numbers separately).

## Report
Per test year: pooled and per-coin Spearman IC of the prediction vs the realised label (bootstrap CI, block 42), hit rate of the sign, and a
simple diagnostic long/short book P&L (weight = clip(pred / pred_std_train, -1, 1) per coin, rebalanced every 4h bar, cost 0.0002 per unit
turnover, no leverage) - LABEL it a vectorised diagnostic (memory: vectorised book screens do not equal the engine). Key question in bold: is
the pre-sample IC of the same sign and similar size as in the reference years? Vietnamese 3-line verdict.
