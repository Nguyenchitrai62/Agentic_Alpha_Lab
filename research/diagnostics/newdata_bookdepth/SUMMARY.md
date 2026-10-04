# bookdepth study (dev only, 2023-01..2025-09-13, n=5340 majors fills; majors == all-coins coverage)
as-of: last snapshot ts < t_fill asserted; depth_rel_7d trailing median, lags 15/60 min
x2 NaN: partial IC on complete-case rows (n_partial per feature)
bd_imb_1: ic23=-0.049 ic24=-0.119 ic25=-0.052 pool=-0.0561 t=-4.1 partial=-0.0559 t_p=-4.1 same_sign=True interesting=True
bd_imb_2: ic23=-0.051 ic24=-0.056 ic25=-0.008 pool=-0.0199 t=-1.5 partial=-0.0266 t_p=-1.9 same_sign=True interesting=False
bd_depth_rel_7d: ic23=-0.160 ic24=-0.159 ic25=-0.240 pool=-0.1677 t=-12.4 partial=-0.1561 t_p=-11.5 same_sign=True interesting=True
bd_chg_bid_15: ic23=-0.148 ic24=-0.093 ic25=-0.030 pool=-0.0825 t=-6.1 partial=-0.0662 t_p=-4.8 same_sign=True interesting=True
bd_chg_bid_60: ic23=-0.123 ic24=-0.163 ic25=-0.115 pool=-0.1198 t=-8.8 partial=-0.0886 t_p=-6.5 same_sign=True interesting=True
4h bd_imb_1: pooled ic23=+0.011 ic24=+0.046 ic25=+0.009 pool=+0.0249 t=+4.3
4h bd_imb_2: pooled ic23=+0.034 ic24=+0.052 ic25=+0.029 pool=+0.0400 t=+6.9
4h bd_depth_rel_7d: pooled ic23=-0.016 ic24=-0.031 ic25=-0.026 pool=-0.0251 t=-4.3
4h bd_chg_bid_15: pooled ic23=-0.036 ic24=+0.008 ic25=+0.001 pool=-0.0092 t=-1.6
4h bd_chg_bid_60: pooled ic23=+0.002 ic24=+0.010 ic25=-0.002 pool=+0.0043 t=+0.7
interesting: bd_imb_1, bd_depth_rel_7d, bd_chg_bid_15, bd_chg_bid_60
bd_imb_1 persym: BNB=-0.027 BTC=-0.068 ETH=-0.053 SOL=+0.002 XRP=+0.007 all5_same_sign=False
bd_imb_2 persym: BNB=+0.001 BTC=-0.064 ETH=-0.030 SOL=+0.025 XRP=+0.037 all5_same_sign=False
bd_depth_rel_7d persym: BNB=-0.132 BTC=-0.183 ETH=-0.134 SOL=-0.319 XRP=-0.082 all5_same_sign=True
bd_chg_bid_15 persym: BNB=-0.093 BTC=-0.048 ETH=-0.063 SOL=-0.126 XRP=-0.020 all5_same_sign=True
bd_chg_bid_60 persym: BNB=-0.157 BTC=-0.065 ETH=-0.054 SOL=-0.187 XRP=-0.049 all5_same_sign=True
