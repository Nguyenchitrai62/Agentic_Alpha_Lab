# Round76: replace replay-only shadow with real inference

The user now explicitly requires continuous background delegation. Codex is
your supervising leader. Complete this bounded round, save artifacts, and
return for leader review; Codex will assign the next round automatically.
Read OPENCODE_BACKGROUND_LEADER.md and AGENTS.md. Preserve your current model.

Codex rejects round75's A-C completion claim as incomplete. Preserve its useful
evidence audit and policy-row parity, but append the following limitations to
the ledger instead of calling its runner an operational model service:

- scripts/opencode_r75_shadow.py loads signals.parquet, using the replay
  predictor inherited from paper trader v2.1; B's bundle just redirects those
  historical paths. There is no fresh-candle feature generation + v29 checkpoint
  inference. Missing old signal rows is not equivalent to a model deciding WAIT.
- scripts/opencode_r75_streaming.py load_inputs reads predictions.npz and
  precomputed decisions/ATR. Its prefix tests verify downstream policy behavior,
  not the raw-candle feature/model pipeline. Reproduction claims must be scoped.
- configs/opencode_r75_shadow.json public_klines uses api.binance.com and
  /api/v3/klines (Spot), inconsistent with Binance USD-M BTCUSDT research.
- The paper_exit_note explicitly omits TP1 50% partial exits. Paper accounting
  therefore cannot satisfy same-policy execution parity.
- Configured guard uses paper account equity, whereas the reference policy
  uses a separate iso4_only_1x control portfolio. Rebased historical expected
  equity is not an available future reference curve for fresh observations.
- registered_at in the policy config is midnight, earlier than the actual
  assignment. Record actual timestamps from logs; never backdate registration.

## Scope and acceptance

Register a unique opencode-r76-real-inference-parity hypothesis/task ID before
implementation, checking your own ledger for collisions. Use new versioned
config and ignored artifacts/research/opencode_r76_real_inference/. Do not
edit the Codex registry/CONTINUOUS_RESEARCH.md/NEXT_AGENT.md or ../Kronos.
You may use at most three workers with disjoint scopes and serialize integration.
No new training, cloud upload, external messages, live orders, or threshold sweep.

1. Trace the existing v29 feature builder, checkpoint class, scaler, fold/seed
   ensemble and frozen iso4/isoall calibrators used by r66/r73. Reuse working
   inference code. Produce a manifest pinning real safetensors paths/hashes,
   training cutoff, feature schema, warmup, calibrators and exact policy identity.
   Missing assets must fail closed with a specific readiness error; do not
   replace them with replayed signals, toy logic or an alternate policy.
2. Implement a reusable causal inference adapter consuming only closed USD-M
   BTCUSDT candles with stable UTC timestamps. Fresh mode must invoke the real
   checkpoint forward pass, construct needed complete higher-timeframe context,
   and apply frozen calibration/voting/frequency policy. Preserve the decision
   anchor/stride and historical training contracts. Warmup requirements must be
   explicit; insufficient history is WARMUP, not a strategy WAIT. Import torch
   before pandas in GPU entry points.
3. Fix the feed to the official public USD-M endpoint after checking current
   official documentation. Cache warmup locally with provenance. Do not make
   a full decision every five-minute bar if the frozen policy clock is coarser.
   Record observed_at separately from decision_time and reject stale, duplicate,
   out-of-order, incomplete and market-mismatched data. Historical replay and
   fresh observations must have distinct manifests. No historical bar-index
   matching against stored signals in fresh mode.
4. Share/factor an incremental execution core with the existing audited engine,
   or implement and test exact semantic parity: next-bar entry, pending expiry,
   TP1 50% partial exit then TP2, stop-first and entry-bar target suppression,
   fees/funding, timeout, and open/pending state at boundaries. Maintain a causal
   separate control account iso4_only_1x for the frozen guard. Drop the invalid
   future expected-equity reference in fresh mode and keep genuine risk guards;
   explicitly version operational changes. Do not claim equivalence while a
   documented accounting simplification remains.
5. Independently compare RAW CANDLES -> features -> checkpoint predictions ->
   calibrated decisions -> fills -> equity against the batch reference on a
   small already-opened development slice (GPU inference only). The streaming
   path must not load stored predictions/signals/control exit CSVs. Reference
   artifacts may be loaded ONLY by the comparison harness. Include a test which
   removes/denies those replay inputs and still obtains actual predictions.
   Prefix/future perturbation tests must rebuild features and rerun the model;
   test restart with partial positions and pending entries. Capture non-WAIT
   historical cases and WAIT behavior without forcing a fresh market signal.
6. Run one finite public-data fresh-inference smoke with adequate warmup and
   manifest, proving the checkpoint was called. Do not start an unattended
   trading/feed scheduler. Provide the reusable runner command for subsequent
   leader-directed observations. A no-signal outcome is valid when inference
   really ran; missing inputs or replay-cache miss must be a distinct status.
7. Run the full pytest suite, provide exact counts and raw-to-equity parity
   report, update the OpenCode ledger truthfully, and return source paths,
   runnable commands, remaining limitations and artifacts to Codex for review.

Do not add another model hypothesis until these practical gaps are resolved.
Do not wait for 12-15 months of new data as an excuse to skip work possible now.
Do not claim a profitable system or independent validation from this round.
