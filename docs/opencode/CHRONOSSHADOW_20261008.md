# Chronos C2 shadow log (prospective Chronos-Bolt-small dip tilt, 4 clocks x 5 majors, hourly)

- What: `scripts/chronos_shadow.py --once` logs one row per (sym, shift, T) whose
  4h bar opened in the last hour (5 rows/run; `--backfill-hours N` labels N
  hours as backfill, never prospective). Settings identical to
  `research/tournament/oc_chronos/run_chronos_4shift.py` (amazon/chronos-bolt-small
  pinned at HF snapshot revision 772f3d25d38aec6d914c8949dab4462e2d46f5d8, ctx 512x4h
  log closes, H=1, quantile heads 0.1..0.9, deterministic; imports chronos from
  oc_chronos/pylib; frozen anchor-2026 C2 fit direction +1, q20 1.0765874390,
  q80 2.5955569464, hi/lo 1.25/0.75).
- Venue: Binance USD-M public 1h klines aggregated to 4h (same venue and
  OHLCV+quote-volume convention as `build_bars_4shift.py` -> NO venue difference).
- Output: `artifacts/research/chronos_shadow/chronos_features_live.parquet`
  (sym, shift, T, ch_q10/ch_q50/ch_q90, sigma, C0, c2_mult + k2_mult copy,
  model_sha, logged_at, mode, is_prospective). k2_mult is an exact copy of
  c2_mult so the existing bot flag --k2-tilt reads it with no code change.
  PROSPECTIVE iff logged_at - T <= 30 min. Idempotent on (sym, shift, T).
- Parity (research/tournament/bot_c2shadow/chronos_parity.parquet, 2760 rows
  2026-09-01..2026-09-23; parity_report.json): vs oc_chronos parquet on
  (sym, shift, T) — bars C0 exact (0.0), sigma max 4.3e-16, ch_q max 1.3e-4 /
  mean ~4.5e-6 (GPU batch-size reduction order only); multiplier with the
  anchor-2025 fit matches the research one exactly (2745/2745; 15 late-shift
  rows have no research counterpart since that table ends 2026-09-23 20:00).
- Leader start (loop like the kronos loop; 10 min is fine, idempotent per bar):
  `while 1; do .venv/Scripts/python.exe scripts/heavy_slot.py run --tag chronosshadow --min-free-gb 2.0 -- .venv/Scripts/python.exe scripts/chronos_shadow.py --once; sleep 600; done`
  (run with nohup in the background; never starts the paper runner itself).
- Paper runner (needs no code change; backfill rows map to 1.0, only
  prospective/late rows tilt):
  `python -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --k2-tilt artifacts/research/chronos_shadow/chronos_features_live.parquet --tag d17bfg2ch`
- GPU (GTX1650) when available else CPU; elapsed per row/run printed.
- Offline eval (after >= 8 weeks): join prospective rows to the paper runner's
  dip fills by (sym, shift, T); compare sum(c2_mult x rung P&L) vs sum(rung P&L)
  at equal average exposure (divide by mean c2_mult first).
- Verify: `.venv/Scripts/python.exe scripts/chronos_shadow.py --once --dry-run`
  then `.venv/Scripts/python.exe -m pytest tests/test_chronos_shadow.py -q` (6/6).
  Do not start the loop or the runner yourself.

## Tom tat tieng Viet
- Shadow C2 chay song song, ghi nhan xac suat truoc moi bar 4h de kiem chung prospective cho paper runner.
- Parity khop nghien cuu (bar/sigma chinh xac, multiplier khop 100%), mo hinh ghim dung revision.
- Chua adopt tilt; cho du lieu prospective moi ket luan.
