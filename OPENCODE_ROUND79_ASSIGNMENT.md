# Round79: observation-time correctness and checkpoint vintage audit

Continue the SAME background OpenCode session/model/permissions. Read the leader
contract and AGENTS.md. The user already authorized continuous delegation; do
not end with 'say the word'. Codex reviews each bounded handoff and assigns the
next. Preserve all previous evidence and dirty work. No cloud, training, orders,
threshold tuning, ../Kronos or Codex registry/workers edits. Register a unique
OpenCode R79 direction; only your leader serializes that ledger.

## Codex R78 review

Accept useful rolling-index and crash-replay fixes as components, not overall
readiness. R78 ended with vintage audit unfinished and contradictory/stale
acceptance metadata. Further concrete failures were independently identified:

1. CONFIRMED fresh bootstrap backdates a position. Actual R78 CLI with only
   network/model replaced by a deterministic fixture: observed_at 07:10:01Z,
   shadow_start set to first historical close 05:55Z, LONG decision 06:05Z,
   filled at historical next bar, equity already99.98 at bootstrap. Evidence:
   artifacts/research/opencode_background/leader_r78_bootstrap_repro/leader_result.json.
   This is a mechanical test, not model/performance evidence. CLI main sets
   shadow from df.iloc[0] in BOTH modes; 24-bar staleness cannot fix this.
2. R78 raw_candles.parquet is written only if missing. A resumed new window's
   manifest reports its new range/count but still hashes the original file.
   Save immutable per-ingest snapshots and associate each commit with exactly
   the bytes consumed. Include bootstrap/resume observation times and lineage.
3. reconcile_window records gaps but still sends bars across the gap to
   settlement. Recording a missing stop/timeout candle does not make resulting
   fills/equity valid. Revisions are logged while incoming revised data can
   reach inference. Define explicit invalid/paused handling and restoration.
4. W2 confirms fold10-everywhere vs per-fold historical checkpoint mismatch.
   Its old-period trades cannot establish causal historical returns without
   model/scaler/calibrator fit and availability checks. This audit was explicitly
   authorized in recovery; complete it without another user menu.
5. Final requirement_matrix still reports R5 FAIL and obsolete R77 bug notes
   despite new kill evidence, and does not include the vintage blocker. Source,
   config, current evidence and acceptance verdict must agree at handoff.

## Work (up to three workers, disjoint scopes; leader integrates)

### A. Make observation-time and feed validity correct

- Fresh bootstrap starts at actual observed_at. All pre-observation inference is
  diagnostic-only: zero actionable intents, fills, gate consumption, funding or
  account PnL from historical warmup. Test on-grid/off-grid bootstraps with both
  LONG and SHORT raw fixtures and multiple historical fill opportunities.
- For resume/catch-up, decision time and time advice becomes available differ.
  No new intent may fill on a candle that occurred before actual availability.
  Either make missed-clock decisions diagnostic, or specify and implement a
  separately versioned delayed-entry policy shared with its batch reference.
  Preserve already-observed pending/open positions causally through catch-up.
  A 2h signal-age rule does not authorize retroactive next-bar execution.
- Gaps/revisions/invalid bars: fail closed or pause affected accounting/readiness
  until verified backfill/reconciliation. Do not synthesize missing candles or
  settle a position through unobserved price paths. Preserve original state and
  evidence; no silent rewriting historical fills. Handle both empty and open
  portfolios; restored data must recover without duplicated outputs.
- Fix per-ingest immutable raw provenance and test hash/range consistency on
  at least two shifted windows with distinct bytes. Identity must cover actual
  inference/execution implementation dependencies and all frozen assets.
- Consolidate/document the supported CLI. R77 and R78 paths must not each claim
  complete readiness while providing different safety/recovery behavior.

### B. Complete the bounded vintage audit (local existing assets only)

- Inventory all 11 folds and three seeds: actual checkpoint hashes, train/val/
  label end, embargo, scaler fit range, calibrator fit/end and availability
  evidence. Separate historical simulated fit cutoff from actual file creation
  and deployment availability. Unknown metadata stays UNKNOWN, not invented.
- Trace reference per-fold routing and frozen fold10 serving explicitly. On the
  already-opened known anchors, rerun raw features with the CORRECT existing
  historical weights as a separately labeled reproduction mode. Compare first
  numerical divergence by stage/seed/geometry/action, preserving the fold10
  mismatch evidence. Do not tune or relabel it an untouched holdout.
- Enforce availability checks for performance/forward claims. Future-vintage
  model or calibrator at an old decision must be rejected for causal evaluation
  (may be labeled integration-only). Include boundary negative tests. Merely
  selecting per-fold model does not cure a future-fitted shared calibrator.
- Produce a clear eligible interval / excluded interval table and the exact
  existing bundle eligible for prospective observation. No new training needed
  to inventory/route existing assets. No profitability promotion this round.

### C. Independent integrated acceptance

- Regression must reproduce Codex bootstrap bug before repair and fail on its
  reintroduction. Cover delayed catch-up, gaps/revisions, raw snapshot provenance,
  pending and partial position restart with nonempty raw decisions. Test actual
  supported CLI; mock inputs only for mechanics, label them explicitly.
- Reuse prior valid execution semantic/stress tests, avoid long full-history
  reruns that add no evidence. Real checkpoint reproduction uses B's declared
  bounded anchors. Any baseline/overlay mismatch is explicit, not parity PASS.
- Generate a fresh complete requirement matrix from current evidence with
  source hashes and test counts. Include observation safety, vintage eligibility,
  real-model reproduction and unresolved prior requirements. No self-referential
  evidence or documentation claim should count as economic-edge PASS.
- Full .venv/Scripts/python.exe -m pytest after final integration. Record real
  counts and skip reasons. Preserve old artifacts, append superseding verdicts.

Return concise Vietnamese handoff with exact working CLI, source/config hashes,
actual evidence files, all remaining blockers and next highest-value work. End
the bounded round for Codex review; do not ask the user to authorize the audit
again. User aspiration3%/month, DD20% and1x remain goals, not evidence of success.
