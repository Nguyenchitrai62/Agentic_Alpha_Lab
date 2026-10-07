# OpenCode task oc_k2parity - does the LIVE Kronos K2 feed (scripts/kronos_shadow.py) reproduce the RESEARCH K2 features?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2parity/` and `tests/test_oc_k2parity.py`.
Print progress every 10 minutes. Light GPU (a few hundred inferences) via heavy_slot; import torch before pandas. Do NOT edit
scripts/kronos_shadow.py or bot/ (report a suspected bug with a minimal reproduction instead). Do NOT touch the running shadow loop or its
output file artifacts/research/kronos_shadow/kronos_features_live.parquet (read-only); write your own outputs under your folder (`--out`).

## Why
The paper runner paper_d17bfg2k2 sizes dip rungs with k2_mult from the live shadow file. The K2 evidence (oc_kronoshidden, oc_k2placebo,
oc_k2bybit, audit_k2) was computed by research/tournament/oc_kronoshidden/run_inference_4shift.py from 1m-derived 4h bars. If the live path
(1h klines fetched from the exchange, its own shift-bar builder, context selection, sigma, seed_for) differs, the paper log tests a
different signal than the one researched.

## Tasks
1. Read both code paths and list every difference (data source, bar construction per shift, context length / last bar used, sigma window,
   normalisation, sampling S / T / top_p, seed, model revision, the frozen q20 / q80 / direction used by assign_k2 vs fits.json anchor 2025).
2. Run the live path in backfill mode (`--now` / `--backfill-hours`, own `--out` under your folder) for 2026-09-01 .. 2026-09-23 (all 5
   majors, all 4 shifts that the live path produces) - this overlaps the research file
   research/tournament/oc_kronoshidden/kronos_features_4shift.parquet. Join on (sym, shift, T).
3. Report: bar OHLC equality of the context (max rel diff), sigma diff, low1 correlation and max abs diff, share of rows whose k2_mult
   differs, and - to separate code differences from Monte-Carlo noise - re-run the RESEARCH path on the same rows with two different seeds
   and report its own k2_mult disagreement rate. Verdict: live == research up to MC noise (PASS) or a concrete difference (FAIL + fix
   proposal for the leader). Vietnamese 3-line verdict.
