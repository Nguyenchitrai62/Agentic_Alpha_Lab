# OpenCode task oc_chronos - a SECOND time-series foundation model (Amazon Chronos-Bolt) as a dip-size tilt, like Kronos K2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_chronos/` and `tests/test_oc_chronos.py`.
Print progress every 10 minutes. GPU (GTX1650) via heavy_slot; one GPU job at a time; import torch BEFORE pandas.

## Why
research/tournament/oc_kronoshidden + oc_k2placebo + oc_k2bybit: the Kronos-small forecast of the next 4h bar's low (K2 tilt) is the only new
information source with significant timing on the post-release year (placebo pct 97-99), robust on Bybit prices. If a DIFFERENT foundation
model with different pretraining also carries the signal, the evidence becomes much stronger (and a 2-model ensemble may help).
Chronos-Bolt (amazon/chronos-bolt-small, released 2024-11, trained mostly on public non-crypto corpora + synthetic data) -> less
contamination risk for 2021-2024 than Kronos (still disclose), and the post-release year is clean.

## Environment (do NOT modify .venv)
Install the needed packages into a LOCAL target dir: `.venv/Scripts/python.exe -m pip install --target research/tournament/oc_chronos/pylib
chronos-forecasting` (if it pulls an incompatible torch, use --no-deps and install only the missing pure-python deps: transformers (a version
compatible with huggingface_hub 0.33), tokenizers, regex, etc.), then `sys.path.insert(0, <pylib>)` in your scripts. Never pip-install into
.venv. Weights via from_pretrained at runtime (HF cache).

## Features (fixed)
For each majors coin, each clock shift s = 0..3 (4h bars opening at s, s+4, ... UTC; reuse research/tournament/oc_kronoshidden/
bars_4h_4shift.parquet), each bar open T (2020-10 .. 2026-09-23 like the Kronos file): context = the last 512 closes of that shift's bars ending at
the bar closing at T (log prices), forecast horizon 1 bar, quantiles from Chronos-Bolt (it outputs quantile levels 0.1..0.9).
ch_q10 = (q10 forecast of the next close - log C0) / sigma (sigma = std of the last 360 4h log returns, as Kronos' sigma); ch_q50 likewise; risk = -ch_q10.
Save chronos_features_4shift.parquet (sym, shift, T, ch_q10, ch_q50, ch_q90, sigma). Check causality (truncation test).

## Tilt (fixed; identical to K2 except the feature) and evaluation
C2: rung size x1.25 / x0.75 on the outer quintiles of risk, per-anchor fit on harness training rows (research/tournament/harness.py,
t_exit < A - 7 d, shift-0 feature joined on (sym, T)): direction = sign of Spearman(risk, y_dep), edges q20 / q80; same as
oc_kronoshidden (read its PLAN.md / tilt_rule.py and copy the engine mechanism of research/parallel/rounds/parallel-20260906-r2/v414).
Engine on G2 (reproduce 5.41 / 16.91 / 16.82 and oc_kronoshidden's K2 numbers first): rows REF, C2, K2 (from the Kronos file), and
C2K2 = average of the two multipliers (pre-registered ensemble). Dev4 (labelled possibly contaminated) + the post-release year scored once for
all four rows (this is a new information source; report it as such) + a timing placebo on the post-release year exactly like
research/tournament/oc_k2placebo (1000 within-year permutations of the C2 multipliers, normalised). Vietnamese 3-line verdict.
