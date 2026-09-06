# v26 small GRU with pairwise utility ranking — completed 2026-09-06

## Decision

Keep v26 as a development comparator, not a target candidate. The cloud export
and full local replay audit passed. The mean/0.5x branch is positive in all
three execution scenarios with DD below 20%, but its calendar-geometric net is
only 0.20–0.27% per month, far below the required 5%. The 1x branch has higher
net return but exceeds the DD cap. No live use or leverage increase follows.

## Scope and provenance

Private Kaggle kernel
[`nguynchtrai/btc-swing-v26-ranked-gru-20260906`](https://www.kaggle.com/code/nguynchtrai/btc-swing-v26-ranked-gru-20260906)
version 1 completed on 2×Tesla T4 with worker exit codes `[0, 0]` and 33/33
seed/fold models. The local GTX1650 temporal replay/policy audit passed every
forecast; maximum replay error was `6.67572021484375e-06` under `rtol=atol=0.001`.

The continuous report covers 4,076 decisions from `2023-06-01` through the
`2026-03-23` mature-label cutoff (`2.809092589` years), with one global
cooldown, monthly cap, position and compounded-equity state. The mean branch
and mean-minus-standard-deviation branch each produced 135 signals; coverage
was 3.31% of decisions. All dates are opened development, not an independent
test; signals use closed candles and fill from the next candle.

V26 uses the causal 48-wide shared GRU over the same five 128-candle frames as
the earlier v13/v17 temporal model. Training is 16 epochs, three seeds and
eleven chronological folds, with 730-day past-only fitting and an 8-day
label-end embargo. The fixed objective is v22's Huber payoff, pairwise utility
ranking against WAIT, fill loss and macro auxiliary loss. No threshold, seed or
fold was selected during training.

Normal cost is 0.02% per fill with long funding 0.01% every eight hours and
short funding zero. Fee stress uses 0.055% per fill. Execution stress adds 5
bps entry/target penetration, 5 bps market-exit slippage and a 0.055%
market-exit fee. DD is close-sampled; stress is not a queue, mark-price or
liquidation model.

## Continuous portfolio results

Values start from equity 100. Gross PnL, fees and funding are percentage-point
amounts on the compounded account ledger; net return is final equity minus 100.

| Branch / exposure | Scenario | Final equity | Gross PnL | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mean / 1x | normal | 116.366 | 23.312 | 2.730 | 4.215 | +16.366% | 23.34% | 68 | +0.451% |
| mean / 1x | fee stress | 110.950 | 22.368 | 7.326 | 4.092 | +10.950% | 24.11% | 68 | +0.309% |
| mean / 1x | execution stress | 116.811 | 24.091 | 3.675 | 3.605 | +16.811% | 28.53% | 57 | +0.462% |
| mean / 0.5x | normal | 109.539 | 13.006 | 1.372 | 2.095 | +9.539% | 12.30% | 68 | +0.271% |
| mean / 0.5x | fee stress | 106.959 | 12.752 | 3.728 | 2.064 | +6.959% | 12.74% | 68 | +0.200% |
| mean / 0.5x | execution stress | 109.563 | 13.259 | 1.872 | 1.824 | +9.563% | 14.91% | 57 | +0.271% |
| mean−std / 1x | normal | 89.720 | -3.923 | 2.723 | 3.633 | -10.280% | 33.64% | 79 | -0.321% |
| mean−std / 1x | fee stress | 84.868 | -4.327 | 7.290 | 3.515 | -15.132% | 35.22% | 79 | -0.486% |
| mean−std / 1x | execution stress | 79.389 | -14.012 | 3.830 | 2.768 | -20.611% | 32.32% | 67 | -0.682% |
| mean−std / 0.5x | normal | 95.960 | -0.587 | 1.476 | 1.977 | -4.040% | 17.96% | 79 | -0.122% |
| mean−std / 0.5x | fee stress | 93.333 | -0.719 | 4.003 | 1.944 | -6.667% | 18.93% | 79 | -0.204% |
| mean−std / 0.5x | execution stress | 89.974 | -6.362 | 2.113 | 1.551 | -10.026% | 17.01% | 67 | -0.313% |

The mean/0.5x row passes only the provisional positive-net/DD/fill screen. It
does not pass the user's geometric monthly target, and v26 mean/1x does not
pass the 20% DD requirement.

## Forecast diagnosis

The ensemble mean has unconditional payoff MSE `10.0505` versus the
past-mature candidate-constant control `8.3653`, fill Brier `0.19757` versus
`0.19556`, bias `-0.1159%`, and within-decision action-rank correlation
`0.0792`. The rank signal is the strongest among the recent TCN/GRU trials, but
the absolute scores are overconfident: the fixed `0.3–1.0%` bucket predicted
`0.6235%` and realized `0.1430%`; the `>2%` bucket predicted `2.8725%` and
realized `-0.0407%` across 4,085 candidate observations.

## v27 causal calibration probe

Because v26 scores were overconfident, a read-only probe fit monotone maps only
from earlier mature-label fold histories, with the same 8-day embargo. Identity
and fixed previous-quarter windows `[1, 2, 4, all]` were retained; no favorable
window was promoted. The most useful diagnostic was isotonic-4 at 0.5x:
normal net `+27.55%` / DD `10.85%`, fee net `+25.07%` / DD `11.13%`, and
execution net `+20.40%` / DD `10.84%` over the same 2.809-year development
period. Its monthly geometric returns were only `+0.724%`, `+0.666%` and
`+0.552%`. At 1x, the same window was `+59.65%` normal net but DD `20.73%`
and execution net `+42.64%` with DD `20.72%`; it therefore misses the DD cap.
Every v27 branch still fails the 5% monthly target. These are development
diagnostics, not an independent confirmation or a license to tune a threshold.

## Reproduction identity

- V26 plan: `configs/swing_v26_ranked_gru.json`
- V26 cloud export: `artifacts/kaggle/v26_download/tcn-training`
- V26 audit: `artifacts/research/v26_local_audit/audit.json`
- V26 continuous report: `artifacts/research/v26_local_portfolio/continuous/summary.json`
- V26 diagnostics: `artifacts/research/v26_value_diagnostics/summary.json`
- V27 plan: `configs/swing_v27_v26_calibration.json`
- V27 report: `artifacts/research/v27_v26_calibration/summary.json`
- V26 package archive SHA-256: `a516e64b0c617c9cf57eb8bb80c04633e52b20a1381c9f2b73b681da0afc5444`
- V26 bootstrap SHA-256: `0f758f55f4fe38022fe04344d8d94e5c17d9897221957d27e841c86d20f2973d`
- V26 plan SHA-256: `09f3b2c07880fc637332c6a6fbadfe75abf3fd79b5ac7382663b96a87908f4b1`
- V26 audit SHA-256: `fd05555c4478b8674935490407f2415495d2278501eb6ef04a4fba088227188d`
- V27 plan SHA-256: `95d2e1d80416e3470018d9cc67b0d05c6f306160d61a6e0cde00652be504dfe0`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`
- Sequence-cache manifest SHA-256: `e3c08b4875d8848a6bd1681f1d1d9679a6d9d4d1f05d347eaa2492046a1fadba`

The v26 audit, continuous report and v27 report record
`independent_test: false` and `live_approved: false`. The package, weights,
predictions and reports remain ignored research artifacts.
