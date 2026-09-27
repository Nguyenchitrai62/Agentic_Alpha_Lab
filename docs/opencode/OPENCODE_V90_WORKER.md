# v90 worker (track B): pooled majors sequence model — PACKAGE ONLY, DO NOT SUBMIT
(read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, TRAINING.md, OPENCODE_VF_COMMON.md)
Write ONLY under `research/parallel/rounds/parallel-20260906-r2/v90/` and `tests/test_v90_*.py`.
Never run `kaggle kernels push`/`datasets create`; the leader submits after audit. No credentials in files.
Build a self-contained private-Kaggle package:
- Data: public Binance USD-M 4h klines + funding for BTC/ETH/SOL/BNB/XRP (BTC `data/raw/ma_ribbon_20260924`,
  others `data/raw/xs_universe_20260924`); pack as one parquet/npz with SHA-256 manifest. No project source
  other than a single standalone training script.
- Model: TCN + Transformer hybrid (2-10M params, justify capacity), input 180 x 4h bars x 5 assets of causal
  features (log returns 1/6/42 bars, range, volume z, funding 7d mean, distance to SMA50/SMA200 of the daily
  ribbon as of last closed daily bar), output per-asset 7-day vol-normalized forward return (Huber) and
  1-day (aux). Train-only normalization per anchor.
- Protocol: 5 expanding anchors 2021-09-24..2025-09-24; for each: train on labels realized before anchor-17d,
  early-stop on the last 15% of training time (purged by 7d), 3 seeds, predict every bar in the next year.
  Export predictions (per asset, per bar) and checkpoints; deterministic seeds; runtime estimate on T4 <= 3h.
- Local smoke test: run 1 anchor x 1 seed x 1 epoch on CPU/GTX1650 subset to prove the script runs.
- Write `package_manifest.json` (hashes, param count, runtime estimate, commands) and `result_manifest.json`
  with status "audited", audit.passed false (awaiting leader), live_approved false. Stop when done.
