# OpenCode task oc_ablation - leave-one-layer-out ablation of G2's risk layers in the 4-phase account (what does each layer buy?)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_ablation/` and `tests/test_oc_ablation.py`.
Print progress every 10 minutes. Engine runs via heavy_slot (one phase per process is fine).

## Why
G2 stacks several risk layers that were each adopted on single-clock or older harnesses: the drawdown governor (engine_user `gov`,
per phase), the book vol target / scale, the bear-book filter (longs x0.5 when BTC < 1200-bar mean), the dip gross cap G = 2.0, the
corr-aware dip sizing B1, the close5 dip stop (vs touch), the dip risk budget 0.26 x kd. oc_mvrvmech showed that layers interact (a book change
moved the governor and the dips). Nobody measured, on the honest 4-phase account with the gate DD, what each layer costs and buys today.

## Rows (G2 = v421 RUNS rule inv, k 1.0, kd 1.7, bear True, G 2.0; reproduce 5.41 / 16.91 / 16.82 first; ONE layer removed per row)
- NO_GOV: governor off (g = 1 always).           - NO_BEAR: bear-book filter off (= v411 D17BF without bear? use bear=False).
- NO_CAP: dip gross cap off (G = None).          - NO_B1: corr-aware sizing off (w = 1).
- NO_VT: book vol-target scale fixed at its long-run median (find how the engine scales books; if the vol target cannot be switched off
  cleanly, state it and skip).
- TOUCH: dip close5 stop replaced by the 4-sigma touch stop (8-sigma backstop unchanged).
Find the hooks in research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py and the v421 worker(); if a layer has no hook, say
so (do not edit the engine; patch a copy in your folder if needed and prove the copy reproduces G2 first).
Report per year (dev4 + the most recent year - this is a DIAGNOSTIC ablation, no selection; label the recent year), 4-phase reset R, max yearly
DD, full-path DD (max of close / 1m-marked), worst single-phase DD, and the gap test of research/tournament/oc_gapstress at the worst minute
(-10 % all-coin gap) for G2 vs each row. Table: return bought / DD bought per layer. Vietnamese 3-line verdict: which layers earn their
keep in the 4-phase account and which are pure drag (candidates for a later pre-registered simplification).
