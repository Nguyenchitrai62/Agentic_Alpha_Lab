# OpenCode task oc_k2seeds - is the Kronos K2 clean-year gain robust to the model's SAMPLING seed? (program rule: >= 5 seeds)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2seeds/` and `tests/test_oc_k2seeds.py`.
Print progress every 10 minutes. GPU via heavy_slot (one GPU job at a time; another worker may hold the GPU - wait); import torch before pandas.

## Why
Kronos features are Monte-Carlo estimates (S = 64 sampled paths, torch seed 1234; research/tournament/oc_kronoshidden PLAN / run_inference_4shift.py).
Program rule (memory, v259): every stochastic learner must report >= 5 seeds before any claim. K2 (post-release +0.15 %/month, timing
placebo pct 97-99, audited) was run with ONE seed.

## Method (fixed)
Re-run the Kronos-small inference with IDENTICAL settings except the torch seed in {1, 2, 3, 4} (plus the original 1234), for all four clock
shifts, 5 majors, over 2024-09-01 .. 2026-09-23 only (the post-release year plus enough history for the 2025 anchor's fit is NOT needed -
the 2025 fit uses training rows before 2025-09-17: for those rows use shift-0 features from the SAME seed computed over 2020-10 .. 2025-09; if
that is too slow, compute the 2025 fit from the original seed-1234 features and say so - the multipliers on the clean year then differ only
through the clean-year features). Then for each seed: K2 multipliers on the post-release year (anchor-2025 fit), engine row on G2 for the
post-release year only (4-phase, as oc_kronoshidden), and the vectorised placebo percentile of research/tournament/oc_k2placebo.
Report per seed: clean-year R / DD vs REF 4.648 / 12.90, normalised dip-replica gain, placebo percentile; the share of (coin, bar) cells whose
K2 multiplier changes between seeds. Verdict (Vietnamese 3 lines): is the gain stable across seeds (all 5 > REF)?
