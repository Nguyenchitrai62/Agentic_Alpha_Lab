# v186 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v186_audit/` and `tests/test_v186_audit.py`. Use
relative paths without quoting. Do NOT open v186/ until part A is saved (`replication.json`). Base: your v183
replication (`v182_v183_audit/`) and v181 alt data handling (`v181_audit/`).
A: v183 exactly, but the sleeve ladder runs on 11 perps in the column order BNB, BTC, ETH, SOL, XRP, DOGE, ADA, LINK,
LTC, AVAX, TRX (alts: 1m from data/raw/alts_intraday_20260926, 4h opens/funding from data/raw/xs_universe_20260924;
within-bar forward-fill of prices as for the majors). Books stay majors-only. One shared open-notional budget 1/6 with
fills ordered by (minute, rung, asset column); vol leg = unbudgeted sleeve over all 11 assets shifted 2 bars; the 1m
mark includes open alt rungs (books marked on the majors only). Normal and stress rows: monthly, 4h DD, 1m DD, worst
bar, taken/TP/cancelled. Save `replication.json`.
B: compare with `v186/v186_result.json` (the leader patches two lines of the v183 source to loop over 11 sleeve
assets - check nothing else changed). Write COMPARISON.md. Do not edit leader files.
