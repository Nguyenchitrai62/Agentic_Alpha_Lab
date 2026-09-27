# v25 ranked-gate TCN utility — completed 2026-09-06

## Decision

Reject v25. The private training export, all-model replay audit and policy
parity checks passed, but every registered continuous branch failed the user's
calendar-geometric net target and drawdown gate. No live use, leverage increase
or deployment approval follows from this run.

## Scope and provenance

The private Kaggle kernel
[`nguynchtrai/btc-swing-v25-ranked-gate-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v25-ranked-gate-20260906)
version 1 completed on 2×Tesla T4 with worker exit codes `[0, 0]`. The export
contains 33/33 seed/fold models and reports `state: complete`. Local CUDA
replay on the GTX1650 passed all 33 forecasts and exact ordered policy checks;
the largest replay error was `2.1457672119140625e-06` under the registered
`rtol=atol=0.001` gate.

This is opened development history, not an independent test. The one-state
continuous evaluator used 4,076 decisions from `2023-06-01` through the
`2026-03-23` mature-label cutoff (`2.809092589` years). Signals are made only
after a closed candle and begin filling on the next candle. The mean branch
generated 135 signals; mean-minus-one-standard-deviation generated 131. Signal
coverage was therefore 3.31% and 3.21% of decisions respectively. The final
immature label tail was excluded once, globally.

## Registered model and costs

The model kept the causal five-frame TCN plus cross-frame attention used in
v22, with width 256, TCN width 64, four attention layers, four heads and
dilations `[1, 2, 4, 8, 16]`. It trained all three seeds across eleven
chronological folds for eight epochs, using 730 days of past data and an
eight-day label-end embargo. The fixed objective was Huber payoff regression,
pairwise utility ranking against WAIT, a positive-net gate margin at 0.3%,
fill loss and the macro auxiliary loss. No evaluation threshold or seed was
tuned.

Normal cost is 0.02% per fill with long funding 0.01% every eight hours and
short funding zero. Fee stress changes the fee to 0.055% per fill. Execution
stress adds 5 bps entry/target penetration, 5 bps market-exit slippage and a
0.055% market-exit fee. Drawdown is close-sampled; the execution scenario is
not a queue, mark-price or liquidation model.

## Continuous portfolio results

Values start from equity 100. Gross PnL, fees and funding are percentage-point
amounts on the compounded account ledger; net return is final equity minus 100.

| Branch / exposure | Scenario | Final equity | Gross PnL | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 56.386 | -37.782 | 2.962 | 2.869 | -43.614% | 62.77% | 110 | -1.685% |
| mean / 1x | fee stress | 52.172 | -37.180 | 7.884 | 2.763 | -47.828% | 64.18% | 110 | -1.912% |
| mean / 1x | execution stress | 55.506 | -38.234 | 4.070 | 2.190 | -44.494% | 66.67% | 91 | -1.731% |
| mean / 0.5x | normal | 76.806 | -19.569 | 1.806 | 1.819 | -23.194% | 38.19% | 110 | -0.780% |
| mean / 0.5x | fee stress | 73.890 | -19.448 | 4.879 | 1.783 | -26.110% | 39.35% | 110 | -0.894% |
| mean / 0.5x | execution stress | 76.049 | -20.019 | 2.494 | 1.438 | -23.951% | 41.59% | 91 | -0.809% |
| mean−std / 1x | normal | 70.702 | -22.376 | 3.298 | 3.625 | -29.298% | 54.63% | 107 | -1.023% |
| mean−std / 1x | fee stress | 65.576 | -22.166 | 8.777 | 3.481 | -34.424% | 55.91% | 107 | -1.244% |
| mean−std / 1x | execution stress | 73.179 | -18.125 | 5.247 | 3.449 | -26.821% | 52.06% | 96 | -0.922% |
| mean−std / 0.5x | normal | 85.793 | -10.157 | 1.882 | 2.168 | -14.207% | 31.94% | 107 | -0.454% |
| mean−std / 0.5x | fee stress | 82.632 | -10.159 | 5.087 | 2.122 | -17.368% | 32.89% | 107 | -0.564% |
| mean−std / 0.5x | execution stress | 87.188 | -7.890 | 2.925 | 1.997 | -12.812% | 30.06% | 96 | -0.406% |

The best registered branch is still negative and above the 20% drawdown cap.
The 1x baseline has 110/107 fills in the normal scenario, but trade count does
not rescue the negative edge. All rows fail the target; the evaluator records
`passes_provisional_continuous_screen: false` and
`meets_user_5pct_monthly_target: false`.

## Forecast diagnosis

The v25 ensemble mean has unconditional payoff MSE `9.1237` versus the
past-mature candidate-constant control `8.3653`, fill Brier `0.19558` versus
`0.19556`, net bias `-0.2424%`, and within-decision action-rank correlation
`0.0258`. The rank correlation is below v22's `0.0389`; the gate did not
improve selection. In the fixed `0.3–1.0%` score bucket, 15,706 candidate
observations predicted `0.6127%` but realized `-0.1156%`. The fixed `1–2%`
bucket predicted `1.2026%` and realized only `0.0241%`. These are diagnostics,
not tuned filters or independent observations.

For context, v22's better normal mean/1x result was `+17.690%` net with
`35.02%` drawdown, still a failure of the risk target. v23 listwise TCN ended
at `-13.526%` net with `49.51%` drawdown. The v25 gate therefore gets no
promotion over the earlier ranked objective.

## Reproduction identity

- Plan: `configs/swing_v25_ranked_gate_tcn.json`
- Cloud export: `artifacts/kaggle/v25_download/tcn-training`
- Replay audit: `artifacts/research/v25_local_audit/audit.json`
- Continuous report: `artifacts/research/v25_local_portfolio/continuous/summary.json`
- Diagnostics: `artifacts/research/v25_value_diagnostics/summary.json`
- Package manifest: `artifacts/kaggle/btc_swing_v25_ranked_gate_20260906/package-manifest.json`
- Package archive SHA-256: `23079b22fecc272681f019a5b1cb1644f046bd8c7fca2b0b6601dbb202bc9366`
- Bootstrap SHA-256: `5d56c314d2cdc2a47926bae59abbdd8af34a51d26ca7a9f7a0481bbb76ed0674`
- Plan SHA-256: `76ff7dfd6d657f34a7c8f38d85b8cc8dca0ae89797fa0ac84410a6d4ed62a887`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`
- Training summary SHA-256: `8b73c8256a96b79de476e935c862eac47d224707167b5c42d3986e95932d4258`
- Audit SHA-256: `cd69a703f68b0372cc312a983b72e5828262d793c6ebcaa0c5940d238dc0a011`

Both the audit and continuous report explicitly record
`independent_test: false` and `live_approved: false`. The dataset, checkpoints,
predictions and reports remain ignored research artifacts and are not added to
Git.
