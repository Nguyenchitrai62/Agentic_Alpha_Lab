# v28 hurdle GRU utility — completed 2026-09-06

## Decision

Reject v28 as a target candidate. The full cloud export and all-33-model local
replay audit passed, but every registered portfolio branch missed the target.
The best drawdown-safe branch, mean-minus-std at 0.5x, lost 9.915% normal,
12.510% under fee stress and 6.501% under execution stress. Its DD stayed
below 20% only because the net return was negative. There is no deployment,
leverage increase or live approval.

## Scope and provenance

Private Kaggle kernel
[`nguynchtrai/btc-swing-v28-hurdle-gru-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v28-hurdle-gru-20260906)
completed on 2x Tesla T4 with 33/33 seed/fold models and worker exit codes
`[0, 0]`. The retry full replay audit passed every forecast on the local
GTX1650: 12,228 fold-decision replays, maximum error
`7.15255737304688e-06`, with `rtol=atol=0.001`.

The continuous result covers 4,076 decisions from `2023-06-01` through the
`2026-03-23` mature-label cutoff, one global monthly/cooldown/position state,
and 2.809092589 years of compounded equity. All dates are opened development,
not an independent test. Signals use closed candles and fill from the next
candle.

V28 decomposed utility into causal fill, win, positive-payoff and
negative-payoff heads, while retaining the fixed small-GRU and pairwise WAIT
ranking structure. It used 16 fixed epochs, three seeds, eleven chronological
folds, a 730-day past-only window and an 8-day label-end embargo. No seed,
fold, threshold or portfolio branch was selected retrospectively.

Costs are 0.02% per entry/exit fill, long funding 0.01% every eight hours and
zero short funding. Fee stress is 0.055% per fill. Execution stress adds 5 bps
entry/target penetration, 5 bps market-exit slippage and a 0.055% market-exit
fee. DD is close-sampled; OHLC stress is not a queue or mark-price model.

## Continuous portfolio results

Capital starts at 100. Gross, fees and funding are percentage-point amounts on
the compounded ledger; DD is shown as a positive magnitude here.

| Branch / exposure | Scenario | Final equity | Gross | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 78.997 | -13.322 | 2.867 | 4.814 | -21.003% | 44.084% | 84 | -0.697% |
| mean / 1x | fee stress | 74.453 | -13.204 | 7.670 | 4.672 | -25.547% | 44.949% | 84 | -0.871% |
| mean / 1x | execution stress | 91.779 | -0.094 | 4.091 | 4.036 | -8.221% | 43.683% | 72 | -0.254% |
| mean / 0.5x | normal | 91.146 | -4.624 | 1.570 | 2.660 | -8.854% | 24.625% | 84 | -0.275% |
| mean / 0.5x | fee stress | 88.493 | -4.631 | 4.257 | 2.619 | -11.507% | 25.202% | 84 | -0.362% |
| mean / 0.5x | execution stress | 98.050 | 2.444 | 2.200 | 2.194 | -1.950% | 24.329% | 72 | -0.058% |
| mean-minus-std / 1x | normal | 77.745 | -14.710 | 2.728 | 4.817 | -22.255% | 35.091% | 83 | -0.744% |
| mean-minus-std / 1x | fee stress | 73.320 | -14.721 | 7.292 | 4.666 | -26.680% | 37.554% | 83 | -0.916% |
| mean-minus-std / 1x | execution stress | 84.226 | -7.182 | 4.088 | 4.503 | -15.774% | 32.077% | 71 | -0.508% |
| mean-minus-std / 0.5x | normal | 90.085 | -5.684 | 1.524 | 2.707 | -9.915% | 18.849% | 83 | -0.309% |
| mean-minus-std / 0.5x | fee stress | 87.490 | -5.715 | 4.131 | 2.664 | -12.510% | 19.537% | 83 | -0.396% |
| mean-minus-std / 0.5x | execution stress | 93.499 | -1.822 | 2.221 | 2.457 | -6.501% | 17.098% | 71 | -0.199% |

The user gate requires at least 5% monthly geometric net and DD no greater
than 20% in all three scenarios. No row passes it.

## Forecast diagnosis

The ensemble mean had unconditional net MSE `9.4058` versus the causal
past-candidate constant `8.3653`, fill Brier `0.20288` versus `0.19556`, bias
`-0.0992%`, and within-decision action-rank correlation `0.04087`. The hurdle
decomposition did not improve either calibration or ranking enough to justify
another identical run.

## Reproduction identity

- Plan: `configs/swing_v28_hurdle_gru.json`
- Cloud export: `artifacts/kaggle/v28_download/tcn-training`
- Local audit: `artifacts/research/v28_local_audit_retry/audit.json`
- Continuous report: `artifacts/research/v28_local_portfolio/continuous/summary.json`
- Diagnostics: `artifacts/research/v28_value_diagnostics/summary.json`
- Kernel: `nguynchtrai/btc-swing-v28-hurdle-gru-20260906`
- Private dataset: `nguynchtrai/btc-swing-v28-hurdle-gru-20260906-data`
- Clean package archive SHA-256: `0dfd391ffbb01d2ac78cac6a92975e3a26a99639ac802beb08ede5e4ae942715`
- Bootstrap SHA-256: `b90548b23b91271a501f852bd22e11118bad18c7e7bbe6e963f7bb328f64397d`
- Plan SHA-256: `1dd931104d59007d1d00db406357c60e8868cb2c22f1c95a554f7655f2d0fb01`
- Audit SHA-256: `819779cd0dc44a44e73bad0cd8c6d2a9e2b13a34d5d337d5af29fd9dc184baf9`
- Continuous summary SHA-256: `5783af220fc55fccac6a351e4992d645687d51b7329afbfebd259c0cafafd937`
- Diagnostics summary SHA-256: `67ec13d2d8324bf61a4f12bb25090c6ac1da51b9575555b2345cb4e43d187bee`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`

The continuous report, audit and cloud summary all retain
`independent_test: false` and `live_approved: false`.
