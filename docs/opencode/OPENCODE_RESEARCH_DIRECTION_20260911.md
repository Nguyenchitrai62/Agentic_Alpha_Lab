# OpenCode assignment: practical signal advisory pipeline

Date: 2026-09-11. Assigned by Codex on the user's explicit request to inspect,
redirect, and delegate work to the existing OpenCode session.
Recipient: `ses_f84183f7effekxCq6LK0D3D8O0` (Chuyển skill Codex sang OpenCode).

## Objective and authority

Continue the existing project toward an evidence-backed BTC signal advisory
system. Deliver a runnable, read-only shadow/paper pipeline and an honest
assessment of its edge. This assignment is authorization to perform the local
audit, implementation, tests, and replay below. Do not end with another menu
asking the user to invent a hypothesis. Work through the bounded deliverables.

The user's 2026-09-09 instruction accepted 3% monthly instead of the old 5%
aspiration and asked for realistic testing on several recent months to one year.
Keep 3% as a reported aspiration, not a promise or a reason to force trades.
Keep the 20% drawdown tolerance, fixed 1x baseline, and existing research rules.
Do not retrospectively rewrite old 5% verdicts. Separate operational readiness,
statistical evidence, and the user's return aspiration in new versioned output.

This assignment does not authorize live orders, exchange trading credentials,
paid compute, or a new cloud upload. Heavy training is not needed for this round.
Keep existing checkpoints. Do not change the user's current OpenCode model.
Do not touch ../Kronos or other Codex worktrees. Preserve existing uncommitted work.

## Findings to resolve

1. The last response (2026-09-10 01:47 UTC) calls seven opened historical OOS
   evaluations a pristine forward window. The data hash being unchanged proves
   integrity, not independence. Once returns influence candidate choice, that
   interval is development evidence for later choices. Audit the exposure
   timeline; do not assume all seven candidates were registered before any
   result was observed. A later date than model training is not sufficient to
   prove prospective deployment or selection independence.
2. `configs/opencode_hypothesis_ledger.json` and
   `configs/opencode_forward_protocol.json` still contain a 0.05 monthly gate.
   The latter counts months using first/last trade exit, while the evaluation
   span is approximately 2026-03-23 through 2026-09-08. This can count partial
   months as full months and omit zero-trade months. Use one explicit evaluation
   interval for returns, exposure, calendar bins, and elapsed duration.
3. `artifacts/research/opencode_v159_fwdevaltop3/summary.json` reports
   NO-IN-SAMPLE-BASELINE and paper NOT_GREEN for each of the three candidates.
   Existing rehearsal evidence from another policy does not validate these
   policies. Close this exact identity/parity gap before making readiness claims.
4. The latest cloud result in round72 is Regime-MoE: replay error 4.29e-6,
   rank +0.0675 versus +0.0741 single-model reference, negative monthly returns
   in all scenarios, and roughly 38-58% DD. Verify from saved artifacts, preserve
   this rejection, and do not retrain it without a materially new hypothesis.
5. Research audit counters (13/13 reproduction, 4/4 seals), arbitrary p=0.2
   fill thinning, and a favorable result after dropping trades do not establish
   queue realism, statistical significance, or profitability.
6. The saved top-three summary is less favorable than the last prose response:
   L3-combo monthly is +0.356% normal, +0.142% fee stress, and -0.138% execution
   stress (19/19/17 trades). Confirmed_dd_guard is +1.209%/+1.069%/+0.824%
   with 11 trades in each scenario. Band2 has only two trades. These are observed
   historical outcomes, not expected future returns. Explicitly correct the
   implication that all deployable-shaped books remain positive under stress.

## Working protocol

Read AGENTS.md and TRAINING.md. The OpenCode ledger is a separate namespace
from research/parallel/registry.json (the latter currently has v82/v84/v88 active).
OpenCode already reuses bare v159/v160 for different objectives. Register a
unique descriptive round75 ID in the OpenCode ledger, check existing IDs, and
record objective/data/policy contracts before changing research logic. Do not
write the Codex registry or its CONTINUOUS_RESEARCH.md/NEXT_AGENT.md files.
Keep the shared OpenCode ledger leader-only. If using up to three existing
workers, give them disjoint new paths and serialize integration yourself.

Use ignored `artifacts/research/opencode_r75_practical/` for evidence and
reports. Use descriptive new source/config/test filenames, not recycled vNN.
First write a short acknowledgement and ordered task list, then execute.

## A. Evidence and evaluation contract

Produce `evidence_audit.json` and `EVIDENCE.md` with precise artifact paths,
hashes, model fit/calibration dates, test ranges, candidate registration times,
first metric exposure times, and selection dependencies. Mark uncertain exposure
as UNKNOWN, never clean by default. Preserve old reports and append corrections.

