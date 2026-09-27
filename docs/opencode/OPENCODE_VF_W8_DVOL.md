# vf W8: options implied volatility (Deribit DVOL) for BTC (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/implied_vol.py`, `tests/test_vf_implied_vol.py`,
`research/vf/implied_vol_study.py`, `artifacts/research/vf/implied_vol/*`,
`data/raw/dvol_20260924/*` (all downloads/temp here; never write outside the workspace).
Data: Deribit public API (no auth)
`https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp=<ms>&end_timestamp=<ms>&resolution=3600`
(returns [ts, open, high, low, close]; paginate by time, <= 1000 rows per call, sleep 0.2s).
Fetch 2021-03-24 (DVOL start) .. 2026-09-24 hourly. Save parquet + manifest with hashes.
A DVOL hourly candle is available at ts + 1 hour.
compute(): DVOL level, 1d/7d change, z-score vs 90d, DVOL minus realized vol
(30d, annualized, from BTC bars as-of), DVOL term proxy none; ratio DVOL / 30d RV.
events(): implied-vol spike (DVOL z > 2 -> +1 contrarian and separately -1 panic
continuation as two columns), IV-RV spread extreme high (+1) / low (-1),
DVOL crush after spike (+1). Event study on 1h/4h/1d.
