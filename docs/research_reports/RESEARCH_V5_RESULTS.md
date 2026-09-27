# Kronos v5 — completed, fails trading usefulness

2026-09-05. Private Kaggle `nguynchtrai/kronos-btc-swing-v5-20260905`,version1.
Confirmed2 Tesla T4, FP16 DDP;100321928 trainable parameters,3958042 frozen tokenizer
parameters,12 updated trunk blocks. Train4448, validation308, policy752 examples.
Policy covers previously researched2025-09 through2026-03; NOT independent test.

| Epoch | Train loss | Validation loss |
|---|---:|---:|
| 1 (selected) | 2.01985 | 1.44078 |
| 2 | 1.86703 | 1.69918 |
| 3 | 1.56274 | 1.96601 |
| 4 (early stop) | 1.36123 | 2.06310 |

Runtime1204.60s. Both validation/policy ALL WAIT,0 fills,equity100,net0/DD0.
WAIT avoids losses but does not meet the user's useful trading-signal objective.
Do not present this as successful risk control or compare v2/v5 raw loss directly:
loss definitions differ. v2/v5 dataset decision grids also differ because source
start timestamps determine stride anchoring. Later probes use exactly v5 decisions
on both branches to avoid that comparison confound.

Saved-head diagnostics against train-only per-candidate constant net predictor:

- Validation MSE6.56286 vs constant6.07160:8.09% worse.
- Policy MSE14.73058 vs constant13.75912:7.06% worse.
- Expected net ranges: validation[-1.10385,-0.100883]%, policy[-1.17931,-0.099899]%.
- Only candidate4/12 ever rank first before abstention. Output varies more than
  v2 but usefulness has not improved. Relative validation loss rising while train
  decreases suggests poor generalization; it does not uniquely prove model size
  or loss is the cause. Robust/ranking objective can change output calibration.

Full checkpoint `artifacts/kaggle/swing_results_v5/checkpoint/swing.safetensors`
SHA256 `e0d216b34179cd5ed8c45736dce9f527f0767ac561f033abf03bc7aeb8706fa1`.
`artifacts/research/swing_v5_cloud_audit.json`: all saved hashes verified,8 predictions
replayed per split on localGPU; maximum absolute output difference0.004114/0.004849
(FP16/device differences), saved-prediction backtests match. This checks integrity,
not calibrated probabilities or real-world execution. v2 full audit now also passed.

## Next experiments already in progress

- v6 probe: freeze v5, extract768-dimensional macro/micro/feature context; fit
  train-only PCA32, then compare same ExtraTrees head on raw40 vs raw40+context.
  Seeds1729/1730/1731, no threshold sweep, same v5 labels and decisions. Trained
  v5 used validation for checkpoint selection, so this is development only.
- v7 probe: existing buy-volume imbalance and number-of-trades activity across
  fully closed5frames, PCA16 fitted only on train, same three-seed tree comparison.
  Feature-cache generation and model comparison completed, both branches FAILED.
  No new API data
  or public upload. Flow fields are interpreted as existing dataset schema.
- Execution sensitivity now includes2/5/10bps limit penetration and adverse
  market exit slippage, no limit price improvement, market exits0.055% fee. New
  engine leaves old frozen code unchanged, zero-stress parity tested. Use
  `scripts/stress_saved_signals.py` to reprice saved signals without regenerating.

v4 sensitivity at10bps remains+5.04235%, ONE fill. Adverse-price sampled DD4.43273%
vs close DD4.22281%. It is not queue simulation or true intrabar/mark DD and does
not cure tiny-sample evidence. Sensitivity scenarios are assumptions, not verified
exchange execution prices/fees. No leverage, live orders or profit guarantee.

Continuation/process state is maintained in `CONTINUOUS_RESEARCH.md`.77 tests pass.
Do not stop research merely because this experiment is finished; no usable model yet.

## v7 completed ledger (development, not test)

Same v5 policy and same decisions for both branches, train-only PCA and forests.
At each seed, policy results below are AFTER normal fees/funding at1x:

| Branch | Seed | Policy net | Policy DD | Fills |
|---|---:|---:|---:|---:|
| raw40 | 1729 | -20.3310% | 24.0278% | 16 |
| raw40 | 1730 | -12.2551% | 16.1876% | 16 |
| raw40 | 1731 | -19.6933% | 25.6693% | 16 |
| raw40+flow/PCA16 | 1729 | -23.6995% | 24.1644% | 15 |
| raw40+flow/PCA16 | 1730 | -31.6113% | 33.5003% | 16 |
| raw40+flow/PCA16 | 1731 | -26.2512% | 32.4042% | 10 |

Validation has0 fills for seeds1729/1731, and1 for1730 (raw+4.3752%, flow+2.6174%).
These isolated validation wins do not rescue the negative policy outcomes.5bps
execution-stress policy net remains negative for all6 fits. More difficult fills
occasionally improve aggregate results by removing losers; not evidence that worse
execution is beneficial. No new model selected, no live approval.

## Loss interpretation issue for subsequent experiments

The v5 head's point estimate is trained with Huber plus utility-ranking objectives.
Neither objective makes that output a calibrated conditional arithmetic-mean
return. Therefore the inherited `expected_net_percent` field/0.3% gate is a
heuristic score interface, not a demonstrated expectation. This may contribute
to abstention, but it is not a proven sole cause of failure. Do not rewrite the
frozen results or silently reinterpret a score as a win probability.

Next separate a mean-payoff objective (including unfilled zero utility) from
tail-risk/ranking/WAIT logic, or calibrate scores using strictly chronological
out-of-fold development outcomes. The v6 frozen-context/tree probe uses explicit
unconditional payoff targets and tests whether the neural representation adds
information with the same downstream estimator; its cache is still running.

## Continuation audit: decision clock

2026-09-05 heartbeat added optional `decision_anchor_utc` support to the neural
dataset builder; no old source snapshot or dataset was regenerated. Audit
`artifacts/research/decision_clock_audit_v1.json` verifies that dropping50 leading
source candles no longer changes common decision timestamps with the explicit
anchor. Config omission preserves positional legacy behavior.83 tests pass.
Use1970-01-01T00:04:59.999Z anchor with stride72 for future controlled comparisons.
