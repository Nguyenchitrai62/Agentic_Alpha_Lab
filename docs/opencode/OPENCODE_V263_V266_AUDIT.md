# v263 - v266 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v263_v266_audit/` and `tests/test_v263_v266_audit.py`. Use relative paths
without quoting. Do NOT open any v263..v266 result JSON or log until part A is saved (`replication.json`). Read the four scripts and in
`engine_user/engine_user.py` the arguments sleeve_breaker, sleeve_stop_mode ("touch" / "close1" / "close5"), sleeve_backstop,
sleeve_budget_sl (all default = unchanged results).
v266 B1 is the new best candidate (5m-close dip stops + an 8-sigma native backstop): audit it with extra care.
A: (1) confirm every default reproduces v247 B18 (dev4 5.777, DD 19.65). (2) Re-implement the sleeve exit rules independently for a sample of
rung fills (at least 200 fills over the dev years, including the 2024-08-05 bar): touch stop; close1 / close5 trigger (1m close / close of
the 5-minute block ending at minutes 4, 9, ... of the bar, at or below lv * (1 - 5 sigma)); exit at the NEXT minute's open (next bar open
after minute 239); backstop touch at lv * (1 - 8 sigma) filled at min(level, open) and winning over a same-minute close trigger or TP; TP
touch 1 sigma, stop-first on ties; timeout. Confirm no exit uses a price before it is observable (the close trigger of minute k cannot exit
before minute k + 1). (3) sleeve_breaker: the mark uses closes up to minute f - 1 only. (4) v263: labels from the reference run, classifier
fit windows (positions closed before anchor - 7 days), state at the decision-bar close. (5) Run every variant; robust selection per
version; most recent year only for each selected row.
Save `replication.json`. B: compare with the four result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with a "## Verdict"
PASS/FAIL, explicitly checking feature timing, label windows, fit windows and fill / exit timing. Note: v264-v266 were run after their
pre-registration commits (3a4df5d, 370dc59 + engine fix 'mins' name clash found at the first variant, eb99e67) but before the registry
rotation (tracks held by audits) - confirm the committed scripts equal the run scripts. Do not edit leader files.
