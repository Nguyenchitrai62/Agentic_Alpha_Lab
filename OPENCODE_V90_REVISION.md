# v90 revision (leader review 2026-09-25) — still PACKAGE ONLY, DO NOT SUBMIT
(read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_V90_WORKER.md, OPENCODE_VF_COMMON.md)
Edit only `research/parallel/rounds/parallel-20260906-r2/v90/**` and `tests/test_v90_*.py`. Keep the registered data
contract (public USD-M klines + funding only; no spot data) and the standalone single-script design.
Leader findings on `kaggle/train_v90.py` to fix:
1. `win_ok` requires ALL five assets feature-complete, so training starts only ~2021-05 (SOL listing + 200 daily bars)
   and anchor 2021-09-24 has ~566 windows for a 2.9M model. Fix with per-asset availability masking: after
   train-only normalisation set missing feature values to 0 and append one availability channel per asset
   (1 = all 8 features finite at that row, else 0) -> 45 input channels. A window is valid when BTC is
   feature-complete for all 180 rows (other assets may be masked).
2. Labels: compute per asset from OPENS, y7 = log(open[t+43]/open[t+1]) / vol42_t, y1 = log(open[t+7]/open[t+1]) / vol42_t
   (execution fills at the next open). Keep the hidden-year guard on the label END time. Loss is already NaN-masked; a
   training row needs a finite BTC y7 (other assets may be NaN and are masked in the loss).
3. Keep embargo (label realised before anchor-17d), validation split/purge, seeds, early stopping, param band.
4. Re-run tests + CPU smoke; update package_manifest.json (report fit/val/pred window counts per anchor from the
   real bundle for ALL five anchors without training: just the split sizes) and result_manifest.json
   (audit.passed false). Runtime estimate on T4 for 5 anchors x 3 seeds must stay <= 3.5 h; if not, reduce MAX_EPOCHS
   and say so.
