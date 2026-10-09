# oc_k2parity — DIFF (code-path comparison, no outcomes)

Live = scripts/kronos_shadow.py (functions build_shift_bars, select_context,
compute_sigma, infer_one, seed_for, assign_k2, frozen_fit, model_sha).
Research = research/tournament/oc_kronoshidden/{build_bars_4shift.py,
run_inference_4shift.py, tilt_rule.py, fits.json} + kronos_fast.py (shared).

## 1. Data source
- Research bars: local 1m klines (Binance USD-M): alts
  data/raw/majors_intraday_20260924/{SYM}_1m_{YYYY}.parquet, BTC
  data/raw/btc_intraday_20260924/klines_1m_{YYYY}.parquet. Aggregated 1m -> 4h.
  Venue Binance USD-M (same as live, so no venue difference by construction).
- Live bars: Binance USD-M public 1h klines via GET fapi.binance.com/fapi/v1/klines
  (interval=1h, paged limit 1500, retry 6x, rate-limit 0.21s), plus /fapi/v1/time
  for server_ms. Aggregated 1h -> 4h. Same OHLCV+quote_volume convention
  (amount = quote_volume sum), but a different aggregation level (exchange 1h
  close vs local 1m sum). Rounding / late-trade corrections can differ at 1e-6..1e-4.

## 2. Bar construction per shift
- Grid identical: T_s = floor((open_time - s h)/4h)*4h + s h, s = T.hour % 4.
  Research (build_bars_4shift.py): group 1m by T, open=first, high=max, low=min,
  close=last, volume=sum, amount=quote_volume sum, nmin=count. Drops only the
  trailing incomplete bar per (sym,shift); interior nmin<240 only 3 rows
  (SOL listing Sep 2020), none in Sep 2026.
- Live (build_shift_bars): same groupby on CLOSED 1h rows only
  (closed = close_time < server_ms; caller enforces bars closing <= T by using
  only closed rows), n_h=count, requires n_h==4 downstream. Uses ONLY closed rows;
  research uses 1m up to last complete 4h bar (1m ends 2026-09-23 23:59 ->
  last complete T 2026-09-23 20:00 shift 0; shifts 1/2/3 end 17/18/19:00).
- open_T: research sigma uses b.open[e] (the forecast bar's own open from 1m).
  Live uses the 1h open at exactly T (hit = open_time==T) else fallback
  ctx close last. Same concept (bar open known at T), different source cell.

## 3. Context length / last bar used
- Both P=400. Research: for forecast index e (b.T[e]=T), context = rows e-400..e-1
  (400 bars with T'<T); C0 = close[e-1]; y-stamps = T + 0,4,...,20h.
- Live: select_context = last 400 rows with T'<T AND n_h==4; C0 = ctx close last;
  y-stamps = T + 0,4,...,20h. Identical when bars match and all n_h==4 (true in
  Sep 2026). No lookahead in either (rows with open >= T excluded).

## 4. Sigma window
- Both SIG_WIN=360, pandas rolling(360).std() (sample, ddof=1) over log-open diffs
  INCLUDING the diff to the forecast bar's own open:
  research sig[e] with lo=log(b.open); live compute_sigma/infer_one with
  opens=[ctx.open..., open_T]. Same math; values differ only via input opens.

## 5. Normalisation / sampling / device
- Per-window z-norm identical: m,s = mean/std (numpy ddof=0) over the 400x6 window,
  xn=(x-m)/(s+1e-5), clip to [-5,5] inside kf.sample_paths (default clip=5,
  neither path overrides). Denorm out*(s+1e-5)+m in float64. Same.
- Sampling identical: H=6, S=64, TEMP=1.0, TOP_P=0.9, TOP_K=0, fp32 in / float64
  feature math. Same kronos_fast.sample_paths code (live imports it from OC).
  Batching differs only: research B=32 batched, live B=1 per row. Math is
  batch-independent; RNG stream position differs (see seeds).
- Device: research dev="cuda:0" hard-coded. Live device="cuda:0" if available else
  cpu. Same on this host (cuda available). CPU fallback would change numerics
  slightly (not used here).

## 6. Seeds (the intended difference)
- Research: torch.manual_seed(1234) once; sequential draws across batches/groups.
  Leader resume note (REPORT.md): run killed after 18/20 groups; XRP shifts 2-3
  recomputed in a resumed process with a DIFFERENT RNG stream (sampling noise only).
  So the research file itself mixes two RNG streams.
- Live: seed_for(sym,shift,T) = sha256("{sym}|{shift}|{T-iso}|{MODEL}|S64|T1.0|p0.9")
  first 8 hex chars; torch.manual_seed(seed)+cuda seed per row. Fully reproducible
  per row, independent of order. Different from research by design -> Monte-Carlo
  noise expected even with identical bars. The MC-baseline step quantifies it.

## 7. Model revision
- Both MODEL="NeoQuasar/Kronos-small", TOKENIZER="NeoQuasar/Kronos-Tokenizer-base",
  loaded from the same OC/model/ + kronos_fast.py files (live imports them).
  Live records model_sha = sha256(MODEL + bytes of kronos_fast.py, model/kronos.py,
  run_inference_4shift.py)[:12]. Research records no sha. Drift check at runtime
  (check_model_id) warns if MODEL strings differ. Weights come from the HF hub
  cache in both cases (no local weight files in OC/model/).

## 8. Frozen q20/q80/direction (assign_k2 vs fits.json anchor 2025)
- fits.json "2025-09-24": direction=1, q20=0.5872428352509342, q80=2.182801599162049.
- Live FROZEN constants identical; frozen_fit() asserts equality to 1e-12 at runtime,
  falls back to constants if file unreadable. K2 hi/lo=1.25/0.75 both sides.
- assign_k2(low1) == tilt_rule.assign_mult(-low1): risk=-low1; direction>0:
  risk>=q80->hi, risk<=q20->lo else 1.0; NaN->1.0. Boundary inclusive both sides.
  No difference.

## 9. Other (labelling only, not features)
- Live adds logged_at, mode (backfill when --backfill-hours>0 else
  prospective iff logged_at-T<=30min else late), is_prospective, model_sha.
  Research has none. Backfill rows are never prospective by construction.
- Live done_keys idempotence on (sym,shift,T); research resume on (sym,shift) groups.
- Research START=2020-08-01 + E>=P + finite-sigma filter; live len(ctx)>=400 +
  finite sigma>0. Equivalent in-window.

## Summary of expected parity gaps
Expected identical: grid, P/H/S/T/top_p/top_k, norm/clip, sigma formula, C0 def,
stamps, fits/thresholds, denorm/feature formulas. Expected noise: per-row seeds
(+ research XRP s2-3 resumed stream) -> low1/k2_mult MC scatter. Suspect systematic
risk: 1m-aggregated vs exchange-1h-aggregated OHLC (incl. open_T cell) -> sigma/low1
bias if bars differ; incomplete-bar handling at the Sep-23 edge (research drops
trailing incomplete; live with Oct server time sees them complete).
