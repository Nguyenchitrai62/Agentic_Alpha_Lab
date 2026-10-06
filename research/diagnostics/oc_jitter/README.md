# oc_jitter — joint +-10% jitter robustness around R2B1D17BFG2

Analyzer for Kaggle job `jitter_g2_joint` (spec:
`artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json`): BASE R2B1D17BFG2
(deployed v421: rule inv, k 1.0, kd 1.7, bear true, G 2.0, book_hook bear) + 12
seeded joint uniform draws within +-10% of kd/G/k (seed 20261006, kd,G,k order
per row J01..J12). Harness: `artifacts/kaggle_stage/engine_kernel/engine_harness.py`.
One-at-a-time plateau: `research/diagnostics/oc_plateau2/REPORT.md`.

## Run

Leader downloads the running Kaggle job (account 2, kernel
`trainguyenchi/oc-engine-4p`) into `artifacts/kaggle/engine_jitter_v2/`, then:

```
.venv/Scripts/python.exe research/diagnostics/oc_jitter/analyze_jitter.py
```

The script finds `results.json` recursively under that dir and writes
`REPORT.md` + `results.json` next to itself. Overrides:
`--results <path> --job <job.json> --outdir <dir>`.

## Checks

1. GATE: BASE must reproduce v421 (5y 5.41 / worst 2.588 / max yearly DD 16.91 /
   full-path DD 16.82 within rounding, tol 0.011), else exit 2 with GATE FAIL.
2. Per-row table: kd/G/k, 5y %/mo, worst year, max yearly DD, full-path DD, losing years.
3. Distribution over the 12 jitters: min/median/max of 5y, maxDD, fullDD; shares
   with 5y >= 5.0, DD < 20 (both DDs), no losing year. Verdict ROBUST iff all 12
   pass all three, else failing rows + which parameter moved most (largest
   relative |jitter-base|/base over kd/G/k).

## Test

```
.venv/Scripts/python.exe -m pytest tests/test_oc_jitter.py -q
```

Uses a synthetic `results.json` (no Kaggle, no commits). Diagnostic only;
deployment stays R2B1D17BFG2 regardless.
