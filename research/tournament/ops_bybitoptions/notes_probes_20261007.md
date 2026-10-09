Probe log — ops_bybitoptions, 2026-10-07 ~08:15 UTC (keyless public GETs only).

Endpoints:
- https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin={BTC,ETH,SOL}&limit=1000
  -> instruments_{BTC,ETH,SOL}.json (retCode 0; n=736/630/336 incl. Trading/Delivering/PreLaunch)
- https://api.bybit.com/v5/market/tickers?category=option&baseCoin={BTC,ETH,SOL}
  -> tickers_{BTC,ETH,SOL}.json (retCode 0; n=680/580/298)
- https://api-testnet.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC&limit=50
  -> testnet_instruments_BTC.json (retCode 0, status Trading e.g. BTC-25JUN27-103000-P-USDT) => options ARE listed on testnet.

ATM weekly references (expiry 2026-10-16 08:00 UTC, nearest weekly Friday; underlying at snapshot BTC 84171.3 / ETH 2617.06):
- BTC-16OCT26-84000-C-USDT bid 1735 ask 1740 mid 1737.5 spread 5 = 0.288% of mid; bidIV 0.3130 askIV 0.3140 => 0.10 vol pts. mark 1733.11 markIV 0.314.
- BTC-16OCT26-84000-P-USDT bid 1570 ask 1575 mid 1572.5 spread 5 = 0.318% of mid; bidIV 0.3142 askIV 0.3152 => 0.10 vol pts. mark 1573.91 markIV 0.314.
- ETH-16OCT26-2625-C-USDT bid 59.6 ask 60.4 mid 60.0 spread 0.8 = 1.333% of mid; bidIV 0.3869 askIV 0.3918 => 0.49 vol pts. mark 60.15 markIV 0.3904.
- ETH-16OCT26-2625-P-USDT bid 67.9 ask 68.9 mid 68.4 spread 1.0 = 1.462% of mid; bidIV 0.3891 askIV 0.3952 => 0.61 vol pts. mark 68.09 markIV 0.3904.
Straddle spread cost (sum of both legs, one-shot buy AND sell): BTC ~10 USDT on ~3310 mid (~0.30%); ETH ~1.8 on ~128.4 mid (~1.40%).

Instrument facts: settleCoin=USDT for all (BTC/ETH/SOL); expiries at 08:00 UTC (BTC/ETH: daily 08/09/10 Oct + weekly 16/23/30 Oct + 06 Nov, monthly/quarterly out to Jun-27; SOL: 6 expiries incl. same weeklies);
strike grids 16OCT: BTC 22 strikes 70k-100k (1k steps near ATM, 2k wings), ETH 28 strikes 2000-3500 (25-50 near ATM);
filters: BTC tick 5/minPrice 5/lot min 0.01 step 0.01 max 500/deliveryFee 0.00015; ETH tick 0.1/min 0.1/lot 0.1/0.1/5000/0.00015; SOL tick 0.01/min 0.01/lot 1/1/100000/0.0002.

Docs used (public help + API v5, fetched 2026-10-07):
- https://www.bybit.com/en/help-center/article/Bybit-Option-Fees-Explained (maker 0.02/taker 0.03, cap 7%; delivery BTC/ETH 0.015% SOL 0.02% cap 12.5%, daily exempt; liq 0.2%)
- https://www.bybit.com/en/help-center/article/Introduction-to-Bybit-Options (USDT-settled European cash-settled, auto-exercise, settlement = avg index 30 min pre-expiry)
- https://www.bybit.com/en/help-center/article/FAQ-Options-Trading/ (9 expiry types BTC/ETH incl. Weekly listed Thu 08:00 UTC; 7 for SOL; order limits table; price bands)
- https://www.bybit.com/en/help-center/article/How-to-Get-Started-with-Options-Trading-on-Bybit (Cross or PM required, Isolated NOT supported; Pro = buy+sell, Easy/Discover = buy-only; limit+market, PostOnly, TP/SL market-only full-close on mark; reduce-only close)
- https://www.bybit.com/en/help-center/article/Initial-Maintenance-Margin-Calculations-Options + Differences-Between-Buying-and-Selling-Options (short needs IM+MM ~10-15% underlying; long premium only, no MM)
- https://www.bybit.com/en/help-center/article/Differences-Between-the-Margin-Modes-Under-the-Unified-Trading-Account (UTA Cross default shares collateral; PM optional, switch needs IMR<=100% + no hedge-mode; no USD minimum found in EN docs)
- https://bybit-exchange.github.io/docs/v5/order/create-order + /batch-place + /rate-limit (category=option, orderType Market/Limit, TIF GTC/IOC/FOK/PostOnly, reduceOnly, takeProfit/stopLoss full-size market, max 50 open option orders/coin, ~10 req/s option trading)
No authenticated endpoints used; .env never read.
