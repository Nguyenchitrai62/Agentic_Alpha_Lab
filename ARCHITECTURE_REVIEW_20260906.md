# Review of the supplied BTC multi-timeframe architecture

Source read in full: C:/Users/trait/Downloads/btc_multi_timeframe_ai_architecture.md.
Its recommendations are proposals for evaluation, not instructions to trade live.

## Current evidence and compute state

v18 local Transformer run STOPPED with exit1, session61208 finished. Eight folds
of seed1729 have full metadata/reports. Fold8 saved model.safetensors but failed
CPU/GPU replay assertion:1/768values outside rtol1e-3/atol1e-3, maximum absolute
difference0.00116229. No full33model summary or continuous v18 result exists.
Do not describe this as running, as an out-of-memory failure, or as finished
validation. Diagnose attention kernels/precision and compare actual signals before
changing tolerance. Preserve the partial weights and all prior artifacts.

v17 corrected calibration four-quarter1x is a useful DEVELOPMENT comparator:
100->177.3981 over2.80909years,66fills, normalDD18.8565%, monthly geometric1.71505%,
CAGR22.6373%; executionstress net57.3992%,DD19.4311%,monthly1.35477%. Observed normal
winrate62.1212%,stress60.3448%. This variant was observed among many experiments;
it is not independent validation and does not meet5%monthly or79.5856%yearly target.

User now prefers heavy training on Kaggle CLI/free GPUs, local inference/backtests.
CLI2.2.4 is installed. No new Kaggle job was submitted during this review. Existing
packager/bootstrap only supports old Kronos swing schemas, so it needs a new
versioned TCN/sequence bundle; the new model cannot simply use the old bundle.

## Assessment

TCN per timeframe -> temporal tokens -> cross-timeframe attention -> multi-task
heads is a credible next hypothesis. Causal dilated convolution can efficiently
encode local price/volume structure; attention can combine macro and micro context.
The original TCN paper supports benchmarking convolutional sequence models, but
does not establish BTC profitability or that GRU is categorically unsuitable:
https://arxiv.org/abs/1803.01271 . TFT itself combines recurrent processing with
attention and gating: https://arxiv.org/abs/1912.09363 .

The file's4layer,d_model256 Transformer is approximately3.15M block parameters
under the conventional4x feedforward expansion, excluding TCNs/embeddings/heads.
Thus it is not a recommendation to jump to1B. The total cannot be calculated
without TCN widths/depth/kernels.3.06M may underfit a suitable task, but present
evidence does not establish this: training loss falls while temporal performance
is unstable. Current5628decision windows heavily overlap3–7day labels; five
resolutions of the same path do not multiply independent market outcomes byfive.

## Changes needed for this user's trading horizon

1. Retain1d with4h macro context. The supplied1m/5m/15m/1h/4h layout omits1d and
   emphasizes intraday setups. Start5m/15m/1h/4h/1d; evaluate1m later for execution
   timing if historical data and fill simulation support it.
2. Preserve a sequence of tokens from each TCN. Reducing256candles to one embedding
   per frame before a Transformer discards temporal detail. Add timeframe and
   elapsed-time/age embeddings; patch index alone is not equal elapsed time across
   frames. Use adaptive macro/micro fusion or candidate cross-attention.
3. Predict several horizons (e.g.1/3/7days) and conditional trade outcomes. Keep
   fill/no-fill, time to entry, payoff quantiles, TP/SL first-hit probabilities and
   MFE/MAE heads as candidates. Weight/ablate tasks: more heads can conflict rather
   than improve signal. No particular head is proven useful yet.
4. MFE/MAE ratios alone do not specify whether SL happens before TP; estimate
   path/order under the chosen limit entry, expiry, TP1/TP2 and max holding. A
   stopped LONG is not automatically a profitable SHORT. An untouched barrier
   ending at timeout is not automatically NO TRADE. Label both directions using
   their own executions and account for the value of abstaining.
5. Calibrate probabilities/payoff with label_end<refit-8days. Use one global
   trading state. The file's probability0.68 and return0.004 are illustrations,
   not validated thresholds. Derivative inputs require historical availability
   timestamps, lag/missingness, and no future on-chain revisions.
6. Attention weights are not validated causal contributions of each timeframe.
   Show them as diagnostics, check feature/frame ablations for actual contribution.
7. A last-token predictor with all input candles closed may attend bidirectionally
   within its past window. A naive causal mask over concatenated different-frame
   tokens is not chronological causality; use true timestamp masks if predicting
   multiple historical positions or reconstructing held-out future targets.

## Recommended implementation sequence

Prefer deep learning as requested. Benchmark TCN-only and TCN+attention on identical
causal data/labels, then add payoff/risk heads. Consider20–50M as an INITIAL
capacity trial (engineering proposal, not an optimal size), with smaller comparator;
scale toward100M+ only if loss/generalization evidence and training data justify it.
For larger models, self-supervised pretraining on past-only OHLC/flow windows and
diverse liquid assets is a testable hypothesis, followed by BTC execution-aware
fine-tuning. Purge asset-aligned future dates too: cross-asset data can leak regimes.

Kaggle: private allowlisted bundle, hash manifest, verified GPU allocation. Split
independent fold/seed training across two GPUs first; each produces independently
replayable weights. Two GPUs do not automatically pool VRAM; multi-GPU replicas
alone will not solve a model exceeding one device's memory. Download artifacts
and use local inference/continuous backtest, matching the user's preference.
Official CLI reference: https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md .

Do not promise the target can be reached by adding parameters. Acceptance remains
geometric5%monthly after costs with globalDD<=20%, prospective evidence and no
post-hoc choice of a winning seed/market interval. Record every variant and failure.
