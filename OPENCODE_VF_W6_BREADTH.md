# vf W6: alt-market breadth and cross-asset lead/lag for BTC (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/breadth.py`, `tests/test_vf_breadth.py`,
`research/vf/breadth_study.py`, `artifacts/research/vf/breadth/*`. Prefix `brd_`.
Data: `data/raw/xasset_20260924/{SYM}_{4h,1d}.parquet` and `_funding.parquet`
for ETH, BNB, SOL, XRP, ADA, DOGE, LINK, LTC, BCH, TRX (USD-M, same columns as
BTC bars). Align to the BTC bar by close_time (as-of; an alt bar counts only
if its close_time <= the BTC bar close_time); missing symbols before listing
are excluded from the denominator.
compute(): fraction of alts above EMA50/EMA200, fraction in 4h EMA20/200
ribbon uptrend/downtrend, median alt return 1/6/42 bars minus BTC return
(relative strength), ETH/BTC ratio trend (EMA distance), dispersion of alt
returns, mean alt funding z-score, count of alts at 55-bar highs/lows.
events(): breadth thrust (fraction above EMA50 crosses up 0.7 -> +1, down 0.3
-> -1), ETH/BTC breakout, alt funding crowding (-1), BTC-alt divergence
(BTC new 55-bar high while < 30% alts at highs -> -1). Event study on 4h/1d.
