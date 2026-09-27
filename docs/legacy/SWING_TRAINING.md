# Kronos-base swing trading — v2

Read `AGENTS.md` first. User scope: research/paper only, 1–4 useful alerts/month,
reversal or pullback-entry opportunities, holding several days to one week.
Profit after costs and drawdown matter more than candle direction accuracy.
User subsequently raised maximum acceptable drawdown to20%. `configs/swing_acceptance.json`
records this filter separately from the already-submitted immutable training config.
Do not select a model exceeding20% simulated DD just because its return is higher.
Latest completed experiments and test provenance: read `RESEARCH_V4_RESULTS.md` first.
Provisional sample floors30 fills/12 months are research safeguards, not user-imposed
requirements or a proof of statistical significance. Forward/mark-price stress still required.
No guarantee of profitability; no live orders, paid compute or unlimited GPU search.

## Implemented architecture

5m/15m/1h/4h/1d closed candles, 128 bars each, plus 40 causal features retaining
drawdown, trend, range and volume context that per-window normalization can erase.
Shared pretrained **Kronos-base** trunk: all 12 blocks, hierarchical embedding,
time embedding and final norm trainable. Old next-token output heads are replaced
by task-specific heads, not trained. Tokenizer-base is frozen. This is **full trunk
fine-tuning**, not frozen embeddings, not LoRA, and not joint tokenizer training.

Macro attention combines 4h/1d. Micro 5m/15m/1h queries macro context through
cross-attention, then entry attention/fusion scores 16 ex-ante bracket candidates:
2 sides × 2 entry offsets × 2 4h-ATR brackets × 3/7-day holding horizon.
Prices are derived from chosen bracket and current ATR/close, not free-form price regression.
No rule assumes a deep drawdown guarantees a rebound, and no explicit reversal
probability head has been calibrated. The model scores trading outcomes and also
learns auxiliary 3/7-day returns; these are not proven reversal alerts yet.

Outputs: conditional mean net, ordered net q10/q50/q90, OHLC fill score,
positive-net score conditional on fill. Unfilled samples are masked for conditional
outcome heads, not for fill head. Ranking uses P(fill) × conditional mean net.
No fixed 55% win-rate gate; asymmetric payoffs can be positive with lower win rates.
Scores remain uncalibrated, and conditional quantiles are not unconditional risk bounds.

## Policy fixed before training

- Candidates require predicted expected net >=0.3%, OHLC fill score >=0.25.
- Signals no more than 4 per UTC calendar month, cooldown 5 days, no forced minimum.
- Causal selection: first eligible events, never hindsight top 4 over the whole month.
- Alerts consume frequency quota even if unfilled; portfolio engine disallows overlapping positions.
- Check decisions every 6 hours (72 ×5m), not every 5 minutes. Intraday windows provide
  context, but this first experiment can miss entry opportunities between decision times.
- Entry limit valid 12×5m bars; offset 0.5/1.5×ATR5m. SL/TPs use ATR4h and 1% minimum unit.
- TP1 50%, TP2 remainder. Holding horizon 3 or 7 days after actual fill. Fixed1x.
- Capital starts at 100 and compounds; fee 0.02% each entry/exit fill; long funding
  0.01% each UTC00/08/16 held, short funding0. 7 days long costs about 0.21% funding
  at unchanged notional, in addition to fees; partial exits reduce funding exposure.
- Stop-first OHLC; intrabar-entry targets suppressed; stop/time exits market-like
  at scenario fee, NOT guaranteed maker. No queue/mark data, DD close-sampled.
- Stress scenario 0.055% fee/fill is an assumption, not verified Bybit fee schedule.

## Immutable data

`data/processed/kronos_swing_20260905_v2`, source three-year BTC snapshot.
128-day macro warmup means actual train decisions start later than raw source start.

| Split | Config interval (UTC, end exclusive) | Samples |
|---|---|---:|
| train | 2023-09-06 to 2025-06-01 | 1992 |
| validation | 2025-06-09 to 2025-09-01 | 308 |
| policy evaluation | 2025-09-09 to 2025-12-01 | 304 |

Labels fully contained in each split; purge maximum2016+12=2028 bars; embargo8 days.
Overlapping labels inside a split mean far fewer independent market events than samples.
Policy interval was part of previously observed v1 development; do NOT call it pristine test.
Likewise unknown overlap with Kronos pretraining limits historical evidence.
No source candles after 2025-12-01 included in cloud upload. Calibration and locked test
are not in bundle. Do not repeatedly tune against the eventual test.

## Training and reproducibility

Kaggle T4×2 required; DDP synchronizes full gradients, each GPU has its own model/optimizer.
VRAM is not combined. FP16 AMP + GradScaler, activation checkpointing, batch1/GPU,
gradient accumulation8 => global effective batch16. Base LR5e-6, heads1e-4.
At most4 epochs, patience2 on validation loss; training timer3000s and kernel limit3600s.
Checkpoint selection based on validation loss, not selected maximum backtest profit.
The script records all block gradient probes and changed-weight probes to verify updating.
Checkpoint saved per improvement; training-state resume is not implemented (optimizer
states are not exported). Do not represent a fresh restart as continuation of an optimizer.

