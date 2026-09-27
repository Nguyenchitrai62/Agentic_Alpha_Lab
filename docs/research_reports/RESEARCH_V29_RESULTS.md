# v29 residual GRU utility — completed 2026-09-06

## Decision

Reject v29 as a target candidate. The 33-model cloud export and complete local
replay audit passed, and the residual formulation improved action ranking over
several recent neural trials, but the portfolio still missed the 5% monthly /
20% DD requirement. The best normal-net row was mean-minus-std at 1x:
`+29.138%` with `26.255%` DD. Its 0.5x version reduced DD to `13.481%` but
returned only `+15.358%` over the full development interval (`+0.425%` monthly).
No live use or leverage increase follows.

## Scope and provenance

Private Kaggle kernel
[`nguynchtrai/btc-swing-v29-residual-gru-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v29-residual-gru-20260906)
completed once on 2x Tesla T4 with worker exit codes `[0, 0]` and 33/33
seed/fold models. The local GTX1650 replay audit passed all 12,228 fold
decisions; maximum error was `5.7220458984375e-06` with `rtol=atol=0.001`.

The continuous report covers 4,076 decisions from `2023-06-01` through
`2026-03-23` (`2.809092589` years), using one global policy and compounded
equity state. All dates are opened development, not an independent test;
signals use closed candles and fill from the next candle.

V29 fits a per-fold candidate prior from only matured 730-day training labels,
then trains the small causal GRU on context residuals and ranks prior-plus-
residual utility against WAIT. It uses fixed 16 epochs, three seeds, eleven
chronological folds and an 8-day label-end embargo. The candidate prior is
persisted in every checkpoint and checked during replay. No threshold, seed,
fold or portfolio branch was selected retrospectively.

Normal cost is 0.02% per fill with long funding 0.01% every eight hours and
zero short funding. Fee stress is 0.055% per fill. Execution stress adds 5 bps
entry/target penetration, 5 bps market-exit slippage and a 0.055% market-exit
fee. DD is close-sampled; the OHLC stress is not a queue or mark-price model.

## Continuous portfolio results

Capital starts at 100. Gross, fees and funding are percentage-point amounts on
the compounded ledger; DD is shown as a positive magnitude here.

| Branch / exposure | Scenario | Final equity | Gross | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 97.844 | 5.085 | 2.950 | 4.291 | -2.156% | 28.233% | 77 | -0.065% |
| mean / 1x | fee stress | 92.699 | 4.750 | 7.895 | 4.157 | -7.301% | 29.289% | 77 | -0.225% |
| mean / 1x | execution stress | 114.933 | 23.577 | 4.478 | 4.165 | +14.933% | 24.478% | 66 | +0.414% |
| mean / 0.5x | normal | 100.702 | 4.426 | 1.519 | 2.205 | +0.702% | 15.034% | 77 | +0.021% |
| mean / 0.5x | fee stress | 98.021 | 4.314 | 4.123 | 2.170 | -1.979% | 15.657% | 77 | -0.059% |
| mean / 0.5x | execution stress | 108.980 | 13.246 | 2.218 | 2.048 | +8.980% | 12.836% | 66 | +0.255% |
| mean-minus-std / 1x | normal | 129.138 | 37.243 | 3.327 | 4.777 | +29.138% | 26.255% | 82 | +0.761% |
| mean-minus-std / 1x | fee stress | 121.938 | 35.428 | 8.883 | 4.606 | +21.938% | 27.804% | 82 | +0.590% |
| mean-minus-std / 1x | execution stress | 115.859 | 25.051 | 4.943 | 4.249 | +15.859% | 27.312% | 78 | +0.438% |
| mean-minus-std / 0.5x | normal | 115.358 | 19.371 | 1.661 | 2.351 | +15.358% | 13.481% | 82 | +0.425% |
| mean-minus-std / 0.5x | fee stress | 112.094 | 18.906 | 4.503 | 2.310 | +12.094% | 14.389% | 82 | +0.339% |
| mean-minus-std / 0.5x | execution stress | 109.047 | 13.764 | 2.537 | 2.180 | +9.047% | 14.430% | 78 | +0.257% |

No row reaches 5% monthly geometric net in all three scenarios while staying
within 20% DD. The 1x branch with the highest net exceeds the DD limit; the
drawdown-safe 0.5x branches remain far below the monthly target.

## Forecast diagnosis

The ensemble mean has unconditional net MSE `9.89436` versus the causal
past-candidate constant `8.36532`, fill Brier `0.197188` versus `0.195558`,
bias `-0.11508%`, and within-decision action-rank correlation `0.073874` versus
the constant control's `0.001348`. Thus the residual GRU carries some ordering
signal, but its scores remain badly overconfident: the fixed 0.3–1.0% bucket
predicts about `0.6036%` while realizing only `0.0286%`, and the >2% bucket
predicts `2.9277%` while realizing `-0.0584%`.

## v30 follow-up pointer

Because the ranking signal survived while absolute scores were miscalibrated,
v30 applied a pre-registered causal isotonic probe to v29. It improved the
development result substantially, but isotonic-4 at 1x still had 20.086% normal
DD and 20.473% fee-stress DD, with only 2.405% and 2.268% monthly returns. The
complete table is in `RESEARCH_V30_RESULTS.md`; no mapping was promoted.

## Reproduction identity

- Plan: `configs/swing_v29_residual_gru.json`
- Cloud export: `artifacts/kaggle/v29_download/tcn-training`
- Local audit: `artifacts/research/v29_local_audit/audit.json`
- Continuous report: `artifacts/research/v29_local_portfolio/continuous/summary.json`
- Diagnostics: `artifacts/research/v29_value_diagnostics/summary.json`
- Kernel: `nguynchtrai/btc-swing-v29-residual-gru-20260906`
- Private dataset: `nguynchtrai/btc-swing-v29-residual-gru-20260906-data`
- Package archive SHA-256: `ae8012e4bbf5339395c2e3b1532080ba7f855ed8fefb03333c3e0c8a0dd7867c`
- Bootstrap SHA-256: `ae75cd31fdc81d01c4c27454b9af27b41fac85fe9c92c081af89b59cb7d772f3`
- Plan SHA-256: `158c785f6882c0a28769f86c5112446457248eb5b52e572ec722d507bcb14e9b`
- Cloud summary SHA-256: `31b0f10c661aa42b364561999fbf9f25001bb101d893cd6a18f183b9f1683a69`
- Audit SHA-256: `8a32411f9de8fce1e183174b694cf4cfe5862a5de6e5c745aa0cae2419a36b94`
- Continuous summary SHA-256: `4d81a045c361913f455723ff70a503c3129caa192f22ac73de1b02906b0a4f24`
- Diagnostics summary SHA-256: `770c7dab2d0741cbe9892bf678c988310f2ed6c3d1d148b1b65ff81b386eb8a1`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`

The cloud summary, replay audit and continuous report retain
`independent_test: false` and `live_approved: false`. All weights,
predictions and reports remain ignored research artifacts.
