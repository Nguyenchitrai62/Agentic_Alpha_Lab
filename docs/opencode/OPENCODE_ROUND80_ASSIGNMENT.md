# R80: correct economic time through gaps and enforce vintage eligibility

Continue this SAME OpenCode background session/model/permissions. Read AGENTS.md
and OPENCODE_BACKGROUND_LEADER.md. No new cloud, training, live orders, threshold
sweeps, ../Kronos or Codex registry/worker edits. Preserve dirty work and earlier
evidence. Register a unique R80 OpenCode direction; serialize ledger in leader.
The rejected recursive deletion of C:/TRAI_NC/Source_code/artifacts in R79 must
NOT be retried or bypassed. Use new output paths inside this repo; leave it alone.

## Codex's independent R79 review

Useful progress: fresh observation anchor, immutable ingest snapshots, inventory
of existing model vintages and honest WITHHELD economics. Overall readiness is
still rejected. Three new deterministic mechanical counterexamples:

1. Backfill changes economic outcomes by consuming execution indices twice.
   Using actual RollingAdvisor/reconcile/settlement and the existing test fixture:
   arm LONG at bar9; with uninterrupted 30 bars, entry fills at bar10 and equity
   is99.98 with an open position. Hide bars10,11,12 and pause, commit+resume with
   the COMPLETE same data: pending is rejected as expired and equity remains100.
   Post-gap indices were allocated while paused; backfill consumes NEW indices
   beyond the original expiry21 even though candle times are identical.
2. Partial backfill incorrectly clears validity: missing bars10,11,12; receive
   only bar10 -> paused=False and unresolved_gaps=[], although11/12 still absent.
   apply_validity_pause tests ANY seen open inside a gap instead of ALL expected
   valid timestamps. Evidence for both:
   artifacts/research/opencode_background/leader_r79_gap_repro/result.json.
3. check_availability(valid_decision,None,None) and (...,'NaT','NaT') return
   ELIGIBLE. pd.Timestamp returns NaT without raising; comparisons silently
   fall through. Evidence: leader_r79_gap_repro/availability_result.json. The
   --claim causal CLI with missing args follows this same fail-open guard.

These are synthetic regression evidence, not economic performance. Fix cause,
not expected test values. Keep all fixes within one reviewed contract.

## A: timestamp-stable execution and complete validity recovery

- Economic clock must be stable across identical data consumed uninterrupted,
  chunked, duplicated, gapped/backfilled and restarted. Prefer immutable candle
  timestamps or absolute 5m grid identity. Do not assign fresh elapsed-time
  indices merely to satisfy monotonic assertions. Pending expiry, holding timeout,
  funding, cooldown and control exits must follow actual candle times. No
  resetting/re-arming pending to conceal the counterexample.
- A gap stays unresolved until EVERY expected valid closed candle is available
  or the run is explicitly censored/invalid. Partial backfill, out-of-order
  backfill, overlapping gaps, repeated pauses and multiple restarts must preserve
  the missing set and positions. Never settle past a still-missing price path.
- Test the Codex full-backfill counterexample with open AND pending positions,
  short and long, TP1 partial, expiry and timeout boundaries. Compare timestamps,
  fills, fees/funding, gates and final portfolio against uninterrupted execution.
- Data rejected for invalid OHLC/grid/close-time must NOT be permanently marked
  economically settled/seen or silently counted as settled. Historical revisions
  need a persistent validity decision; an ingest diagnostic marker alone must
  not erase unresolved uncertainty in an already-open position.
- Latest-new-bar is not sufficient to authorize backdated entry when a feed is
  stale or observed late. Validate decision/observation/earliest-fill times;
  missed next-bar entry is diagnostic unless an explicit delayed-execution
  policy is implemented and independently compared. Preserve pending positions
  whose intent really existed before catch-up.

## B: strict, shared vintage guard and prospective attestation

- Reject missing/null/empty/NaT/UNKNOWN/invalid decision and asset timestamps;
  normalize explicit timezones or reject ambiguous naive values. No exceptions
  or NaT comparisons may yield ELIGIBLE. Test missing CLI args and boundary cases
  as well as the function. Include model AND calibrator fit/label/embargo rules.
- Distinguish simulated historical fit eligibility from actual observed local
  availability. Fold0 calibrator asof=None cannot be casually labeled eligible.
  Fix derived tables and preserve UNKNOWNs. The guard must be used by the real
  causal evaluation/serving boundary, not only an optional standalone --claim
  tool accepting arbitrary dates typed by the caller. Resolve dates from pinned
  artifact provenance; declare mechanical fixture exceptions visibly.
- Historical deployment logs may be unknowable; do not spin on reconstructing
  them or invent dates. Create a local immutable CURRENT availability attestation
  for the existing verified bundle (UTC observed_at, all asset/source/config
  hashes, fit/calibration ranges/unknowns). This authorizes neither past claims
  nor trading. Prospective observations after this attestation can be tracked
  honestly, subject to other readiness gates; never backdate it to2025-12-01.
- On the bounded opened R79 anchors, compare correct per-fold model/calibrator
  raw output to the actual stored historical reference, not only fold2 vs fold10.
  Identify unexplained residual differences. This is reproduction, not holdout
  performance. Reuse cached valid feature work but rerun model as required;
  no new fit, new dataset search, long full-prefix run or parameter change.

## C: acceptance, supported CLI and bounded handoff

- Regression tests must fail on the current code for all three Codex cases and
  pass after repair. CLI smoke and restart must share the actual serving path.
  Never label empty or synthetic evidence as real-model performance.
- Choose ONE supported advisory entry point. Mark older R77 CLI research-only
  or route it through that supported interface; no requirement to maintain two
  separate production-ready implementations. Correct stale line claims: R77
  fresh already uses observed_at; the real issue is missing wrapper safeguards.
- Generate verdicts from actual current test/evidence outcomes with exact node
  IDs and matching source/asset hashes. Existence of a test .py or an artifact
  path plus 'suite green' is insufficient. Stale evidence, changed source,
  missing outcomes and incomplete requirements must withhold PASS.
- Run full .venv/Scripts/python.exe -m pytest after final integration, record
  passed/failed/skipped accurately and skip reasons. Run one finite fresh public
  data smoke through supported CLI, with immutable provenance; no unattended
  feed scheduler or real orders. Preserve old logs and artifacts.

Use at most three workers with disjoint write scopes. Leader performs integration
and resolves all scope handoffs instead of declaring out-of-scope failures left
for the user. Return concise Vietnamese handoff with actual commands, evidence,
remaining blockers and proposed next research step. Codex will independently
review and continue. 3% monthly /20%DD /1x remain aspirations, not acceptance.