Local CPU full-model smoke with2 samples completed; all12 blocks changed.
37 tests passed before upload, including randomized label parity vs reference engine,
funding/timeouts, conditional masking, causal monthly caps and legacy regressions.
The reference engine now optionally accepts per-signal `holding_bars` <= configured cap;
old signals without that field preserve their prior behavior.

```powershell
.\.venv\Scripts\python.exe scripts/build_swing_dataset.py --output data/processed/swing_NEW
.\.venv\Scripts\python.exe scripts/train_swing.py --dataset data/processed/swing_NEW --output artifacts/checkpoints/swing_smoke_NEW --device cpu --smoke
.\.venv\Scripts\python.exe scripts/package_kaggle.py --dataset data/processed/swing_NEW --output artifacts/kaggle/swing_NEW --owner YOUR_USERNAME --slug swing-new --swing
```

Windows Kaggle2.2.4: set `$env:PYTHONUTF8='1'`, cwd staging/dataset, use `datasets create -p . --keep-tabular`.
Multi-component `-p` upload paths break the CLI on this host. Never pass `--public`.
Wait datasets status ready, then cwd staging/kernel and `kernels push -p . --accelerator NvidiaTeslaT4 --timeout 3600`.
Do not push again while running; inspect existing status/log instead.

Current private dataset: `nguynchtrai/kronos-btc-swing-base-20260905-v2-data`.
Current kernel: `nguynchtrai/kronos-btc-swing-base-20260905-v2`.
Staging: `artifacts/kaggle/kronos_swing_20260905_v2`.
Bundle414609330 bytes, SHA256 `a59d4ccbaa05e60b4a898e0868cb37a069f0cfd1074c9c12a37a908db7ad3a76`.
Bundle allowlists code, development, weights and upstream MIT license. No secrets, no test.
Token stays outside repo in the user's Kaggle config directory; never print or commit it.

## Results and next steps

Submission completed: private kernel version1 is COMPLETE on2 Tesla T4.
Downloaded reports/predictions/runtime to `artifacts/kaggle/swing_results_v2/checkpoint`.
Training took423.87 seconds; best epoch1, stopped epoch3. All12 trunk blocks changed
according to saved update probes. Validation loss worsened after epoch1.
Validation308 and policy304 decisions were all WAIT: max predicted expected net
approximately0.1104%/0.0973%, below the frozen0.3% gate. This does NOT pass acceptance.
Full safetensors weights have NOT yet been downloaded, so a local replay of the
complete cloud checkpoint is still pending. Do not describe local smoke as that replay.
Additional local FP16 GTX1650 smoke passed and audit reproduced checkpoint predictions
and backtest. Full suite now39 tests passes, including closed1d as-of invariance.

Cheap comparator (same fixed policy, no test/tuning): `scripts/swing_tree_baseline.py`.
`artifacts/baselines/swing_tree_20260905_v2`: validation100→111.6082, DD−4.895%,
6 fills; policy100→112.5896, DD−7.306%,8 fills. 4 alerts/month in each interval.
Fee stress remains positive. These are tiny historical development samples, NOT
proof of deployability. Quantiles/conditional win are not estimated by this comparator;
no baseline checkpoint was exported. Do not annualize or extrapolate these returns.

`scripts/audit_swing.py` verifies downloaded weights/code/data and replays selected
development predictions plus reference backtest. `scripts/evaluate_swing_checkpoint.py`
supports explicitly dated, one-shot historical holdout with immutable evaluation manifest;
it refuses smoke checkpoints and dates overlapping development/8-day embargo.
No holdout has been opened by that script yet. Run only after checkpoint is fixed,
and keep later unseen data for subsequent experiments. No automatic repeated test tuning.

`scripts/check_swing_acceptance.py --report <report.json>` applies the user-confirmed
20% drawdown screen plus provisional evidence checks. Tree policy report passes
net/stress/DD/frequency but fails sample/month/heldout evidence; not a live candidate.
No duplicate kernel version or second GPU job was submitted. No recurring monitor
was created. The job is finished; full weights may be retrieved for further analysis.
Tree v3 export and failed holdout, and v4 walk-forward/reserve results, are recorded
in `RESEARCH_V4_RESULTS.md`. Those tests do not establish Kronos profitability.

Submission/results status is updated below after API confirmation; don't infer GPU
allocation or success merely from a push acknowledgement. Download outputs to a NEW
ignored folder, verify hashes, replay predictions, then inspect both costs and gross results.

```powershell
.\.venv\Scripts\kaggle.exe kernels status nguynchtrai/kronos-btc-swing-base-20260905-v2
.\.venv\Scripts\kaggle.exe kernels output nguynchtrai/kronos-btc-swing-base-20260905-v2 -p artifacts/kaggle/swing_results_v2
.\.venv\Scripts\python.exe scripts/infer_swing.py --checkpoint artifacts/kaggle/swing_results_v2/checkpoint --candles data/processed/kronos_swing_20260905_v2/development_candles.parquet
```

Standalone inference returns a candidate, not an executable order or a frequency-limited
alert service. Caller must apply portfolio/monthly cooldown state. No dashboard integration yet.
Walk-forward, calibrated scores, mark/queue stress and independent forward validation remain
necessary. A few winning trades in a 3-month policy interval are not sufficient evidence.
