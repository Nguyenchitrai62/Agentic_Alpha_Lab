# v267 + v268 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v267_v268_audit/` and `tests/test_v267_v268_audit.py`. Use relative paths
without quoting. Do NOT open v267/v267_result.json, v268/v268_result.json or their logs until part A is saved (`replication.json`); read
`v267/v267_stress_robust_select.py`, `v268/v268_book_close_stops.py` and in `engine_user/engine_user.py` the new arguments book_stop_mode
("touch" / "close5" / "close60") and book_backstop (defaults unchanged).
A1 (v267): rerun the 4 candidates x 3 scenarios (base; cost stress maker 0.0004 / taker 0.0007 + 0.0005 via the module constants, restored
afterwards; latency win_start 15); dev DD = max per-year dd_1m_pct of the first four years; apply the pre-registered rule (pool: dev DD <= 20
in all three scenarios and no losing dev year; pick the highest worst dev year; empty pool -> R0_O1).
A2 (v268): re-implement the book close-stop exit for a sample of >= 100 dev book positions (close of the 5m / 60m block beyond the stop,
fill at the next minute's open or the next bar open after minute 239; native backstop 2 sigma_d beyond the stop, touch, fill at
min(level, open), wins on ties); confirm the defaults reproduce v247 B18 (5.777) and that v266 B1 reproduces 6.13; run K1 / K2; robust
selection; most recent year only for the selected row.
Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking fill / exit
timing and that no stop exit uses a price before it is observable. Do not edit leader files.
