# oc_liqcheck SUMMARY (descriptive only, no rule)

- Store 2026-10-04→10-06: 3,230 liq rows (binance 2,277 / bybit 953); all 5 majors × both venues × 3 days present.
- Gaps >5min: 10-04 05:29→12:45 (7.26h) + 10-05 12:58→17:40 (4.70h outage); 10-06 clean; topbook gaps match exactly.
- Quality: 0 dups, 30/30 files event_time-monotonic, side/raw/price/qty/notional fully consistent; recv−event lag +506ms binance / −327ms bybit (clock drift).
- Top burst 10-04 15:04 ETH $5.64m (single $5.63m short); rest are binance BTC $0.49–1.60m; ±30min paths all within ±0.5%.
- Hourly top: ETH 10-04 15:00 $5.66m, BTC 10-05 06:00 $2.83m; nothing selected, nothing sized.
- Ready for walk-forward (>=3 months + several 2.5σ flushes): earliest 2027-01-04; recount flushes on covered time then.
- Verdict: HEALTHY but infant — monitoring only.
