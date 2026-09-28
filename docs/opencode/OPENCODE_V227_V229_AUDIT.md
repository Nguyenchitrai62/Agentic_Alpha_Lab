# v227 + v228 + v229 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v227_v229_audit/` and `tests/test_v227_v229_audit.py`. Use relative paths
without quoting. Do NOT open v227/v227_result.json, v228/v228_result.json, v229/v229_result.json or their logs until part A is saved
(`replication.json`); read `v227/v227_sleeve_coin_bandit.py`, `v228/v228_trade_offset.py`, `v229/v229_trade_hourly_ladder.py`.
A: with your independent v218 D2 trade mode (engine_user, v216 G2 grid policy, sleeve budget 0.15, rung x1.75, win_start 5):
(v227) Q1 no dip bids on BNB; Q2 coin bandit (bid x clip(ewma_coin/ewma_all, 0.5, 1.5), 180-day half-life over bids of the unfiltered
D2 run that exited before the close of the decision bar, x1 below 50 finished bids); Q3 per (coin, rung), 30 bids minimum.
(v228) entry/adjustment limit offset k_off 0.35 / 0.45 / 0.55 sigma_4h.
(v229) hourly dip ladder on (L1), with size_mult 1.5 (L2), with align (1.5, 0.0) (L3).
Check the causality of the v227 bandit (only bids with exit time < decision time) and of sigma_1h in the hourly ladder (known before
the holding hour). Report dev4, worst first-four monthly, gate DD; robust selection per version; the most recent year only for each
selected row. Save `replication.json`. B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a
"## Verdict" section PASS/FAIL. Do not report the most recent year of non-selected rows. Do not edit leader files.
