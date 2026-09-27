# User hypotheses: minimum bracket distance and inverse signals

Read-only diagnostic simulation completed2026-09-06; no model, trading policy,
cloud job or live orders changed. Preserve as research evidence, not deployment.
Uses v19 full local-audited predictions/signals. Dataset hashes reverified and
require_tcn_audit passed before simulation. Source:
`artifacts/research/v19_local_portfolio/continuous/{mean,mean_minus_std}/signals.parquet`.
Dataset`data/processed/swing_regime_research_v4`, modelplan`configs/swing_v19_tcn_fusion.json`.
Evaluation2023-06-01–2026-03-23,2.809092589years; previously opened development.

## Are brackets too close for fees?

Across135alerts perbranch, planned SL/TP1 distance from limitentry:
- Mean: minimum1.99920%, median3.93375%, maximum14.01643%.
- Mean-minus-std: minimum1.99863%, same median/max.
- TP2: minimum approximately4%, median7.86750%, maximum28.03286%.
- Neither branch has any planned SL orTP1 below1%. Actualfilledtrades minimum
  SL/TP1 distances are2.50877% formean and1.99863% formean-minus-std.
- Minimum0.5% or1% widening rule would change ZERO current orders.

Mean1x currentportfolio: grossPnL−34.21096, fees2.72056,funding4.05262,
netPnL−40.98415 oninitialcapital100. Costs worsen performance but are not the
primary source of loss. This decomposition is on the existing compounded
portfolio, not a separately simulated zero-cost portfolio.

## Inverse hypothesis: tested precise implementation

Keep the135alert clocks and original selected bracket/holding choices; flip
candidate side (LONG<->SHORT). Recalculate prices from the same decisionclose,
atr5,atr4 via`data.swing.prices`, so buy-limitbelowclose becomes sell-limitabove
close and viceversa. Preserve absolute SL/TP distances and maxholding3/7days.
Assertions checked opposite direction, mirrored entryarounddecisionclose and
identical riskdistance/alerttimestamps. Model expected-return/fill scores are
not reused or described as confidence for these opposite-side orders.

Re-simulate fills, positions, partialTP1, SL-first ordering, fees andlongfunding;
do NOT negate original PnL. This changes which alerts fill and how trades exit.
Basecapital100 compounded,1x only,entryexpiry12x5mbars,TP1half,4alerts/monthcap.
Normalfees.02%eachfill,longfunding.01%/8h,shortfunding0.
Fee-stress.055%eachfill. Executionstress5bpsentry/targetpenetration,
5bpsexitslippage,.055%marketexitfee,no limitpriceimprovement.

| Original ensemble being inverted | Scenario | Net total | Monthly geometric | DD | Fills |
|---|---|---:|---:|---:|---:|
|Mean|Normal|+17.1702%|+0.47118%|27.6493%|87|
|Mean|Fee stress|+10.2403%|+0.28964%|27.9070%|87|
|Mean|Execution stress|−19.6581%|−0.64721%|37.6139%|83|
|Mean−std|Normal|−28.1449%|−0.97571%|48.8722%|94|
|Mean−std|Fee stress|−32.7668%|−1.17083%|50.2198%|94|
|Mean−std|Execution stress|−39.6012%|−1.48461%|54.4947%|84|

Meaninverse normal: gross24.53155,fees3.53681,funding3.82452,winrate51.7241%,
profitfactor1.09355. Mean−stdinverse normal:gross−21.27236,fees3.28316,
funding3.58941,winrate42.5532%,profitfactor.84175.

Conclusion: one inverse policy improves normal-cost PnL but is execution-sensitive
and breaches20%DD; the other stillloses. Neither meets5%monthly/20%DD target.
This is hindsight-proposed developmentdiagnosis, not independent validation.
No claim that inverse strategies can never work; this specific transformation
has not demonstrated a robust useful edge. Avoid leverage escalation.
Wider brackets are not the current missing safeguard; existingTP2 can already
be large relative to3–7dayholding. Reconsidering bracket/horizon fit would be a
separate registered experiment, not a retroactive change to v19 results.
