# v170 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v170_audit/` and `tests/test_v170_audit.py`.
Do NOT open v170/ until part A is saved (`replication.json`). Base: your audited engine_real replication
(`engine_real_audit/audit_engine.py`) or `engine_real/engine_real.py` (`v154_books`, `context`, `run`, `FULL`).
A: replace only the execution arrays. Per symbol, 1m klines (`v135.load_1m`), holding bar T = t + 4h, minute offsets
inside T: p0 = open at offset 0, lo/hi = min low / max high over offsets 2..W-1, pW = open at offset W (NaN -> p0).
Buy: maker if lo < p0*(1-0.001): fee 0.0002, rel -0.001; else fee 0.0005, rel pW/p0 - 1 + 0.0002. Sell symmetric
(hi > p0*1.001: fee 0.0002, rel +0.001; else fee 0.0005, rel pW/p0 - 1 - 0.0002). No p0 -> taker with rel +/-0.0002.
W in (15, 60, 120); W = 15 must equal engine_real (3.708 / 18.87). Target 0.25, governor on, all realism on.
Report monthly, yearly, full-path DD, maker share of buys/sells over live bars, component sums. Save `replication.json`.
Also check (diagnostic) that the gain is not concentrated in one year and that the taker branch at W=60 charges the
drift pW/p0 - 1 (no free waiting).
B: compare with `v170/v170_result.json` (return > 1pp, DD > 0.5pp must be explained), review `v170/v170_exec_window.py`
for look-ahead (the fill decision uses only minutes after the decision), write COMPARISON.md. Do not edit leader files.
