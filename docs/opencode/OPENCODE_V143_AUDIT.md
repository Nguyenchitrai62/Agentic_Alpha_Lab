# v143 audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v143_audit/` and `tests/test_v143_audit.py`.
This is a code + reproducibility audit (neural network training is not bit-reproducible on GPU):
1. Leakage review of artifacts/kaggle/v143/kernel/train_v143.py: per-target cutoffs (anchor - 78*4h for y6/y18, anchor -
   102*4h for y42) and label masks (t + (h+1)*4h >= cutoff -> masked), training/validation split (validation = last 365
   days before the y6 cutoff, training steps end 102 bars before it), normalisation statistics from training steps only,
   test = [anchor, anchor+365d). Report any row whose label end is on/after its cutoff, any test-period data in the
   normalisation, and any use of future rows in the per-step asset set.
2. Export check: research/parallel/rounds/parallel-20260906-r2/v143/v143_export.py writes the audited v103 panel
   (compare features/targets with your v103_v105 replication on a sample of rows).
3. Reproducibility: retrain anchor 2025-09-24 on CPU with seeds 0-4 (`--data artifacts/kaggle/v143/dataset`, write to your
   audit folder) and compare IC(mean(p6,p18) vs y6) with artifacts/kaggle/v143/local_out/pred_2025-09-24.parquet (report
   the difference; >0.02 needs an explanation).
4. Evaluation: independently recompute research/parallel/rounds/parallel-20260906-r2/v143/v143_evaluate.py numbers from the
   saved predictions (causal scale ratio = std(HGB pred)/std(NN) of the PREVIOUS anchor year, 1 for the first year; blend
   0.5*HGB + 0.5*ratio*NN; NN-only secondary) within the v133 pipeline; compare with v143/v143_result.json.
Write COMPARISON.md with the verdict. Do not edit leader files.
