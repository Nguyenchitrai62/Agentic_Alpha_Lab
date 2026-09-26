# v165 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v165_audit/` and `tests/test_v165_audit.py`.
Scope: the EVALUATION of the Kaggle predictions (the training ran on Kaggle; do not retrain, do not use Kaggle/credentials).
Inputs: `artifacts/kaggle/v165/output/v165_out/pred_<anchor>.parquet` (columns t, sym, mlp_plr_p6/p18/p42/p84,
ft_p6/p18/p42/p84) and the audited leader modules (import, do not copy): `v144/v144_deploy_v3.py` (`books_v142`,
`simulate`, and its `v129`, `v125`, `v115.v114.v113` = ext with `ext.v92`, `ext.v94`), `v151/v151_info_ensemble.py`
(`books_with_options`), `v154/v154_ensemble_coinbase.py` (`books_coinbase`). Do NOT open v165/ until part A is saved.
A: 1. Check the prediction files: one row per (t, sym) in each anchor's test year [anchor, anchor + 365 d), no NaN.
2. p_k = mean of the two architectures for k in (p6, p18, p42, p84). Inner-merge on (t, sym) with the v103 panel p103
   (from `books_v142`). Spearman IC per anchor year of mlp_plr/ft p6 vs y6 and p42 vs y.
3. Vol forecast: `v129.vol_predict(p103, f103, ANCHORS, EMBARGO_BARS)` with f103 = p103 columns except y*, t, open, sym,
   bar; replace vol42 by pvol where available.
4. Member E = 0.25 * LO + 0.25 * LS94 + 0.5 * LS103, where LO = `v125.phased(v125.raw_lo(frame(p42)), range(6))`,
   LS94 = phased raw_ls of mean(p18, p42, p84), LS103 = phased raw_ls of mean(p6, p18); each scaled by its book vol
   target (`ext.v92.vol_target_scale` for LO, `ext.v94.vol_target_scale` for both LS books), NaN scale -> 1.
5. Primary books = (A + B + D + E)/4 on the union index (missing -> 0); secondary = E alone. `simulate` rows 0.15
   ungoverned / 0.20 / 0.25 governed. Save `replication.json` (IC table, both blocks: monthly, full-path DD, yearly).
B: compare with `v165/v165_result.json` (IC > 0.01, return > 1pp, DD > 0.5pp must be explained), audit
`v165/v165_evaluate.py`, `v165/v165_export.py` and `v165/kaggle/train_v165.py` for look-ahead (feature timing, target
cutoffs vs anchor minus embargo, early-stopping year inside training, normalisation fit on train only), write
COMPARISON.md with a verdict. Do not edit leader files.
