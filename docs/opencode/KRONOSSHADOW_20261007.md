# Kronos shadow log (prospective K2 features, 4 clocks x 5 majors, hourly)

- What: `scripts/kronos_shadow.py --once` logs one row per (sym, shift, T) whose
  4h bar opened in the last hour (5 rows/run; `--backfill-hours N` labels N
  hours as backfill, never prospective). Settings identical to
  `research/tournament/oc_kronoshidden` (Kronos-small, ctx 400x4h, S=64,
  T=1.0, top_p 0.9, hash seed per row; fits.json anchor-2025 K2 1.25/0.75).
- Venue: Binance USD-M public 1h klines aggregated to 4h (same venue and
  OHLCV+quote-volume convention as `build_bars_4shift.py` -> NO venue difference).
- Output: `artifacts/research/kronos_shadow/kronos_features_live.parquet`
  (sym, shift, T, sigma, C0, 8 feats, k2_mult, model_sha, logged_at, mode).
  PROSPECTIVE iff logged_at - T <= 30 min. Idempotent on (sym, shift, T).
- Leader start (loop like the carry loop; 10 min is fine, idempotent per bar):
  `while 1; do .venv/Scripts/python.exe scripts/heavy_slot.py run --tag kronosshadow --min-free-gb 2.0 -- .venv/Scripts/python.exe scripts/kronos_shadow.py --once; sleep 600; done`
- GPU (GTX1650) when available else CPU; elapsed per row/run printed.
- Offline eval (after >= 8 weeks): join prospective rows to the G2 paper
  runners' dip fills by (sym, phase, bar); compare sum(k2_mult x rung P&L) vs
  sum(rung P&L) at equal average exposure (divide by mean k2_mult first).
- Verify: `.venv/Scripts/python.exe scripts/kronos_shadow.py --once --dry-run`
  then `.venv/Scripts/python.exe -m pytest tests/test_kronos_shadow.py -q`.
