# v32 top-action/WAIT GRU — completed 2026-09-06

## Decision

Reject v32 as a target candidate. The private 33-model export, full local
replay audit and continuous portfolio replay all passed their integrity gates,
but the top-action/WAIT loss did not produce useful out-of-sample candidate
ranking. No registered branch reached the required calendar-geometric
`>=5%` monthly net in all three scenarios while keeping global drawdown
`<=20%` and at least 30 fills. No deployment, leverage or live approval
follows.

## Scope and provenance

Private Kaggle kernel
[`nguynchtrai/btc-swing-v32-top-action-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v32-top-action-20260906)
completed exactly once on two Tesla T4 workers with exit codes `[0, 0]` and
33/33 seed/fold models. Runtime was Torch `2.10.0+cu128`. The local GTX1650
replay audit passed every forecast; the maximum numerical replay error was
`2.384185791015625e-06`.

The continuous report covers 4,076 decisions from `2023-06-01` through
`2026-03-23` (`2.809092589` years), with one global policy and compounded
equity state. All dates are opened development, not an independent test;
signals use closed candles and a signal at candle `t` can fill only from the
next candle onward.

V32 kept the causal 48-wide GRU, closed-candle sequence, train-only
normalization, 730-day matured-label window, 11 chronological folds, three
seeds and 8-day label-end embargo. Its registered change was a top-action versus
explicit WAIT classification objective with a Huber payoff, fill and direction
auxiliary terms; the class target was the best realized executable candidate
when it cleared the frozen `0.3%` boundary, otherwise WAIT. The implementation
tied the class logits to the candidate payoff score, so this result does not
establish that a separate action-logit head would work.

Normal cost is `0.02%` per fill with long funding `0.01%` every eight hours and
zero short funding. Fee stress is `0.055%` per fill. Execution stress adds
5 bps entry/target penetration, 5 bps market-exit slippage and a `0.055%`
market-exit fee. DD is close-sampled; OHLC stress is not a queue-position or
mark-price model.

## Continuous portfolio results

Capital starts at 100. Gross, fees and funding are percentage-point amounts on
the compounded ledger; DD is shown as a positive magnitude. Signals/coverage
is the number of policy signals divided by the 4,076 continuous decisions;
fills are listed as normal/fee-stress/execution-stress.

| Branch / exposure | Scenario | Final equity | Gross | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 92.817 | -0.743 | 2.982 | 3.458 | -7.183% | 35.193% | 73 | -0.221% |
| mean / 1x | fee stress | 88.187 | -0.457 | 8.000 | 3.356 | -11.813% | 36.907% | 73 | -0.372% |
| mean / 1x | execution stress | 95.234 | 2.050 | 4.030 | 2.786 | -4.766% | 29.613% | 63 | -0.145% |
| mean / 0.5x | normal | 98.033 | 1.271 | 1.484 | 1.753 | -1.967% | 18.807% | 73 | -0.059% |
| mean / 0.5x | fee stress | 95.562 | 1.319 | 4.031 | 1.727 | -4.438% | 19.881% | 73 | -0.135% |
| mean / 0.5x | execution stress | 99.260 | 2.727 | 2.041 | 1.426 | -0.740% | 15.440% | 63 | -0.022% |
| mean-minus-std / 1x | normal | 81.728 | -14.183 | 1.986 | 2.103 | -18.272% | 29.323% | 53 | -0.597% |
| mean-minus-std / 1x | fee stress | 78.731 | -13.848 | 5.367 | 2.054 | -21.269% | 31.073% | 53 | -0.707% |
| mean-minus-std / 1x | execution stress | 104.094 | 9.296 | 2.959 | 2.243 | +4.094% | 21.823% | 44 | +0.119% |
| mean-minus-std / 0.5x | normal | 91.463 | -6.386 | 1.032 | 1.119 | -8.537% | 15.513% | 53 | -0.264% |
| mean-minus-std / 0.5x | fee stress | 89.776 | -6.307 | 2.812 | 1.106 | -10.224% | 16.350% | 53 | -0.319% |
| mean-minus-std / 0.5x | execution stress | 103.025 | 5.552 | 1.435 | 1.092 | +3.025% | 11.196% | 44 | +0.088% |

The safest rows by drawdown are below 20%, but they lose money and have
monthly returns near zero. The only positive 1x execution rows fail normal and
fee stress and the drawdown gate. Signal coverage was 123/4,076 (`3.02%`) for
the mean branch and 87/4,076 (`2.13%`) for mean-minus-std.

## Forecast diagnosis

The ensemble's unconditional net MSE was `8.793882` versus the causal constant
control's `8.365318`; fill Brier was `0.209896` versus `0.195558`; bias was
`-0.531286%`; and within-decision candidate-rank correlation was `-0.001778`
versus `+0.001348` for the constant control. In the fixed score buckets, the
ensemble's `0.3–1.0%` predicted bucket averaged only `+0.242410%` observed net,
and the `0.0–0.3%` bucket averaged `+0.029064%`, confirming that the learned
score did not order the candidates well enough for the unchanged policy.

The result is a failed ranking hypothesis, not evidence that the fixed action
grid has no headroom: the earlier leakage-marked oracle bound still showed
positive capacity. The next experiment must separate action selection from
payoff-score regression and use a registered inference adapter, rather than
repeating this tied-logit objective, residual-GRU window, or post-hoc map.

## Reproduction identity

- Plan: `configs/swing_v32_top_action_gru.json`
- Cloud export: `artifacts/kaggle/v32_download/tcn-training`
- Local audit: `artifacts/research/v32_local_audit/audit.json`
- Continuous report: `artifacts/research/v32_local_portfolio/continuous/summary.json`
- Diagnostics: `artifacts/research/v32_value_diagnostics/summary.json`
- Kernel: `nguynchtrai/btc-swing-v32-top-action-20260906`
- Private dataset: `nguynchtrai/btc-swing-v32-top-action-20260906-data`
- Package archive SHA-256: `ed68a90b153fe8caea81148501096330323d40ad81a5aeb97eeb3bb4425e0cb7`
- Bootstrap SHA-256: `410cb05dc61ff09c71bcd32842d575d6bd1c9adfa6bbfda03a0673454458379c`
- Plan SHA-256: `7d73748c9ccde2d115bd1964b5f13de8423a71d3ae948eb9fd21636bdfe2932b`
- Cloud summary SHA-256: `f60626fe7e5ff7bd0d4f2919c7a4b4effddbab11d2fb7e940aea158efa383002`
- Audit SHA-256: `0659cff25e6fe13282a398141dd6c1abd20c237eeb2cb68ef838fb081eea0e11`
- Continuous summary SHA-256: `db88e5037f491191646635282c1a31680e700aac706e8f8eeb3534b2a77b2759`
- Diagnostics summary SHA-256: `d10c0ddeef8ae442c0b069d8451d123dd5d95ed8b2ca0bf88ee72860b0c3b4a1`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`

The cloud summary, replay audit and continuous report retain
`independent_test: false` and `live_approved: false`. All weights, predictions
and reports remain ignored research artifacts.
