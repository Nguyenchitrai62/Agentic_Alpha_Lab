# BTC swing research v4 — completed, not approved for live use

Run date: 2026-09-05. Latest user scope: profitable trading-support pipeline,
1–4 useful alerts/month, reversal/pullback opportunities, 3–7-day holding;
maximum acceptable drawdown raised to20%. This is a research screen, not a promise.

## Outcome first

A frozen **ExtraTrees + five-timeframe feature + bracket-selection pipeline** was
profitable on the reserved April–July2026 historical interval. It is NOT a successful
Kronos fine-tune and NOT evidence of reliable profit: only one trade filled.

| Evaluation | Capital100 becomes | Net | Close-sampled maxDD | Filled trades |
|---|---:|---:|---:|---:|
| v3 first holdout, fixed1x | 85.2165 | -14.7835% | 23.2150% | 9 |
| v3 first holdout, exposure0.5–1x | 91.2537 | -8.7463% | 13.3887% | 9 |
| v4 reserve, fixed1x | 105.1135 | +5.1135% | 4.2228% | 1 |
| v4 reserve, fee stress0.055%/fill | 105.0416 | +5.0416% | 4.2243% | 1 |
| v4 reserve, exposure0.5–1x | 102.5567 | +2.5567% | 2.1205% | 1 |

The reduced-exposure comparison was declared before testing; it only reduces risk,
never exceeds1x. Tree disagreement is NOT calibrated confidence. No leverage boost.
These intervals/models differ; the table is a research ledger, not an apples-to-apples
claim that v4 beats v3 out of sample.

v4 gross PnL5.356379, fees0.041071, long funding0.201815, net5.113493
(capital100 units). One long, zero shorts, zero simulated liquidations. PF undefined.
The single win does not justify quoting100% as an estimated future win rate.
Three alerts from460 decisions: April0, May0, June3, July0. Two unfilled/rejected.
Thus the desired1–4 alerts in each month is not met; do not lower the threshold using
this test just to meet frequency. No forced minimum trades.

`check_swing_acceptance.py` passes return, fee-stress, DD and maximum-frequency
checks, but FAILS provisional30-fill and12-month evidence floors. Passing those
floors in future would still not establish statistical significance or live safety.

## What actually ran

1. Kaggle `nguynchtrai/kronos-btc-swing-base-20260905-v2` completed on2 Tesla T4.
   All12 pretrained trunk blocks were fine-tuned; tokenizer frozen. Approximately
   99.86M trainable parameters; all block-update probes changed. Best epoch1,
   early stopped3, runtime423.87s. Validation308/policy304 decisions all WAIT.
   Reports/predictions downloaded, full weights not yet downloaded. See
   `SWING_TRAINING.md`; no duplicated GPU job is running.
2. Same-policy tree comparator looked positive on development. It was exported
   before a first holdout, 2025-12-09 through2026-03-23 exclusive. It FAILED as
   shown above. This interval became development for v4, not independent evidence.
3. Extended immutable BTC futures5m source back to2022-01-01, including an earlier
   market cycle.492025 candles through2026-09-05 10:04:59.999UTC; source validation
   found no gaps, duplicates or invalid candles. Never filled missing bars silently.
4. Built5628 development examples from2022-05-09 through2026-03-15; full label
   windows end before2026-03-23. Daily128-bar warmup, closed5m/15m/1h/4h/1d only.
5. Ran12 declared configurations across5 purged chronological walk-forward folds:
   two ExtraTrees sizes, three gates, two expected-net thresholds.8-day embargo
   between training-label end and each evaluation start, full3/7-day labels.
6. Selected on development only:100 trees, depth8, leaf20, max_features0.8,
   seed1729, **no explicit regime gate**, minimum expected net0.6%, fill score0.25.
   Trend and confirmed-reversal/pullback rules were tested but not selected.
7. Froze weights/config/source hashes before opening reserve2026-04-01 through
   2026-08-01 exclusive ONCE. Last holding windows are purged, not truncated.
   The result above was not used to tune v4.

Development fold net returns: +1.8784%, +12.0018%,0%, -2.5443%, +6.8046%.
18 total fills;3/5 positive folds, one WAIT fold, one losing fold; worstDD16.3349%.
Mean fold net3.6281% is neither annualized nor a compounded continuous portfolio.
The development screen is weaker than the final evidence screen. Selection over
12 candidates introduces selection bias; do not treat development as a new test.

## Model output and execution

40 causal features (8/frame) capture returns, distance from rolling high/low,
range, moving-average trend and relative volume. Two multi-output ExtraTrees
forests estimate unconditional net payoff and OHLC fill fraction for16 brackets.
Ranking considers net after the user's cost assumptions; no calibrated probability
of reversal, win, maker fill or future drawdown is available.

Bracket grid: long/short × entry offset0.5/1.5 ATR5m × two SL/TP grids based on
ATR4h (with1% price minimum unit) ×3/7-day holding. TP1 exits50%, TP2 remainder.
Prices are deterministic geometry around current price/ATR, not learned free-form
price levels. Trees choose the bracket, WAIT gate selects whether to alert.

