# Round77: integrated stateful advisory runner and independent parity

Codex reviewed round76 source and reran pytest: 269 passed, 1 skipped in
170.13 seconds. Real safetensors inference and the corrected USD-M feed are
useful progress. Overall acceptance is PARTIAL: the components are not wired
into a runnable stateful advisory service and the equity verifier is circular.
Read OPENCODE_BACKGROUND_LEADER.md and AGENTS.md; continue as the same background
worker with the same model/permissions. Register a unique descriptive R77 ID in
your OpenCode ledger, preserve prior artifacts, and do not edit the Codex registry,
its workers/worktrees, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, or ../Kronos.
No cloud, training, live orders, threshold sweep or new model hypothesis.

## Concrete blockers from code review

1. `opencode_r76_feedexec.py:main` in fresh mode parses klines, writes
   fresh_closed.parquet, then RETURNS. It never invokes infer_decisions or
   FeedExecStrategy. The final report still points users at the old R75 replay
   runner. A separate one-off inference smoke is not end-to-end integration.
2. `opencode_r76_parity_verify.py:run_full_comparison` calls P.rebuild_equity
   on BOTH batch_sig and stream_sig. `opencode_r76_parity.py:rebuild_equity`
   calls the same run_backtest in both cases. Thus equal signals trivially
   produce equal equity without checking FeedExecStrategy or FeedExecAccount.
3. FeedExecStrategy.on_bar expects `confidence`; adapter output does not provide
   that field and defaults would drop real signals. WAIT is also not its FLAT
   convention. Define one explicit schema, use the actual frozen score/gates,
   and do not inject confidence=1.0 or turn WAIT into SHORT just to pass tests.
4. Feedexec config still declares stride 12 with a stale 'W1 absent' rationale,
   while the frozen adapter clock is 72 bars on the 6h UTC grid. A positional
   index modulo is not stable when cache windows start at different times.
5. The so-called iso4_only_1x control account is armed only after an OPERATING
   confirmed decision passes busy/daily-halt/divergence checks. It is a mirror of
   the admitted operating signals, not the distinct iso4-only policy. This
   invalidates the frozen control-account DD sizing claim.
6. infer_decisions resets monthly counters and next_allowed on each call.
   It evaluates all eligible historical decisions in its supplied warmup frame.
   Repeated fresh polling needs persistent policy state and a decision watermark;
   it must not reinterpret or emit warmup-history decisions as observed signals.
7. Fresh smoke summary only records candle count, timing and WAIT count; it
   lacks exact range, observed_at, hashes and decision timestamps. Restart
   verifier picked pending state; it did not prove partial-TP1 restart parity.

## Required implementation

Deliver one new clearly named R77 runner CLI whose fresh and replay modes share
the same causal feature/inference/decision/execution interfaces. Factor reusable
components rather than maintain another disconnected mock pipeline. Use up to
three workers only if they have disjoint scopes; the OpenCode leader must perform
the actual integration and executable smoke after all workers land.

- Load/pin the real model and frozen calibrators, validate hashes, preserve UTC
  6h anchor, fetch adequate public USD-M warmup with pagination, cache/provenance,
  and ingest only complete 5m candles. Cache indices cannot be identity.
- Keep feature warmup separate from the declared start of the shadow account.
  Fresh bootstrap must not fill old intents or reconstruct hypothetical trades
  from before observation. A past decision inferred now may be diagnostic only;
  never backdate an actionable alert. WAIT, WARMUP, OFF_CLOCK, STALE and readiness
  errors must remain distinct and record observed_at/decision_time.
- Persist timestamp watermarks, model/policy/config identity, frequency counters,
  cooldown, pending order, partial/open position, operating account, independent
  control account, kill state and deterministic output IDs. Repeated batches,
  overlapping windows and restart must produce the same once-only outputs as
  uninterrupted consumption of the same OBSERVED stream. Reject identity changes
  on resume. Journal outputs/state so recovery does not duplicate fills/alerts.
- Expose raw calibrated iso4-only decisions/geometry and confirmed decisions from
  the adapter; run their independent frozen frequency gates and portfolios.
  Control must evolve even when operating abstains, is busy or is halted. DD
  sizing uses only the independently realized control exits strictly available
  before the operating decision. Do not count current/future information.
- Keep baseline 1x evaluation separate from DD/operational overlays. Explicitly
  version any daily-halt/divergence rules not part of the historical reference;
  compare the same rules in batch and streaming or report the intentional delta.
  Never describe a different policy as bit-identical to confirmed_dd_guard.
- Wire actual model output into execution with an explicit tested adapter.
  Honor TP1 partial exit, TP2, stop-first, next-candle entry, intrabar-entry target
  suppression, expiry/timeout, fees/funding, pending/open boundary state and
  truncation/censoring. Advisory only, with no exchange order adapter.

## Independent evidence (must use the integrated runner)

1. Compare BATCH execution through the existing audited engine versus STREAMING
   execution through the actual incremental account/strategy, fed raw candles
   and real checkpoint outputs through the runner. Do not call run_backtest on
   the streaming side. Do not supply prerecorded signals, control exits or
   prediction tables to its inference path.
2. Include compact semantic fixtures for long AND short, TP1 then stop/TP2,
   ambiguous entry/stop/target order, timeout and funding boundaries, expiry,
   pending restart AND partially exited position restart. Compare each fill,
   quantity/remaining size, gross PnL, fees, funding, net equity and timestamps.
   Include normal, fee stress and explicit execution stress; disclose any
   unsupported scenario and withhold a global PASS until it is implemented.
3. Test the verifier itself with negative controls: deliberately wrong TP1
   fraction, fee, entry timestamp, or control routing in a test double must
   make parity FAIL. Matching two invocations of one engine is insufficient.
4. On an already-opened development slice, exercise real checkpoint predictions,
   both WAIT and non-WAIT without changing thresholds. Rebuild features and
   rerun the model for prefix/future perturbations; compare numeric predictions,
   features and geometry (with justified tolerance), not only action strings.
   Chunk partition/rolling-window/restart parity must cover frequency state.
5. Run a finite fresh public-data invocation through this same CLI. Persist full
   source range/hash, observed timestamps, model/config/source identities,
   actual inference call evidence, readiness, decision/abstention records and
   state. If off clock, test real inference diagnostically but label it nonactionable;
   do not pretend a historical decision is a timely new signal. No unattended
   feed/trading scheduler in this round. Provide the exact working CLI commands.
6. Run full pytest after final integration, record pass/fail/skip counts and
   source hashes in the final manifests. Preserve/label earlier limited evidence.
   Report completion only against these R77 requirements, not a recycled R75
   A-C summary. Return the working command and independent artifacts to Codex;
   Codex will audit and dispatch the next bounded round automatically.

Stop model research until this integration gap is closed. There is concrete
local engineering work here; do not conclude that all remaining work needs
cloud training or months of waiting. No profitability/promotion claim.
