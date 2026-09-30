# v288 + v289 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v288_v289_audit/` and `tests/test_v288_v289_audit.py`. Use relative
paths without quoting. Do NOT open v288/v288_result.json, v289/v289_result.json or their run logs until part A is saved
(`replication.json`).
v288: `v288/v288_path_label_two_members.py` - options + TV member B (v233 builder) trained on the v287 path label (PB / PBq); rebuild
PB / PBq independently (do not reuse member_PB*_path.parquet), check the builder reproduces member_B_tv with the label off, replicate
CB_ref 5.864, P1_ref 5.683 and Q1; decision = v286.dev_select({P1_ref, Q1}); the most recent year must NOT be scored when Q1 is not
adopted. Leakage: label windows (open t+1 .. open t+1+h), training filter / embargo, labels never used as features or in vol models.
v289: `v289/v289_dip12h_account.py` - 12h dip-reversal sub-account next to CB. Write your OWN sub-account simulator from the docstring
(sigma from closed 12h periods only, bids at minute 5 at O exp(-k sigma), k 3 / 3.5 / 4, trade-through fills until minute 704, sizing
3% risk at 3 sigma on the placement equity, touch stop 3 sigma (gap -> minute open, fill minute checked stop-first), TP +1 sigma maker
(not in the fill minute), exit at the next period open, funding 0.0001 per 00/08/16 UTC settlement held, minute marking, liquidation
check), the monthly (1-x, x) combination with CB's engine path (engine_user `path_out`, a default-neutral hook: confirm results are
unchanged with it) and the engine_user.summarize metrics. Replicate CB_ref, the account's dev years, S1, S2, selection (dev_select, DD
filter 2021-2024) and replaces_cb. Explicitly check feature timing (sigma), fill timing (minute >= 5, trade-through, no same-minute TP),
stop / TP ordering, funding and that no data after the anchor feeds a choice.
B: compare with the result JSONs (return > 1pp or DD > 0.5pp = mismatch); COMPARISON.md with a "## Verdict" PASS/FAIL per version.
Do not edit leader files.
