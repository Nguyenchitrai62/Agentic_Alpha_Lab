# Temporal BTC models: development results, 2026-09-05

Status: v13/v14 complete; v15 continuous evaluation running. No live approval.
Read `RESEARCH_RUN_LOG.md` for the authoritative latest process status.

## What changed

v13 learns directly from128closed OHLC/volume candles on each of5m,15m,1h,4h,1d.
An8-candle patch encoder and sharedGRU learn temporal order, then macro features
gate micro entry context. Candidate interaction heads score16 long/short
entry/SL/TP1/TP2/holding choices.40,707trainable parameters, fixed16epochs,
3seeds; train-only normalization,730day trailing history,8day label-end embargo.
This is learned bracket selection, not a hand-coded directional trading rule.
It does not produce a calibrated reversal probability or maker fill probability.

Individual seeds still failed the registered eight-fold stability screen.
v14 combines unconditional payoff forecasts from ALL3seeds, without selecting the
best seed. Both the simple mean and a fixed1std disagreement penalty were retained.
All24saved checkpoints passed hash verification and replay of all7,788seed-decision
forecasts onCPU; maximum absolute difference0.000038743014 againstGPU forecasts.

## Correct capital/risk interpretation

The mean ensemble's average fold return was+6.2321%, but it is NOT a single
compounded portfolio return. Its worst scenario per-fold drawdown14.4224% also
does NOT establish a20% portfolio drawdown limit. Replaying frozen signals with
capital carried across those evaluation intervals gives the following:

| Mean ensemble scenario | Capital100 ends at | Net return | Global close-sampled DD | Filled trades |
|---|---:|---:|---:|---:|
| 1x, requested fees/funding |154.3990|54.3990%|23.9068%|57|
| 1x, higher fees |148.3873|48.3873%|24.7050%|57|
| 1x, adverse execution |135.2895|35.2895%|20.5281%|48|
| 0.5x, requested fees/funding |125.6370|25.6370%|12.6895%|57|
| 0.5x, higher fees |123.1593|23.1593%|13.1445%|57|
| 0.5x, adverse execution |117.4605|17.4605%|10.7955%|48|

Exposure0.5x means position notional is half current equity, not a confidence
estimate. This is a post-v14 risk baseline, not a parameter selected on an unseen
test. No leverage was added. Normal0.5x gross29.0537 capital points minusfees1.2226
andfunding2.1941 gives net25.6370.1x gross61.9058 minusfees2.6192 andfunding4.8876
gives net54.3990. Normal winrate50.8772%,57fills:33long/24short.

Crucially, capital is FLAT in the gaps between the original eight evaluation
intervals. This is not full continuous trading from2023 to2026; do not annualize
it as such. The original6/8jointlypositive fold screen still fails(5/8).
The disagreement-penalty branch is weaker:0.5x normal+7.5217%,DD16.9288%; its1x
normal drawdown31.4262% fails. Its results are preserved, not discarded.

## Costs and limitations

Entry/exit fee0.02% per fill, long funding0.01% perUTC8h boundary, shortfunding0.
Higher-fee scenario charges0.055% each fill. Executionstress uses5bps entry/target
penetration,5bps market-exit slippage,0.055% market-exit fee, no favorable limit
gap-price improvement. SL/timeout are market-like, not guaranteed maker orders.
OHLC penetration is not order queue modelling. Drawdown is not exchange mark or
true intrabar drawdown; adverse-price diagnostics have their own caveats.

All data here are opened development. No inference about guaranteed future profit,
optimal architecture or statistical independence follows from these results.
Neural seeds, overlap in3–7day labels, regime shifts and low sample count matter.

## v15: next registered check

Keep the architecture,16epochs,3seeds, costs and signal thresholds fixed. Refit at
11contiguous quarterly boundaries from2023-06-01. Predict all4,076available6h
decisions until2026-03-15 18:04:59.999UTC, excluding only the final immature-label
tail before the2026-03-23 data cutoff. No quarter-end prediction gaps.

Assemble forecasts first, then apply one monthly alert count, cooldown, open-position
exclusion and compounded equity state across the whole interval. Model updates
do not close existing positions or reset capital. Preserve both ensemble branches
and exposures1x/0.5x. Fold-local training reports are diagnostics, never the final
continuous result.33weights/replay bundles are saved.105tests passed before run.

Artifacts (ignored byGit):

- `artifacts/research/swing_v13_temporal_20260905/summary.json`
- `artifacts/research/swing_v14_temporal_consensus_20260905/summary.json`
- `artifacts/research/swing_v14_portfolio_audit_20260905/summary.json`
- `artifacts/research/swing_v14_half_exposure_audit_20260905/summary.json`
- `artifacts/research/swing_v15_continuous_20260905/continuous/summary.json` (pending)

Full plan/source/checkpoint/data hashes, trades, costs and predictions stay in the
artifact directories. This report and code/configs can be committed; data/weights
must not be pushed. Continued forward paper testing remains necessary even if
v15's continuous development screen passes.
