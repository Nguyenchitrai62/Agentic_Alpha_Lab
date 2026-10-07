# Common header for the 2026-10-07 wave (read together with your own OPENCODE_W_<tag>.md)

- Read AGENTS.md and docs/opencode/OPENCODE_VF_COMMON.md first. GIT IS READ-ONLY FOR WORKERS: never stash / reset / checkout / restore /
  clean / rm / commit / switch / rebase / merge. Scratch files only under `<your folder>/tmp/`, never the system temp folder; do not inspect /proc.
- Write ONLY inside the folder and test file named in your assignment (plus the data folder if your assignment names one). Never edit any
  other file: not the registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/ (except the one doc your assignment names), bot/,
  backend/, scripts/, other workers' folders, ../Kronos. Never touch artifacts/bot/* state or running processes, .env or credentials.
  No exchange orders of any kind, no authenticated endpoints, no Kaggle uploads.
- HEAVY steps (any 4-phase engine run, any process expected > 0.4 GB RAM, any GPU use) run through the shared semaphore:
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag <your tag> --min-free-gb 2.0 -- <cmd...>`; never `--leader`. Waiting is normal.
  The GPU (GTX1650, 4 GB) is for one job at a time: import torch BEFORE pandas in GPU scripts.
- Selection protocol (AGENTS.md, user-approved): write `PLAN.md` with the pre-registered variants (ONLY those named in your assignment) and
  every fixed setting BEFORE computing any outcome. Compare and choose ONLY on the four dev years (anchors 2021-09-24, 2022-09-24,
  2023-09-24, 2024-09-24; each year = [A, A + 365 d)). Robust criterion: DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/month,
  then the highest dev4 WORST-year monthly return, ties -> higher mean. Score the most recent year 2025-09-24 .. 2026-09-23 ONCE, only for the
  chosen variant (and the reference), and label it. If you change anything after seeing an outcome, keep the original row and add the change
  as a disclosed extra row.
- ZERO LEAKAGE: features at a decision time use only data available at that time (a 4h bar's values are known at its close; a fill at minute f
  may use data up to minute f - 1 only in rows labelled `bot_only`). Fits / thresholds / quantiles use only rows that end before the anchor
  minus a 7-day embargo. State in REPORT.md how you checked feature timing, label windows, fit windows and fill timing.
- Gate costs: maker 0.0002, taker 0.00055 (stops and market exits are taker), longs pay 0.0001 per 8h funding settlement held (00/08/16 UTC),
  shorts receive nothing. Limit orders fill only on a 1m trade-through (strictly through the price); no fill in the first 5 minutes after a 4h
  close. If a stop and a take-profit are both touched in the same 1m bar, assume the stop first.
- Deployed reference = G2 (`R2B1D17BFG2` in research/parallel/rounds/parallel-20260906-r2/v421: 5.41 %/month 4-phase reset metric, max yearly
  DD 16.91, full-path DD 16.82). Its 4-phase hourly equity is stored in `v421/v421_runs.pkl`; research/tournament/oc_carrycompound/
  analyze_carrycompound.py shows how to load it and how to overlay a sleeve on TOTAL equity (A(t) = A(t-1) (1 + r_bot(t)) + dSleeve(t)) and how
  to compute the reset metric (research/diagnostics/r2_decompose5/reset_metric.py) and full-path DD. Reproduce the G2 baseline numbers exactly
  before any overlay; if you cannot, stop and report.
- Report honestly: per-year tables (%/month geometric, DD, trades, win rate), what failed and why. A negative result is a valid result.
  Finish REPORT.md with a 3-line Vietnamese verdict: adopt / reject / needs prospective evidence. Put a short `results.json` next to it.
  Write a pytest file with at least: one causality / truncation test and one hand-checked synthetic case; run it with
  `.venv/Scripts/python.exe -m pytest <file> -q`. Stop when done.
