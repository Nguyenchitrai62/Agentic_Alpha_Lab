# v269 - v272 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v269_v272_audit/` and `tests/test_v269_v272_audit.py`. Use relative paths
without quoting. Do NOT open any v269..v272 result JSON or log until part A is saved (`replication.json`). Read the four scripts and in
`engine_user/engine_user.py` the arguments sleeve_exit_agent (asked at every 5m-block close c before the rule's own exit while the close is
>= 2 sigma below the fill; a True exits at the next minute's open) and sleeve_lock_cut (defaults unchanged).
A: (1) v269: close-stop distance 4 / 6 sigma via m_sleeve_sl on top of v266 B1 (reference 6.13). (2) v270: v267's stress rule on the
4-sigma close stop (budget 0.18 / 0.20); cost constants restored after each stress row. (3) v271: rebuild the checkpoint data set from the
recording run (must reproduce B1), the advantage = exit at open(c+1) (or the next bar open after minute 239) minus the B1 net return of that
rung, the state at c (1m data up to c only - run truncation probes), the per-anchor cross-fitted models on checkpoints whose bar ended
before anchor - 7 days, and the A1 / A2 agents. (4) v272: the same agents with sleeve_lock_cut=True; confirm whether the lock changes
any fill (the leader reports identical results). Report per version: dev4, worst first-four monthly, gate DD, agent counts; robust
selection; most recent year only for each selected row.
Save `replication.json`. B: compare with the four result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict"
PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill / exit timing. Note: all four were run after their
pre-registration commits (293ad42, the v270 commit, a91953b, f52b6eb) but before the registry rotation - confirm the committed scripts equal
the run scripts. Do not edit leader files.
