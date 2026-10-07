# OpenCode task oc_staleness - how fast does the book's skill decay with model age? (decides the live retraining schedule)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_staleness/` and `tests/test_oc_staleness.py`.
Print progress at least every 10 minutes. Heavy steps via heavy_slot.

## Why
The walk-forward research retrains every member once per anchor (yearly). The live advisors use models frozen at a cutoff (e.g.
models/frozen/manifest.json, scripts/*_advisor.py 'freeze' dates). Nobody measured how the book's skill decays as a model ages, so there is no
evidence-based retraining schedule for live. (v280 monthly-retrained flow member: dev worse but most recent year better - "fresher helps new
regimes" stayed a hypothesis.)

## Method (fixed)
For each deployed member family (whale-flow A, Coinbase-premium D; find the training code used by research_books_d2 / pipe_setup and the
member scripts) and for each training cut C in {2021-09-17, 2022-09-17, 2023-09-17} (data before C - 7 d):
- predict every 4h bar from C to 2025-09-23 with the model frozen at C (no retraining);
- per calendar quarter after C (age 0-3 m, 3-6 m, ..., up to 24 m), pooled Spearman IC of the prediction vs the realised label (same label
  as the member) and the vectorised diagnostic book P&L (labelled).
Also a "fresh" reference: the yearly-retrained walk-forward predictions for the same quarters. Report IC vs model age (table + PNG), the age at
which IC halves (if it does), and the difference fresh vs stale per quarter. Recommendation (descriptive): retrain monthly / quarterly / yearly
for live. No deployment change here. Vietnamese 3 lines. Data before 2025-09-24 only.
