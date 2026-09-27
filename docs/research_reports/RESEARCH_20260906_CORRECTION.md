# Research correction and updated target, 2026-09-06

Correction IMPLEMENTED and v17 COMPLETE. No variants meet new user target.
Source: scripts/research_causal_calibration.py and models/causal_calibration.py.
Artifacts: artifacts/research/swing_v17_causal_20260906/summary.json.
Four-quarter1x net77.3981%,DD18.8565%,feeDD19.3585%,executionDD19.4311%;monthly
geometric1.71505%normal/1.57634%fee/1.35477%execution. Calibration starts with
WAIT warmup,includes inactive calendar time,and only consumes label_end<asof-8d.
This is opened development; no deployment or best-window selection.
v18 joint Transformer training now ACTIVE session61208; see researchrunlog.

User target: geometric5% monthly net growth, equivalent79.5856326022% annually,
global portfolio drawdown<=20%. Months may differ. Prefer deep learning; all
architectures/sizes and supporting models/logic permitted. Measure returns over
continuous calendar time including inactive months, after user fees/funding.

## Invalid earlier calibration claims

The read-only isotonic/ridge probes in the conversation fitted on ALL labels from
earlier signal quarters. In the v15 dataset, each quarter includes signals whose
3–7day outcome matures in the following quarter. At EACH of10 refit boundaries,
28 previous-quarter decision labels had label_end>=refit_time. Latest label_end
was about6days19hours after refit. With the required8day embargo,60rows must be
excluded at each boundary. The advertised isotonic+41.4616%,DD12.0428% and its
1/2/4/all-quarter variants are INVALID as causal backtests. Withdraw the earlier
statement that these used only known outcomes. They are not deployable evidence.

The probes also generated signals separately by quarter before concatenation,
resetting cooldown at boundaries. A corrected run must concatenate calibrated
predictions FIRST, then apply ONE global cooldown/monthly cap/portfolio state.
Do not reuse the rejected v17 patch from conversation without both fixes.

Correct design: at refit_time, select earlier out-of-sample predictions whose
label_end < refit_time -8days; apply any fixed lookback to these eligible rows.
Save selected row indices, timestamps, knots, all hashes and actual latest
calibration label_end. No past calibration data means a declared WAIT warmup or
explicit identity comparator, not an unstated change. Mutation of future labels
must leave all current-quarter calibrated predictions unchanged in a regression
test. Compare corrected identity and calibration on the same global state.

## Verified current state

v15 and its controls are COMPLETE; old active session94744 notes are stale.
Artifacts: artifacts/research/swing_v15_continuous_20260905/continuous/summary.json
and artifacts/research/swing_v15_controls_20260905/summary.json.
33temporal neural checkpoints and4076evaluation decisions,2023-06-01 through
2026-03-23 global maturity cutoff. Last evaluated signal2026-03-15; no positions
or returns should be inferred past the reported data horizon.

v15 mean_minus_std0.5x: net18.4918377%, normalDD17.7537315%, feeDD18.4015696%,
execution net12.6023248%,DD17.5461371%,74normalfills. Across2.80909calendar years,
normal CAGR6.22631%, monthly geometric0.504616%. It FAILS the new5%monthly target.
All other v15 ensemble exposure variants also fail the new target. A prior
passes_provisional_continuous_screen=true is only the OLD positive-net screen.
Candidate-mean0.5x control net16.3008442%,DD12.4416903%; neural seed instability
persists. No winning-seed selection and no live candidate.

v16 direction agreement read-only result: unanimous mean0.5x net13.7083%,
DD15.3667%,fee net10.9148%,DD15.9613%,execution net12.6604%,DD15.5565%,71normal
fills. Unanimous mean_minus_std0.5x net11.0468%,DD22.0350% fails risk. No durable
v16 report was saved because write approval failed. Code/config/tests were saved
earlier;107tests passed then. Do not mistake an absent artifact for a running job.

Next: fix and persist causal calibration audit, verify required label embargo and
global state. Then investigate deeper temporal representations/losses and sample
redundancy with frozen comparisons. Never claim increasing parameters guarantees
market predictability or that target profitability is achievable by construction.
