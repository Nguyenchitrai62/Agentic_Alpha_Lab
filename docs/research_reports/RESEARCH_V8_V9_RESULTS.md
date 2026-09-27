# BTC model-agnostic research — 2026-09-05

User now explicitly permits any learned architecture/pipeline; Kronos is optional.
All results below are historical development, NOT new independent tests. No live
orders or leverage escalation. Data and detailed reports remain ignored by Git.

## v8: shared action-value regression

Two histogram-gradient-boosted regressors learn unconditional net payoff and fill
from40 closed-candle, five-frame features plus6 candidate descriptors. Unlike
Kronos, these models have no pretrained transformer/tokenizer dependency. They
learn how market context affects16 possible LONG/SHORT entry/SL/TP1/TP2 brackets;
the bracket menu, sizing and frequency constraints remain execution logic.

Initial static fit: trailing730 days, fully matured labels plus8-day embargo.
Validation2025-06-09 to09-01: **+1.1815%, DD5.0065%,6 fills**.
Policy2025-09-09 to2026-03-23: **+3.7949%, DD11.7180%,19 fills**.
Both normal and fee/execution stresses positive; provisional development screen
passed, but these periods were already studied. No checkpoint deployed.

Monthly retraining is NOT automatically an improvement: validation+6.9744%,
DD3.5561%,8 fills; policy-3.1555%, DD20.9860%,21 fills. Rejected.
Artifacts: `artifacts/research/swing_v8_adaptive_20260905`.

## Wider frozen-specification audit and v9

Eight purged walk-forward folds, fitting only past labels each time, same730-day
window and8-day embargo. No threshold/size/direction optimization on these folds.
Every fold starts equity100 and compounds internally; the means below are **not**
one continuous portfolio return. Gaps between folds are not invested/simulated.

v9 replaces the two models with four learned heads: fill probability,
conditional win probability, mean gain when winning, mean loss when losing.
Expected net = fill × [win × gain − (1−win) × loss]. Classification log loss and
conditional squared-error amount losses, otherwise unchanged boosting settings.
These probabilities are not separately calibrated or certified confidence scores.

| Evaluation interval | v8 net | v9 net |
|---|---:|---:|
| Jun–Aug2023 | −10.2780% | −2.5616% |
| Sep–Nov2023 | −2.8834% | +8.8646% |
| Jan–Mar2024 | −8.5720% | +11.4680% |
| Jul–Sep2024 | −17.0520% | +12.9165% |
| Oct–Dec2024 | +5.8633% | +0.5360% |
| Jun–Aug2025 | +1.1815% | −3.6017% |
| Sep–Nov2025 | +7.7753% | −17.5153% |
| Dec2025–Mar2026 | +4.5305% | −15.6778% |

Exact dates, label cutoffs, predictions and trades are saved with each fold.

- v8:73 fills,4/8 folds positive in normal AND both stress scenarios; mean fold
  net−2.4293%, worst scenario foldDD22.0652%. **Rejected.**
- v9:64 fills,3/8 jointly positive; mean fold net−0.6964%, worst scenario foldDD
  24.5948%. **Rejected.** October2024's small v9 gain becomes negative with fee stress.
- Train-only candidate-mean control:25 fills, mean fold+2.7328%, but worstDD
  23.9489% and positive only2 folds. This is not a recommended alternative either.
- Direct v8 payoff MSE beats the constant control on only3/8 folds; feature/model
  predictive quality remains weak. One profitable recent slice was misleading.

Artifact roots:
`artifacts/research/swing_v8_walkforward_20260905`,
`artifacts/research/swing_v9_hurdle_20260905`.
v8 source snapshots saved before generalizing runner; v9 saves runner/model source.
Configs `swing_v8_walkforward.json` and `swing_v9_hurdle_walkforward.json` fix the
eight folds and research advancement gate. This is disclosed repeated research,
not independent evidence and not proof a strategy can never work.

## Execution assumptions

Fee0.02% each entry/exit fill; long funding0.01% everyUTC8h, shortfunding0. Capital100
compounded,1x baseline. Separate uniform0.055% fee scenario, and5bps penetration
for limit entry/targets plus5bps market-exit slippage/0.055% exit fee. Stop/timeout
are market-like, not guaranteed maker. Penetration is not order queue simulation.
Stress can improve net by skipping a loser; that does not prove a better model.
Drawdown is candle-close sampled, not mark-price or a guaranteed20% live loss cap.

## Next hypothesis and active work

Do not scale up or deploy either failed model. Complete the existing frozen-Kronos
representation probe as a comparator. In parallel, audit publicly archived BTC
open interest/positioning data2022-01-01 through2026-03-22 to investigate whether
missing derivatives context matters more than another blind architecture change.

`configs/btc_derivatives_data_plan.json` and `scripts/download_derivatives_metrics.py`
preserve each ZIP and verify source SHA256; report missing days/fields. A verified
2022-01-01 sample has OI fields but missing positioning ratios. Missing values must
not be silently turned into future/backfilled information.

The archive timestamp is NOT verified live publication time. Binance documents
daily archives as becoming available the following day, and historical downloads
do not establish what a live client knew at each timestamp. Feature construction
requires a separately declared lag/staleness policy and sensitivity tests first.
Source: [Binance public-data documentation](https://github.com/binance/binance-public-data).

Local scheduled continuation prompt was updated using OpenAI Docs to reflect the
model-agnostic user request; existing hourly task preserved, no duplicate created.
At this point90 unit tests pass. This verifies code behavior, not trading profit.
