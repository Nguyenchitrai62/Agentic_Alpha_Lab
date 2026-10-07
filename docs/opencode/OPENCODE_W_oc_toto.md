# OpenCode task oc_toto - a third time-series foundation model as a dip-size tilt (same rule as Kronos K2 / Chronos C2)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_toto/` and `tests/test_oc_toto.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Import torch BEFORE pandas in model scripts.

## Why
Kronos K2 (research/tournament/oc_kronoshidden, oc_k2placebo, oc_k2bybit, audit_k2) is the only new information source with significant timing
on the post-release year. oc_chronos tests a second foundation model with the identical rule. A third model with different pretraining
(pretraining corpus = Datadog observability metrics plus public benchmark sets (check the model card for any crypto series and disclose) - probably the least crypto-contaminated foundation model, so its dev years may count as nearly clean) tells whether the signal is generic "next-bar low risk" that any good forecaster sees, or Kronos-specific.

## Model and environment (do NOT modify .venv)
Datadog Toto (Datadog/Toto-Open-Base-1.0, pip package toto-ts; probabilistic output - take q10 / q50 / q90 from >= 256 samples or from the predictive distribution). Install into a LOCAL target dir: `.venv/Scripts/python.exe -m pip install --target research/tournament/oc_toto/pylib <package>`; if it
pulls a different torch, use --no-deps and add only the missing pure-python deps; `sys.path.insert(0, <pylib>)` in scripts. Weights via
from_pretrained at runtime (HF cache). If the package cannot run on this Windows host after a reasonable effort (e.g. a CUDA kernel that will
not build), stop and report exactly why - do not substitute another model.
Compute: GPU (GTX1650) through scripts/heavy_slot.py; other workers (oc_k2seeds, oc_chronos) also need the GPU - if you wait more than
30 minutes, run on CPU with batched inference instead. Long jobs: start with nohup, log progress to a file under your tmp/, poll the log
(never inspect /proc or other processes; that permission is auto-rejected and ends your session). Make inference resumable
(skip finished (sym, shift) groups).

## Features (fixed; identical definition to oc_chronos)
For each majors coin, each clock shift s = 0..3 (reuse research/tournament/oc_kronoshidden/bars_4h_4shift.parquet), each bar open T in the same
range as research/tournament/oc_kronoshidden/kronos_features_4shift.parquet: context = the last 512 closes of that shift's bars ending at the
bar closing at T (log prices; scale the context as the model expects), forecast horizon 1 bar. f_q10 = (q10 forecast of the next close -
log C0) / sigma (sigma = std of the last 360 4h log returns, as Kronos' sigma); f_q50, f_q90 likewise; risk = -f_q10.
Save toto_features_4shift.parquet (sym, shift, T, f_q10, f_q50, f_q90, sigma). Causality truncation test (features for T unchanged when all
data after T's open is deleted).

## Tilt and evaluation (fixed)
T3: rung size x1.25 / x0.75 on the outer quintiles of risk, per-anchor fit exactly like oc_kronoshidden / oc_chronos (harness training rows
t_exit < A - 7 d, shift-0 feature joined on (sym, T), direction = sign of Spearman(risk, y_dep), edges q20 / q80). Engine on G2 with the
oc_kronoshidden mechanism (copy run_engine.py / tilt_rule.py; reproduce REF 5.41 / 16.91 / 16.82 and K2 first). Rows REF, T3, K2, and
T3K2 = average of the two multipliers (pre-registered ensemble). Report dev4 (with the contamination note from the model card), the
post-release year scored ONCE for all rows (a new information source; no selection on it), 5y, full-path DD, and a timing placebo on the
post-release year exactly like research/tournament/oc_k2placebo (1000 within-year permutations of the T3 multipliers). Also report the
Spearman correlation of risk with Kronos' -low1 (same rows). Vietnamese 3-line verdict.
