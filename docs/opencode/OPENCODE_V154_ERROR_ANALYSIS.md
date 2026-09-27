# v154 error analysis (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)

Write only under `research/diagnostics/v154_error_analysis/` (new: `analyze.py`, `REPORT.md`, `summary.json`) and
`tests/test_v154_error_analysis.py`. Do not edit any other file. DESCRIPTIVE diagnostics on already-seen OOS years:
the report must say that any idea it suggests needs a pre-registered test (and prospective confirmation).

Rebuild v154 exactly by importing the leader modules (do not copy logic):
`research/parallel/rounds/parallel-20260906-r2/v144/v144_deploy_v3.py` (`books_v142`, `simulate` engine pieces),
`v151/v151_info_ensemble.py` (`books_with_options`), `v154/v154_ensemble_coinbase.py` (`books_coinbase`); books =
(A + B + D)/3. Recompute the v144 sequential engine for target 0.25 with the 20% governor (copy the loop from
`v144_deploy_v3.simulate`, extended to also return per-bar arrays: portfolio scale s, governor g, the final weights w per
asset, per-asset gross return contribution w_i * r_i, cost per asset, funding, carry). Check that its monthly return and
full-path DD equal v154's primary row (3.515%/month, 19.15%) before analysing.

Decompose the 2021-09-24..2026-09-23 live span (4h bars) and report gross contribution (sum of w_i * r_i), costs and
net where applicable:
1. by asset; 2. by member (A/B/D: use each member's share of the final weight, w_member = 0.8*s*g*member_book/3);
3. by book inside members (v92 LO / v94 LS / v103 LS, using `books_v142` internals: rebuild b_lo, b94, b103 per member);
4. long vs short legs; 5. by BTC daily ribbon state (rib of the BTC row at t: +1/0/-1); 6. by BTC realised-vol tercile
(vol42 of BTC at t, terciles over the live span); 7. by anchor year; 8. the 5 largest drawdown episodes (peak -> trough
dates, depth) with their contribution split by asset, member, book and long/short; 9. hit rate and payoff ratio of
daily net returns per year.
Write REPORT.md (tables + 5-10 plain observations, no recommendations presented as validated) and summary.json.
Tests: the reconstruction equals v154's primary monthly/DD within 0.01; decomposition sums equal totals.
Runtime: this rebuilds three member books (tens of minutes) - fine.
