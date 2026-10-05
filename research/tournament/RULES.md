# Idea tournament - rules for every worker (Claude subagents / OpenCode)

Repo: C:\TRAI_NC\Source_code\Agentic_Alpha_Lab (Windows; use the Bash tool with POSIX syntax; python = `.venv/Scripts/python.exe`, run from
the repo root). Read `AGENTS.md` first. Leader = the main Claude session; you are a worker.

## Hard rules
1. Write ONLY inside your own folder `research/tournament/<your_name>/` (and optionally `tests/test_tournament_<your_name>.py`). Never edit any
   other file, never `git commit`, never modify `../Kronos` (read-only reference; copy what you need into your folder), never touch `.env`,
   credentials, the backend, the bot, or other workers' folders. No exchange orders of any kind.
2. ZERO LEAKAGE: never load or use market data at or after 2025-09-24 (the hidden most recent year). For the test year starting at anchor A,
   a model may train only on rows with `t_exit < A - 7 days` (`harness.folds` gives the masks). Features of a row must be computable at the
   holding bar's open T (data up to the close of minute 0 of the bar, i.e. <= T + 1 min); fill-time features (minute f - 1) are allowed only in
   a variant explicitly labelled `bot_only`. Any normalisation / hyper-parameter / threshold choice must be fitted inside the training rows
   (inner chronological split), never on a test year.
3. Pre-register: before scoring anything write `PLAN.md` in your folder: hypothesis, features, model, at most 3 variants, fixed settings.
   Then score each variant ONCE with `research/tournament/harness.py` (`load`, `folds`, `score`, `save`). Do not iterate variants on test-year
   scores; if you must change something after seeing a score, add it as a disclosed extra variant and say so.
4. Resources: at most ONE heavy process at a time, keep RAM < 2.5 GB (the machine has ~7 GB free shared with others), CPU runs < 60 min each;
   the GTX1650 GPU (4 GB) may be used for inference / small models (import torch BEFORE pandas in GPU scripts).
5. Report honestly: per-year gains, graduation flag, IC, anything that looks suspicious. A negative result is a valid result.

## Inputs
- `research/tournament/harness.py` - rows, folds, scoring, graduation rule (read its docstring).
- `research/diagnostics/phase_agents/fills_U.parquet` - every rung fill (35 coins, 2020-08..2025-09-24) with exact outcomes y0.5/y1.0/y1.5 and
  fill-time state x0..x6 (see `research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py` docstring).
- `research/tournament/data/bar_open.parquet` - bar-open features per fills_U row (same index; see `prep_features.py`).
- `research/tournament/data/hourly.parquet` - hourly OHLC per coin (35 coins, < 2025-09-25).
- Raw 1m data (if needed): `data/raw/btc_intraday_20260924`, `data/raw/majors_intraday_20260924`, alts in `data/raw/alts2020_intraday_20260930`.
- The deployed baseline = the `size_dep` column (v321 R2 size agent: HGB on 7 state features, cross-fitted halves, rule 1.5 / 1.0 / 0.5).

## Deliverable
`research/tournament/<your_name>/`: PLAN.md, your scripts, `score_<variant>.json` per variant (harness.score output), `REPORT.md` (results
table, verdict, caveats). Final message: a short summary with the per-year gains and graduation flags.
