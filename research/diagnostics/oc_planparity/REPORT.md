# oc_planparity — does the LIVE plan equal the research computation? (2026-10-06)

Verdict: **PARITY** — 0 mismatches on every checked field (see `results.json`).

## Plans checked (latest 1 per phase + merged; history exists so no snapshot was needed)
- `trade_plan_v376_s0`: decision 2026-10-06 08:00Z, generated 08:04:42Z (t_s 04:00, books r 04:00 logged 08:02)
- `trade_plan_v376_s1`: decision 2026-10-06 09:00Z, generated 09:01:25Z (t_s 05:00, ffill from r 04:00)
- `trade_plan_v376_s2`: decision 2026-10-06 06:00Z, generated 06:01:12Z (t_s 02:00, ffill from r 00:00 logged 04:02)
- `trade_plan_v376_s3`: decision 2026-10-06 07:00Z, generated 07:01:08Z (t_s 03:00, ffill from r 00:00)
- merged `trade_plan_v376`: decision 09:00Z, net -0.15% (= mix mean of the four sub-books)
- Plan history lives in: backend SQLite kv `trade_plan_v376*` (read here with `mode=ro` SELECT only) +
  the five artifact files above (per-phase s0..s3 + merged). File and kv agree on all four phases.

## Research path recomputed (causal: only shadow rows with index <= t_s)
- Books: `scripts/forward_v205.live_books(v240_O1 / v285_CB)` -> `0.8*O1 + 0.2*CB` on the common
  index, `forward_trade_phase.books_on_grid` ffill to the shifted decision row (identity at s=0).
  All four phases match to < 1e-6 (s1/s2/s3 correctly reuse the older standard row).
- Book SL/TP: positions satisfy m_sl=4 / m_tp=8 exactly (TP leg = 2x SL leg, ratio 2.0, sigma_rel 0).
  No pending open orders exist in these four plans, so no entry-limit comparison was applicable.
- Dips: RUNGS 2.5/3/3.5/4/5; inverted sigma_4h reproduces every buy_limit/TP/stop/backstop to 0 ticks
  (TP = buy*(1+agent_tp*sg), stop = buy*(1-4*sg), backstop = buy*(1-8*sg)); size_frac/agent_size
  spread 0.0; `data_check.max_rel_diff_1h_vs_1m` = 0.0 (B1 opens agree).
- Merged: local `multiphase.merge` mirror (cap = 0.25*growth/mix) reproduces merged target_weights
  and net_return_pct exactly (e.g. BTC 0.18038179).
- Tolerances: weights abs > 1e-6, prices > 1 tick (BTC 0.1 / ETH 0.01 / BNB 0.1 / SOL 0.01 / XRP 0.0001),
  sizes rel > 1%. Nothing exceeded them.

## Mismatches
None. (An empty list is the result, not an omission — every comparison above ran and passed.)

## Expected overlays that are NOT plan mismatches (runner-side, by design)
- `--bear-book`: plan holds pre-bear weights (v376 has no bear halving); the bot halves book LONGs
  when `is_bear` (BTC 4h open < mean of last 1200, min 600). No halving is baked into these plans.
- `--corr-size`: plan `size_frac` is pre-corr (x1.0); the bot multiplies by 1/(1+n) flushing peers.
- `--dip-mult`: plan is x1.0; deployment scales dip qty only (1.7), admission unchanged.
- `--dip-gross-cap`: plan lists the uncapped ladder; the bot caps open+risk notional per phase (2.0).
- Data source: plan books/market come from Binance USD-M public klines; live trading executes on
  Bybit (maker 0.02% / taker 0.055%, tick/latency at execution, not in the plan). No Bybit-vs-Binance
  price substitution was found inside the plans.
- Rounding/timing/stale rows: file-vs-kv timestamps equal; shadow rows used were logged 2+ min
  before each plan (tightest: 04:00 row logged 08:02:04Z for the 08:04:42Z s0 plan); no stale-leg case
  (common index == both legs' latest in all four phases).

## Reproduce
`.venv/Scripts/python.exe research/diagnostics/oc_planparity/check_parity.py`
(writes only `results.json` here; read-only elsewhere; no network/engine/DB writes; < 0.4 GB, no heavy_slot).
`.venv/Scripts/python.exe -m pytest tests/test_oc_planparity.py -q`
