# R81: wire the actual serving guard and close model/calibrator lineage

Read AGENTS.md and OPENCODE_BACKGROUND_LEADER.md. Continue SAME OpenCode session,
model and permissions, with no --auto, new cloud, heavy training, live orders or
threshold sweep. Preserve dirty work, all existing evidence, ../Kronos and Codex
registry/workers. Register one unique OpenCode R81 direction; leader serializes
ledger. The rejected out-of-project deletion from R79 must not be retried.

## Codex review of R80

R80 finished 2026-09-11T16:46:27Z. Review resumed September14; do not describe the
idle interval as continuous data collection. Mechanical gap and missing-date
fixes are useful. No readiness or economic promotion is accepted.

Confirmed real-model integration failure: supported roll CLI calls
opencode_r77_advisor_core.infer_full, which loads frozen assets and builds rows
directly. R80 added vintage annotations to r76.infer_decisions, a different path.
Codex ran actual core.infer_full on opened 2022 data (one decision): row has NO
causal_eligibility field, while serving_vintage_verdict for the SAME timestamp
returns REJECTED (model fit cutoff2025-11-30). Evidence:
artifacts/research/opencode_background/leader_r80_serving_repro/result.json.
Annotations alone also do not enforce refusal in an action path.

R80 reproduction found stored v15 prediction hashes differ from pinned v29
metadata prediction hashes across seeds. This supports a provenance mismatch,
but not automatically the precise claim that only weights caused it; establish
the actual generating contract or mark unresolved. Frozen calibrators fitted
on another prediction distribution are not validated for these serving weights.

## A. One serving/evaluation contract, actually enforced

- Wire strict provenance/availability checking into the actual core.infer_full
  path used by supported CLI and into its decision-admission boundary. Resolve
  timestamps/hashes from pinned assets, not arbitrary caller-supplied dates.
  Missing, stale or future-vintage provenance is diagnostic/invalid for causal
  evaluation; raw model diagnostics remain visibly integration-only.
- Carry eligibility and its reason through decision records, state, exports and
  acceptance. No eligible decision is implied from the absence of a field.
  Mechanical injected fixtures must explicitly declare fixture mode; they may
  not become production/economic evidence by skipping the guard.
- Distinguish simulated historical fit eligibility, observed bundle presence and
  actual observation times. Use the existing September11 current-attestation as
  evidence only for assets whose bytes still match. Attestation must include
  all actual serving dependencies/configs; changes produce a NEW timestamped
  attestation, never overwrite or backdate the old one.
- Don't chase nonexistent historical deployment logs indefinitely. Unknown past
  availability remains excluded. A valid current attestation establishes an
  honest starting point for future observations, subject to all other gates.
- Reproduce the Codex counterexample on actual checkpoints, then verify the
  supported CLI labels/rejects it. A test of r76.infer_decisions alone is
  insufficient. Include negative cases through actual admission as well.

## B. Bounded lineage resolution and reference disposition

- Inventory only known local v15/reference and v29 checkpoint/download locations
  plus their recorded manifests/scripts. Tie model bytes, train indices/config,
  features/normalization, predictions and calibrators with hashes and date ranges.
  Use the existing opened 35 anchors; avoid whole-history retraining/replay.
- If compatible original weights exist, rerun those anchors with their exact
  contract and compare against stored vectors before calibration. If not found
  within this bounded inventory, explicitly VOID the stored reference as a
  reproduction baseline for the pinned serving bundle. Preserve legacy research
  numbers with labels; don't treat their edge as evidence for this model.
- Audit the iso2/iso4/isoall calibrator inputs and their generating model/version.
  Report supported linkage vs UNKNOWN/mismatch. Do not transplant a calibration
  performance claim across model vintages. No fitting or threshold changes this
  round. Produce a precise next preregistered calibration/research proposal if
  required, using train/validation only and declaring all opened intervals.
- Return one coherent candidate-bundle status: reproducible research-only,
  prospective diagnostic-only, or eligible for supervised paper observation.
  Unsupported economic edge remains NOT_DEMONSTRATED; 3% aspiration unchanged.

## C. Acceptance and practical handoff

- Independent tests must exercise supported CLI -> real raw adapter -> vintage
  decision -> admission/execution, including rejected vintage and unknown data.
  Retain the repaired full/partial gap, pending/TP1 restart, observation-time,
  immutable provenance and cost semantics tests.
- Requirement matrix must include unresolved stored-reference/calibration
  lineage, not only old deployment-log absence. Consume actual test outcomes,
  exact node IDs and matching source/assets. Missing guard fields or mismatched
  evidence hashes withhold PASS. Report engineering readiness separately from
  economic evidence.
- Full .venv/Scripts/python.exe -m pytest after final integration, exact
  pass/fail/skip counts and reasons. One finite current public-data smoke on
  supported CLI with real checkpoints, attestation lineage and no retroactive
  actionable signals. No unattended feed scheduler or trading in this round.
- Provide concise Vietnamese report, runnable command, final hashes, requirement
  matrix and remaining highest-priority step. Stop the bounded round for Codex
  audit; do not ask user to say the word for already-assigned work.

Use no more than three workers, disjoint scopes, with leader-owned integration.
Do not rewrite another runner family: close the existing interface and provenance
gaps. If external approval remains blocked, complete local unaffected work and
report the exact boundary; never bypass a rejected operation.