Historical replay only, signal2026-06-09 00:04:59.999UTC:

- LONG entry limit62923.9714, SL59606.5071, TP1 66241.4357, TP2 69558.9000.
- Entry eligible from00:05UTC, actual fill00:20UTC;7-day maximum holding.
- Trade exited2026-06-16 00:20UTC by timeout after partial TP1.
- This is NOT a current trade recommendation.

Every6 hours at00:04:59.999/06:04:59.999/12:04:59.999/18:04:59.999UTC.
Entry valid12 subsequent5m candles; cooldown5 days, max4 alerts/UTC month,
no overlapping positions. Inference CLI enforces the decision clock. Optional
state applies cooldown/quota/open-position blocking but is read-only: a caller
must maintain alerts/positions and pending orders. Without state output is a
candidate, not a complete paper execution service. No orders are sent.

Equity compounds from100. Fee0.02% each fill; long funding0.01% atUTC00/08/16
on held notional, short funding0. TP/entry use OHLC limit-touch proxies without
queue priority. Stops/timeout are market-like at scenario fee, not guaranteed maker
fills. Stop-first ambiguity handling, entry-candle target suppression, no mark-price
data. DD is candle-close sampled, not exchange mark/intrabar maximum loss.
Fee stress does NOT test adverse slippage, gaps, queue nonfills or liquidation fidelity.

## Immutable artifacts and audit

Local, Git-ignored (do not upload publicly or commit):

- `data/processed/btc_2022_2026_source_v1`: source manifest and candles.
- `data/processed/swing_regime_research_v4`:5628 development examples, config,
  manifest, fold plan, candles and decisions; reserve excluded.
- `artifacts/research/swing_regime_search_v4`: all fold results, leaderboard,
  frozen `checkpoint/forests.npz`, `forests.json`, `metadata.json`.
- `artifacts/evaluations/swing_tree_v3_first_holdout`: failed v3 evidence, preserved.
- `artifacts/evaluations/swing_v4_reserve`: reports, predictions, signals, trades,
  evaluation manifest and separate `replay_audit.json`.

Source candles SHA256:
`7043e22a0608a59c0d944036ccf70cd0eb3f018c53691a3fd4b1c9e13cfaba3d`.
v4 forest SHA256:
`28f808529b78c101d370730881d9b9f1faaadb410580db442d5e877e10bb8237`.

Safe JSON/NPZ export, no pickle; portable inference matched sklearn predictions.
43 tests pass. Separate audit verified source/metadata hashes and replayed all3
held-out alerts including candidate ID, entry, SL, both targets and holding horizon.
Frozen source is unchanged. No historical report was overwritten.

**Bootstrap limitation:** original v4 report resampled one identical trade2000
times, producing degenerate equal quantiles. They are NOT confidence bounds and
must not be displayed as evidence. Separate audit records this; future evaluator
now suppresses bootstrap quantiles below6 trades. Six trades still do not establish
valid confidence. Existing report retained to preserve the experiment record.

## Reproduce from this workspace

From repo root PowerShell, with existing ignored artifacts:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/check_swing_acceptance.py --report artifacts/evaluations/swing_v4_reserve/report.json
.\.venv\Scripts\python.exe scripts/infer_tree_pipeline.py --checkpoint artifacts/research/swing_regime_search_v4/checkpoint --candles data/processed/btc_2022_2026_source_v1/candles.parquet --as-of 2026-06-09T00:04:59.999Z
```

`--state path.json` accepts `{"alert_times":[],"position_open":false}` for known
empty historical state only. Do not fabricate empty state for a running strategy.
Use timezone-aware past alert timestamps. Live candle freshness is NOT verified
by this offline CLI. Dashboard still shows older demo/model snapshots, NOT v4 results.

Fresh clones do not contain source data or trained weights. Read `NEXT_AGENT.md`
for environment setup, then download/build into NEW output folders using
`extend_btc_history.py`, `build_swing_research.py`, `search_regime_pipeline.py`.
Their `--help` lists arguments; base snapshot setup is in `COLAB_3Y_STATUS.md`.
Do not overwrite immutable datasets or call a replay of already-opened dates
independent validation. Kaggle credentials stay outside Git.

## Honest next step

The predeclared reserve is now opened. Later Aug/Sep historical data was already
inspected in prior research. There is no remaining declared pristine holdout in
this research plan. Do not repeatedly tune and test until the same history looks good.

Keep v4 frozen as a paper comparator; pre-register genuinely new forward dates
and record decisions before outcomes exist. No scheduled collector or automatic
paper execution has been started. More history, mark/index/funding/basis/OI data
and execution stress can be developed separately, with causal availability checks.
Larger neural architectures may be compared on development, but parameter count
alone is not evidence; no larger-than-base model was trained in this iteration.
The scarce effective sample of multi-day events, sparse fills and imperfect
execution model remain unresolved. No deployable high-profit/low-risk model yet.
