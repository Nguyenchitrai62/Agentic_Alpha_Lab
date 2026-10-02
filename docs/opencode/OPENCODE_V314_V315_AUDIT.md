# v314 + v315 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Both versions are MANUAL (book-only, sleeve OFF) grids on engine_user trade mode with the audited G2 book rules: books = (2 A + 2 B + 1 D) / 5 where
A = (member_A_O1_orders + member_Aq_O1_orders)/2, B = (member_B_tv + member_Bq_tv)/2, D = (members_v154 level "D" + members_quarterly_D)/2 (files in
artifacts/research/engine_real/, reindexed to the v154 books index, NaN -> 0); trade = v216.GRID with the v216 grid policy (b_abs 0.03, b_rel 0.40,
cool-down 6 bars), theta 0.05, k_off 0.25, tighten 1.5, be_k 2.0, be_off 0.001, n_valid 2; engine kwargs = v221.KW with m_sl 4.0, m_tp 8.0,
sleeve False, win_start 5, governor default (0.20, 0.10). Reference: target 0.25, cap 2 -> dev4 (first four anchors, geometric) 2.502 %/month.
v314: grid target {0.25, 0.30, 0.37, 0.44, 0.52} x cap {2, 3, 4, 5}. v315: target 0.25, cap 2; the flat-state policy returns {"open": k_entry}
(engine: the opening limit offset = k_entry x sigma_4h) with k_entry {0.25, 0.75, 1.25, 2.0} x n_valid {2, 3, 6} (n_valid in the trade dict).
Metrics per anchor year y (yearly segments of engine_user summarize): net, monthly, 1m DD; book trades = position episodes from the events (v213
trade_stats net definition: maker 0.0002 / taker 0.00055 fees, funding excluded) assigned to y by ENTRY time; win = net > 0.
Fitness (both versions, = v310.fitness): per year set Ys: R = geometric monthly over Ys, W = worst year monthly, DD = max yearly 1m DD, WIN = book
win rate; g1 = (R/5, 20/DD, WIN/0.55, min(1, 1 + W/2)) capped 1; if min(g1) < 1: F = 0.7 min + 0.3 mean, else F = 1 + 0.25 min(g2) + 0.75 mean(g2)
with g2 = (R/8, 15/DD, WIN/0.60) capped 1.2; for |Ys| > 1 the training fitness is 0.5 x worst single-year F + 0.5 x pooled F. Flat choice =
mean F over the grid point and its +-1-step grid neighbours. Folds: k = 2 (train years 0..1, test year 2) and k = 3; final on years 0..3, then
the most recent year (index 4) for the final choice.
Write only under `research/parallel/rounds/parallel-20260906-r2/v314_v315_audit/` and `tests/test_v314_v315_audit.py`; relative paths without
quoting; do NOT open v314/ or v315/ result JSONs or logs before `replication.json` is saved.
A: implement independently (you may call engine_user.simulate and reuse the member files; write your own fitness / flat choice / trade
extraction), replicate every grid row (dev4, per-year net / DD / book trades / wins), the fold choices, F values and the final choice and its
most-recent-year metrics; check feature timing (members are cached walk-forward books), fit windows (no fitting here), fill timing (minute-5
rule, limit trade-through, stop-first ties) and that no most-recent-year number enters any choice. Save replication.json FIRST.
B: compare with v314_result.json / v315_result.json (any monthly > 0.01 pp, DD > 0.05 pp or F > 0.001 = mismatch, report all); COMPARISON.md
with "## Verdict" PASS/FAIL. Do not edit leader files.
