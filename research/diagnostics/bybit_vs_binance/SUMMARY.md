# Bybit vs Binance 1m: is Bybit execution materially different? No (one BNB caveat).
Data: Bybit linear 1m 2021-06-01..2026-10-03 last closed minute (BTC/ETH/XRP full range; BNB from 2021-06-29; SOL from 2021-10-15), 13.9M bars, zero in-range gaps; sha256 per file in data/raw/bybit_linear_1m_20261004/manifest.json.
Basis (bybit/binance-1, full overlap): median close within ±1.7 bps in every symbol-year except BNB (2025: -5.0, 2026: -10.1 bps persistent Bybit discount); tails ±14 bps (2021) tightening to ±2-3 bps (2026 BTC/ETH).
Minutes with |close basis| > 5 bps: ~0.3% (2021) -> <0.02% (2025-26), except BNB 2026: 89.7%.
Fills, dev-only (t < 2025-09-14, 7574 fills): Bybit trades through the same limit 83-84% same minute (book) / ~90% (rung), ~90%/94% within t+2, 96.5-97.6% by expiry (book 60 min, rung 240 min); 209 fills (2.8%) never trade through on Bybit.
M5: book 83.8/89.9/96.5% (27 missed of 782), rung 90.2/94.0/97.4% (39 of 1482); R2: book 82.8/90.3/97.6% (24 of 1014), rung 90.4/94.0/97.2% (119 of 4296).
Stops/TPs same minute (dev): book_stop 88.7% (Binance itself 100%), book_tp 89.4% (100%), rung_tp 94.9% (100%), rung_sl 89.6% (Binance 87.4% — recorded exit-fill prices, not trigger levels).
Coverage 100%: every dev fill/stop/TP minute exists on Bybit; Binance self-check is 100% on fills, book stops and TPs, validating minute alignment.
Reading: entries differ only by delay — ~9 in 10 agree within 2 min, ~97 in 100 by expiry; stops/TPs agree ~9 in 10 same-minute. Not material vs 4-8 bps round-trip costs.
Caveat: BNB trades ~10 bps cheaper on Bybit through 2026 (buy limits fill easier, sell limits harder); treat BNB limit levels as venue-specific.
Repro: research/diagnostics/bybit_vs_binance/compare_bybit_binance.py -> basis_by_symbol_year.csv, execution_agreement.csv, agreement_summary.json.
