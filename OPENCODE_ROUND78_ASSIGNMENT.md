# Round78: reliable rolling observation and nonempty end-to-end evidence

Continue the SAME OpenCode background session under Codex supervision. Read
OPENCODE_BACKGROUND_LEADER.md and AGENTS.md. Preserve model/provider/permissions,
existing dirty work, all prior evidence, and the separate Codex registry/workers.
No Kronos edits, cloud submissions, heavy training, new model, threshold tuning,
live orders, or authenticated trading. The goal remains practical read-only
advisory, with a 3% monthly aspiration reported separately from readiness.

## Codex review of R77

Useful progress: unified CLI, real checkpoint adapter, independent control gates,
execution fixtures and negative controls. Overall readiness is REJECTED/PARTIAL.

1. CONFIRMED functional bug in actual CLI: start_bar = last_bar_idx + 1, followed
   by start_bar >= len(df), makes a fresh rolling window of unchanged length
   return 'nothing new' forever. Timestamp watermark is saved but not used to
   select the new suffix. Codex reproduced with only network mocked: old close
   2026-09-10 00:14:59.999Z, new input through 00:19:59.999Z, unchanged watermark,
   zero inference calls. Evidence:
   artifacts/research/opencode_background/leader_r77_rolling_repro/result.json.
   Larger/shorter windows and local/global index remapping are also unproven.
2. R77 verifier says overall PASS while explicitly recording zero non-WAIT real
   decisions and unsupported streaming execution_stress. Fixture success does
   not substitute for a real-model nonempty end-to-end path. Do not reuse that
   overall PASS as acceptance. Correct it via an appended/superseding assessment
   that preserves the original artifact.
3. State is overwritten directly with write_text; outputs are written afterwards
   separately. No demonstrated crash consistency or recovery of outputs after
   the last state commit. Identity records omit implementation source hashes;
   declared asset hashes are not a substitute for actual files checked on resume.
4. Fresh smoke manifest has candle counts but lacks exact source range/hash or
   a persisted candle snapshot. Its 50 DIAGNOSTIC rows and zero actionable
   decisions must be described accurately. No deployment/profitability claim.

## Work packages (maximum three workers, disjoint scopes)

OpenCode leader owns integration and serialized ledger writes. Register one
unique descriptive R78 direction in OpenCode's ledger, not Codex's registry.
Assign owners explicitly; do not let two workers edit the runner/core together.
Prefer repairing/factoring the existing interface over another disconnected
runner family. New version/config must identify changed behavior.

### W1: rolling CLI and durable state

- Use market + timestamp identity to reconcile overlapping windows, select only
  unseen closed candles, and map local inference indices to stable execution
  indices. Preserve pending orders/partial positions, monthly/cooldown counters,
  control and operating portfolios across sliding cache origins and restarts.
- A same-length shifted window MUST settle its new bars. Identical windows are
  idempotent. Cover shorter/longer overlap, month boundary and UTC 6h anchor.
  Detect historical OHLC revisions, gaps/out-of-order/nonfinite/forming bars;
  never silently bridge missing execution bars or treat stale catch-up signals
  as timely new alerts. Specify a bounded timeliness policy before implementing.
- Keep bootstrap history diagnostic-only. Observation time, decision time and
  intended earliest entry are explicit. Catch-up evidence may be reconstructed
  diagnostically but must not backdate actionable outputs.
- Atomic durable checkpoint and journal/output recovery with deterministic IDs.
  Test actual CLI interruption before/after commit and before/after export, not
  merely an in-memory snapshot. Corrupt/truncated state must fail clearly or
  recover from a verified last committed generation. Rebuild missing exports
  even when no new candles arrive. Do not corrupt existing user's artifacts.
- Pin current relevant source/config/all model/calibrator identities and verify
  actual files before resuming. Changed identity needs explicit new run; do not
  accept a declared hash when bytes differ.
- Fresh snapshot/provenance: exact first/last candle, row count, immutable local
  raw-candle artifact/hash, fetched/observed timestamps, source and checkpoint
  hashes, status counts, real inference evidence, diagnostic/actionable counts.

### W2: real-model non-WAIT pipeline evidence

- Use already-opened development data only; record the chosen interval BEFORE
  execution. Historical known signal timestamps may locate integration fixtures
  but never feed stored predictions/signals into the model path or claim an
  unbiased performance estimate from this selection. Keep checkpoint, geometry,
  calibrators, thresholds and gates frozen. Budget a bounded local inference
  scan (one existing development interval, no parameter sweep).
- Rerun raw features and real checkpoint outputs on a slice that exercises WAIT
  and non-WAIT, admitted intents and settled trades through the actual runner.
  Include enough causal warmup and complete holding windows. If the frozen
  implementation never reproduces a previously known signal, diagnose feature,
  clock, checkpoint or calibration mismatch and provide the first numerical
  divergence; do not call training the only remaining remedy.
- Compare raw numeric outputs, geometry, independent policy gates and actual
  incremental fills/equity against an independent batch reference under the
  SAME declared policy. Fixed 1x baseline must be distinct from overlays.
- Rolling-window/chunk/restart comparison must involve nonempty frequency and
  portfolio state. Stored inputs may be read by the reference for diagnosis;
  deny them to the tested raw-model path. Do not force trades or fabricate
  confidence. If unavailable, mark the requirement BLOCKED with exact evidence.

### W3: independent acceptance and execution stress

- Write CLI-level regressions for W1's reproduced rolling bug and crash/output
  recovery; coordinate interfaces without editing W1's files. Test pending and
  partial-position continuation through the integrated runner, not just account.
- Add a clearly versioned deterministic adverse-fill/slippage stress scenario
  to the incremental execution path and independently compare with its batch
  counterpart. This is scenario analysis, not a claimed maker-fill probability.
  If broad support is too large, implement one documented bounded scenario and
  state precisely what remains unsupported; never label incomplete matrix PASS.
- Retain semantic long/short, TP1/stop/TP2, expiry/timeout/funding and deliberate
  wrong-fee/TP1/timestamp/control negative controls. Positive counts matter:
  empty comparisons are EMPTY/NOT_EXERCISED, not passing evidence for trading.
- Generate one machine-readable requirement matrix with PASS/FAIL/BLOCKED/
  NOT_EXERCISED and source artifact links. Required incomplete checks prevent
  overall PASS. Distinguish operational readiness, scenario robustness and
  economic edge. Do not imply an execution fix improves returns.

## Leader integration and handoff

Run full .venv/Scripts/python.exe -m pytest after final integration; record real
counts, skips/reasons, command, source hashes and dates. Run a finite fresh CLI
smoke and at least two controlled shifted-window resume invocations through the
same CLI. No unattended feed scheduler in this round. Return actual evidence
paths, command, remaining highest-priority blocker, and a concise Vietnamese
report to Codex. End the bounded round; Codex audits and assigns the next one
automatically. Do not offer the user another menu or claim all work needs cloud.
