# v281 + v282 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v281_v282_audit/` and `tests/test_v281_v282_audit.py`. Use relative paths
without quoting. Do NOT open v281/v282 result JSONs or logs until part A is saved (`replication.json`).
A1 (v281): read `v281/v281_microstructure_member.py` and `research/diagnostics/data_leaderboard/data_leaderboard_dev.py`. Check feature
timing for every group (TV, perp / spot / OKX / Bybit order flow, premium, open interest / long-short merged at bar close - 5 minutes,
1m intrabar), the 7-day label and the training rows (label end before anchor - 7 days), the scale k (training rows only), and the
blends with the C4 books (reference 6.026). Report member IC per dev year, dev4 / worst / gate DD of U1 / U2, robust selection, most
recent year only for the selected row.
A2 (v282): read `v282/v282_full_rl_trader.py`. Check the simulator (limit fill on trade-through from minute 5 for every position change,
market stops with gap fill, maker targets, stop first, exits from the bar after a fill, adverse funding), the state timing, the per-anchor
training windows, the 2021 fallback to the G2 rule, the evaluation (book PnL from the simulator + the C4 engine sleeve attribution;
first-year equity base fixed in 3538431 before any agent result) and the decision rule on the median seed. PPO may differ across
hardware: re-train at least two seeds per variant and report whether the qualitative verdict (all seeds far below the reference) holds.
Save `replication.json`. B: compare with both result JSONs. COMPARISON.md with a "## Verdict" PASS/FAIL, explicitly checking feature
timing, label windows, fit windows and fill timing. Do not edit leader files.
