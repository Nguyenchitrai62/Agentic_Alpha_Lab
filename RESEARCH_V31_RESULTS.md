# v31 short-window residual GRU — completed 2026-09-06

## Decision

Reject v31 as a target candidate. The private 33-model export, complete local
replay audit and continuous portfolio replay all passed their integrity checks,
but fitting the residual GRU on only the latest 60 days did not solve the
action-ranking problem. The safest fixed branch, mean-minus-std at 0.5x,
returned `+14.244%` normal net with `15.044%` drawdown, but only `0.396%`
monthly geometric net. Its fee-stress and execution-stress monthly returns
were `0.337%` and `0.472%`. No target, deployment or leverage approval follows.

## Scope and provenance

Private Kaggle kernel
[`nguynchtrai/btc-swing-v31-short-residual-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v31-short-residual-20260906)
completed once on 2x Tesla T4 with worker exit codes `[0, 0]` and 33/33
seed/fold models. The local GTX1650 replay audit passed all 33 model forecasts;
the maximum replay error was `1.0728836059570312e-06`.

The continuous report covers 4,076 decisions from `2023-06-01` through
`2026-03-23` (`2.809092589` years), with one global policy and compounded
equity state. All dates are opened development, not an independent test;
signals use closed candles and a signal at candle `t` can fill only from the
next candle onward.

V31 keeps the v29 residual-GRU architecture, loss, candidate grid, thresholds,
three-seed ensemble, 11 chronological folds and 8-day label-end embargo, but
fits each fold on the latest fixed 60 days of matured labels. The minimum was
registered as 160 rows; each fold had 180 rows. There was no seed, fold,
threshold, branch or portfolio selection after seeing outcomes. The 60-day
window was chosen before training because a separate causal prior probe found
the strongest development-only prior edge there; that probe is not a promoted
result.

Normal cost is 0.02% per fill with long funding 0.01% every eight hours and
zero short funding. Fee stress is 0.055% per fill. Execution stress adds 5 bps
entry/target penetration, 5 bps market-exit slippage and a 0.055% market-exit
fee. DD is close-sampled; the OHLC stress is not a queue-position or mark-price
model.

## Continuous portfolio results

Capital starts at 100. Gross, fees and funding are percentage-point amounts on
the compounded ledger; DD is shown as a positive magnitude here.

| Branch / exposure | Scenario | Final equity | Gross | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 110.847 | 18.620 | 2.653 | 5.120 | +10.847% | 28.121% | 61 | +0.306% |
| mean / 1x | fee stress | 106.189 | 18.333 | 7.138 | 5.006 | +6.189% | 28.434% | 61 | +0.178% |
| mean / 1x | execution stress | 115.532 | 24.307 | 3.906 | 4.869 | +15.532% | 28.086% | 55 | +0.429% |
| mean / 0.5x | normal | 107.337 | 11.067 | 1.284 | 2.445 | +7.337% | 15.044% | 61 | +0.210% |
| mean / 0.5x | fee stress | 105.059 | 10.971 | 3.494 | 2.418 | +5.059% | 15.224% | 61 | +0.147% |
| mean / 0.5x | execution stress | 109.419 | 13.623 | 1.883 | 2.320 | +9.419% | 15.031% | 55 | +0.267% |
| mean-minus-std / 1x | normal | 126.481 | 33.868 | 2.418 | 4.969 | +26.481% | 28.121% | 56 | +0.699% |
| mean-minus-std / 1x | fee stress | 121.617 | 33.005 | 6.518 | 4.870 | +21.617% | 28.434% | 56 | +0.582% |
| mean-minus-std / 1x | execution stress | 133.486 | 41.896 | 3.565 | 4.845 | +33.486% | 28.086% | 50 | +0.861% |
| mean-minus-std / 0.5x | normal | 114.244 | 17.799 | 1.173 | 2.382 | +14.244% | 15.044% | 56 | +0.396% |
| mean-minus-std / 0.5x | fee stress | 112.024 | 17.575 | 3.193 | 2.359 | +12.024% | 15.224% | 56 | +0.337% |
| mean-minus-std / 0.5x | execution stress | 117.198 | 21.185 | 1.698 | 2.289 | +17.198% | 15.031% | 50 | +0.472% |

The 1x rows exceed the 20% global drawdown limit. The drawdown-safe 0.5x
rows have positive net and at least 50 fills, but every monthly result is far
below the 5% requirement.

## Forecast diagnosis

The ensemble has unconditional net MSE `8.670506` versus the causal constant
control's `8.727075`, a small improvement. However, fill Brier is `0.222819`
versus `0.196453`, bias is `-0.131424%`, and within-decision candidate-rank
correlation is `-0.024082` versus `-0.023130` for the constant control. The
fixed score buckets also show sign/order failure: predicted `-0.5–0%` averaged
`-0.2314%` while realizing `+0.0291%`, and predicted `0.3–1%` averaged
`+0.5552%` while realizing `-0.1071%`. The short window improved fit error
without improving the ranking needed by the fixed policy.

## Next experiment boundary

V32 must test a materially different action-selection representation, not a
repeat of residual-GRU, another 60-day window, or another post-hoc calibration
map. The next registration should use a causal cross-sectional action-ranking
objective or an explicitly regime-conditioned candidate policy, with its
selection rule fixed before inspecting portfolio outcomes. All v31 artifacts
remain immutable development evidence.

## Reproduction identity

- Plan: `configs/swing_v31_short_window_residual_gru.json`
- Cloud export: `artifacts/kaggle/v31_download/tcn-training`
- Local audit: `artifacts/research/v31_local_audit/audit.json`
- Continuous report: `artifacts/research/v31_local_portfolio/continuous/summary.json`
- Diagnostics: `artifacts/research/v31_value_diagnostics/summary.json`
- Kernel: `nguynchtrai/btc-swing-v31-short-residual-20260906`
- Private dataset: `nguynchtrai/btc-swing-v31-short-residual-20260906-data`
- Package archive SHA-256: `61736966aab3b48b03760fe68c82b348aa2a082abc388a1c4661a394d48d9aab`
- Bootstrap SHA-256: `ae75cd31fdc81d01c4c27454b9af27b41fac85fe9c92c081af89b59cb7d772f3`
- Plan SHA-256: `98e856c0e421fe2efa330ef300077ae4bde16b80104b6b6719a0a3ca12e43ae3`
- Cloud summary SHA-256: `d7106afcb434db7d06cc3b6cf38a6c783ad66153f1ca86b8eae1ee7cd98fb250`
- Audit SHA-256: `d9a2e5c56477b41ada57894961b10c70c103adaac9d19a5dd039f7f347c7b66d`
- Continuous summary SHA-256: `6eaebed20a9e8ce602ee3d28b62869b8065ffc8b7ab54ab7cd11e3b77c61e267`
- Diagnostics summary SHA-256: `961d32a88100788b3963f3523d4e61b78ae24e71be7fde9d7255ac69244caac7`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`

The cloud summary, replay audit and continuous report retain
`independent_test: false` and `live_approved: false`. All weights,
predictions and reports remain ignored research artifacts.
