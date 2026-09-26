# v91 3-book portfolio execution audit (hidden year 2025-09-24..2026-09-23)
Params frozen as of 2025-09-14 (anchor 2025-09-24; portfolio_v1.json NOT used for params).
Selection: regime {'bull': 2.0, 'neutral': 1.0, 'bear': 0.5} x0.4; tsmom K=1.3; carry [3, 7, 14, 3, 14].
Vectorized normal: net 14.5077% (~1.1372%/mo), DD 15.8497%, fees 1.5605, funding 0.774, turnover 78.0259x, fills 697.
Execution normal: net 10.7009% (~0.8522%/mo), DD 18.297%, fees 1.8191, funding 0.7562, turnover 76.4472x, fills 697, limit 602/697 (rate 0.8637).
Fee-stress exec: net 7.3359% (~0.5926%/mo), DD 20.1458%, fills 697.
Execution-stress (5-min window): net 7.0139% (~0.5674%/mo), DD 20.2804%, fills 697, rate 0.8006.
Per-book vectorized net: regime 5.7968%, tsmom 8.2957%, carry 0.1245% (standalone, don't sum).
Costs: maker/taker/slip normal {'maker': 0.0002, 'taker': 0.0005, 'slip': 0.0002, 'window_min': 15}; actual funding both signs; spot proxy = perp 1m.
Rows: 2190 4h bars; months 11.98; coverage 0.8104; vs ~4-8 bps round-trip cost: see monthly gaps above.
Worker self-report; awaiting leader audit. Files: weights_4h.csv, backtest_results.json, selection.json.
