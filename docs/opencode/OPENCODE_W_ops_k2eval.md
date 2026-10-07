# OpenCode task ops_k2eval - offline evaluator: Kronos K2 dip tilt applied to the paper runners' REAL dip fills (prospective evidence tool)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (leader-assigned implementation): you may CREATE
`scripts/k2_paper_eval.py`, `tests/test_k2_paper_eval.py` and `docs/opencode/K2EVAL_20261007.md`. artifacts/* are READ-ONLY; never start /
stop processes.

## Context
research/tournament/oc_kronoshidden: the K2 tilt (dip rung size x1.25 when risk = -low1 is in the favourable outer quintile, x0.75 in the
unfavourable one; anchor-2025 fit in research/tournament/oc_kronoshidden/fits.json) beat G2 by +0.15 %/month on the post-release year; not
deployed. scripts/kronos_shadow.py logs prospective Kronos features + k2_mult per (sym, shift, T) to
artifacts/research/kronos_shadow/kronos_features_live.parquet (column mode: prospective / late / backfill).

## Implement scripts/k2_paper_eval.py
- Read a paper runner's dip fills and exits (default artifacts/bot/paper_d17bfg2; option --runner) from actions.jsonl / exchange.json:
  per dip piece: symbol, phase (from the piece id, see bot/mirror.py), holding bar T, fill price / qty, exit price / time / reason, realised
  P&L incl. fees (as paper_report.py computes it - reuse its parsing).
- Join each piece to the kronos row with the same (sym, shift = phase, T); only PROSPECTIVE rows count (late / backfill reported apart).
- Counterfactual: K2 P&L = k2_mult x piece P&L; normalise by the mean k2_mult of the joined pieces (equal average exposure); report
  sum(P&L), sum(K2 P&L normalised), difference, n pieces joined / unjoined, per coin and per week; exclude the correction window in
  artifacts/research/advisor_shadow/paper_corrections.json.
- --json output; tests with synthetic actions + kronos rows (join on phase/shift, exposure normalisation, exclusion window, prospective
  filter). Run it once now (sample will be tiny) and paste the output into the doc with the honest note that weeks of data are needed.
