# OpenCode task oc_optctx: options skew / put-call flow / Coinbase premium as dip-rung context (beyond DVOL)
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md and research/tournament/RULES.md. Write ONLY under research/tournament/oc_optctx/
(+ tests/test_oc_optctx.py); no commits; no edits of leader files; data up to 2026-09-24 00:00 UTC; one light process.
Data: data/raw/deribit_opt_20260926/BTC_options_4h.parquet and ETH_options_4h.parquet (columns bar, call_buy, call_sell, put_buy, put_sell,
n_trades, iv_otm_put, iv_otm_call; read research/mj/fetch_deribit_options_4h.py to confirm whether `bar` is the 4h bar START - then the row is
usable only from bar + 4h), data/raw/coinbase_20260925/BTC-USD_1h.parquet (Coinbase spot) vs Binance BTCUSDT 1h (data/raw/btc_intraday_20260924
or research/tournament/ext/hourly_ext.parquet), dip rungs research/tournament/ext/fills_U_ext.parquet (majors R2 rungs; T = t_fill - f min).
DVOL z90 from research/tournament/oc_dvol/dvol_hourly.parquet (definition in research/tournament/oc_dvol/PLAN.md).
PLAN.md first. Features at a rung's bar open T (data available strictly before T): skew = iv_otm_put - iv_otm_call (last complete 4h bar) and
its z-score vs the trailing 540 bars (90 days); put-buy share = put_buy / (put_buy + call_buy) over the last 6 complete bars, z vs 90 days;
Coinbase premium = Coinbase close / Binance close - 1 at the last complete hour, mean over the last 24 hours, z vs 90 days. Tests per anchor year
2021..2025 (BTC features for every major; also ETH options for ETH rungs): Spearman IC with y1.0; leave-one-year-out tercile spread (cut-offs from
the other years); and the INCREMENTAL IC after regressing out DVOL z90 (residual IC, same tests). Decision: PROMISING only if IC sign same in
>= 4/5 years AND LOYO spread sign in >= 4/5 AND residual IC sign same in >= 4/5. REPORT.md + results.json, one-line verdict per feature.