Classify datasets as development, historical OOS already observed, genuinely
untouched holdout (only if demonstrated), or prospective shadow. Do not recrawl
the same opened months and call them a new test. If no untouched recent interval
exists, say so; implement nested/purged chronological development evaluation and
start a later prospective collection contract. New candles cannot retroactively
make an old selection process independent.

Make a new versioned assessment contract: operational readiness; net-positive
evidence under normal/fee/execution costs; 3% monthly aspiration; 20% DD;
trade count/duration/concentration/uncertainty. Report INSUFFICIENT_EVIDENCE
separately from a measured performance failure, and allow both findings at once.
Do not relax sample safeguards or promote a candidate on an incomplete sample.
Retain the old 5% outcome as historical reference.

Report all rows with gross PnL, fees, funding, net PnL, monthly geometric return,
drawdown, filled trades, offered/eligible decisions, coverage, long/short splits,
and exposure. Include empty months and the full declared interval. State DD
sampling limitations. Add block-based uncertainty on development evidence where
useful, with blocks at least as long as overlapping holding windows and clear
limitations from few independent observations. Do not call 30 fills proof.

## B. Streaming parity and execution realism

Choose ONE frozen reference policy for plumbing before any additional metrics.
Use confirmed_dd_guard/v29 as the default because its chain is simpler; this is
a diagnostic reference, not a winner promoted from observed OOS. Keep L3-combo
as a frozen comparison if its complete chain is available. Persist exact policy,
weights, calibrators, feature schema, source hashes and cost identity.

Build a clock-driven replay that exposes only data available as of each decision
and runs the same feature/inference/policy/state interfaces used by shadow mode.
Feed it sequentially and compare with the existing batch reference. Verify
prefix invariance: appending/changing future candles cannot change earlier
features, signals, orders, sizing, or state. Audit backward higher-timeframe
joins, funding publication/as-of timing, and any top-k/percentile/fallback logic
that might inspect the entire evaluation window.

Enforce closed candles, next-candle entry, expiry/cancel, one consistent portfolio
state, stop-first, full holding-window accounting, and no backdated fills.
Check reference-equity DD sizing uses only realized information then available.
Test restart/resume, duplicate/out-of-order/missing/stale bars, deterministic
alert IDs, and exactly-once output. Account explicitly for positions/pending
orders across evaluation boundaries and censored tail observations.

Use 1m/public data already available to resolve ordering where possible; keep
ambiguity explicit otherwise. Entry/TP limit fills need conservative assumptions;
stop/timeout remain market-like with slippage and scenario fees. Do not estimate
maker queue probability from OHLC. Any probabilistic fill test must be labeled
an assumption sensitivity, use fixed seeds/multiple draws, and report the full
distribution rather than selecting the favorable draw.

Deliver `streaming_parity.json`, `execution_gap_report.md`, and meaningful tests.
Stop candidate promotion if parity or causal invariance fails; repair the engine
or adapter and label changed results as a new version on development data.

## C. Runnable advisory shadow service

Reuse the existing paper trader v2.1 components where appropriate. Build a
single-command local runner that uses public closed-candle data and outputs
LONG/SHORT/WAIT plus decision/observation time, entry, stop, targets, expiry,
policy/model identity, data freshness, and reasons for abstention. Label model
scores as scores unless their probability calibration has actually been tested.
Log all eligible decisions including WAIT, alerts, simulated fills/cancels, and
portfolio state append-only, with reproducible manifests and restart parity.

Add safe WAIT/halt behavior for missing/stale data, missing checkpoints,
nonfinite outputs, and risk limits. Keep read-only and research/shadow labeling.
No exchange order adapter or external messaging integration is needed.
Provide a same-policy rehearsal of start, signal, expiry, stop/kill, restart,
and continued operation. Make the fixture/replay exercise distinguishable from
fresh market observations. A successful rehearsal establishes functionality,
not trading edge. Do not create unattended schedules as part of this round.

## D. Next hypothesis only after A-C

Use decomposition of actual misses to choose at most ONE new hypothesis with a
falsifiable mechanism and a cheap development-only kill test. Compare the model
against WAIT, a constant/global action-prior policy, and the available cheap
baseline under the identical clock, geometry, costs, folds and portfolio engine.
No broad threshold, architecture, frequency-cap, leverage or ensemble sweep.
No new cloud job until the cheap probe demonstrates incremental value and its
data/execution contract is credible. If it fails, document the negative evidence;
do not claim every possible research direction is exhausted.

## Completion and handoff

Run `.venv/Scripts/python.exe -m pytest`; report exact pass/fail/skip counts.
Provide one concise status with runnable command, manifests, remaining evidence
gaps, and next measured action. The round is complete only when A-C artifacts and
same-policy rehearsal exist (or a concrete blocker is documented with unaffected
work finished). Do not claim the overall profitable-system objective achieved.
Do not stop solely because a profitable model or a 3% monthly guarantee cannot
be proven today. Stop new experiment spawning at this bounded round's end and
return the deliverables for review.
