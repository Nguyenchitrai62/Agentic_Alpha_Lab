# OpenCode task oc_kronosbase - does the LARGER Kronos (Kronos-base, 102M) carry the K2 signal more strongly? (Kaggle GPU inference)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_kronosbase/` and `tests/test_oc_kronosbase.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome.

## Why
K2 (research/tournament/oc_kronoshidden, oc_k2placebo, oc_k2bybit, audit_k2) uses Kronos-small zero-shot. If the bigger sibling with the
identical rule gives a stronger / more stable risk ranking, that is the cheapest upgrade of the only new signal; if not, K2 is not just
"more model = more edge". Kronos-base on the local GTX1650 would take too long (S = 64 paths, 4 clocks, 6 years), so run inference on Kaggle.

## Compute (Kaggle, account 1 only)
Use the Kaggle CLI with its DEFAULT authentication (account nguynchtrai, already configured). Never read, print, copy or pass any token
(.env, ~/.kaggle) and never use the second account. First `kaggle kernels list --mine` and check running kernels / GPU quota; one kernel
at a time. Upload research/tournament/oc_kronoshidden/bars_4h_4shift.parquet as a PRIVATE dataset (own dataset-metadata.json under your
folder); the kernel bundle carries the needed Kronos model source copied from research/tournament/oc_kronoshidden (kronos_fast.py / model/)
- never modify ../Kronos. Weights NeoQuasar/Kronos-base + NeoQuasar/Kronos-Tokenizer-base from the HF hub inside the kernel. Keep the kernel
private; download only the output parquet. Make the kernel resumable / chunked (e.g. one kernel run per clock shift) if the 12 h limit is
tight. If Kaggle is unavailable or out of GPU quota, stop and report - do not run the full job locally.

## Features (fixed; identical to oc_kronoshidden except the model)
Settings exactly as research/tournament/oc_kronoshidden/PLAN.md and run_inference_4shift.py: context 400 x 4h bars, pred_len 6, S = 64,
T = 1.0, top_p = 0.9, top_k = 0, torch seed 1234, fp32, per-window z-normalisation + clip 5, same bars, same T range, same feature
definitions (low1 etc.). First verify on Kaggle that Kronos-SMALL with the same code reproduces 50 rows of
kronos_features_4shift.parquet (low1 max abs diff; GPU nondeterminism must be small) before running Kronos-base.
Save kronosbase_features_4shift.parquet.

## Tilt and evaluation (fixed)
KB2: K2's rule with Kronos-base low1 (per-anchor fits exactly as oc_kronoshidden: harness rows t_exit < A - 7 d, shift-0 feature joined on
(sym, T), direction sign of Spearman, q20 / q80). Engine on G2 with oc_kronoshidden's run_engine.py / tilt_rule.py (reproduce REF and K2
first). Rows REF, K2, KB2, KBK2 = average of the K2 and KB2 multipliers (pre-registered). Report dev4 (labelled: inside Kronos pretraining =
upper bound), the post-release year scored ONCE (a different model; no selection on it - the prospective paper log stays the decider), 5y,
full-path DD, timing placebo pct on the post-release year exactly like research/tournament/oc_k2placebo, and the Spearman correlation of
the two low1 series. Vietnamese 3-line verdict.
