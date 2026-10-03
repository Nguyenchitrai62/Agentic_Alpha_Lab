# M2 MANUAL robustness report (diagnostic; read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Candidate: the MANUAL (book-only, human-followable) pipeline M2 (v317 / v318 reference): books = (2A + 2PT + D)/5 with A = (member_A_O1_orders +
member_Aq_O1_orders)/2, PT = (member_PT_pooledtv + member_PTq_pooledtv)/2, D = (members_v154 level "D" + members_quarterly_D)/2 (files in
artifacts/research/engine_real/, reindexed to the v154 books index, ffill, NaN -> 0); engine_user trade mode, sleeve OFF, v216.GRID with the v216
grid policy (b_abs 0.03, b_rel 0.40, cool 6) BUT the flat-state policy returns {"open": 0.75} (pullback entry limit 0.75 sigma_4h), n_valid 3,
theta 0.05, k_off 0.25 (in-position orders), tighten 1.5, be_k 2, be_off 0.001; v221.KW with m_sl 4, m_tp 8, sleeve False; target 0.25, cap 2,
win_start 5. Base must reproduce dev4 3.011 %/month (first four anchors) and 5y 3.16 / most recent year 3.76 / gate DD 20.57.
Reference leg: G2 manual (books (2A + 2B + D)/5 with B = (member_B_tv + member_Bq_tv)/2, plain open policy k_off 0.25, n_valid 2): dev4 2.502.
Rows for both legs: base; cost_stress (maker 0.0004, taker 0.0007 + 0.0005); HUMAN latency: win_start 15 / 30 / 60 / 120 (the first fill minute
of a new order after the 4h close); missed decisions: every k-th decision bar skipped for new orders (k = 6: the trader misses one 4h decision a
day; implement with the policy returning "wait" when flat and "hold" in a position at those bars); band_lo / band_hi; cool 3 / 12; the stationary
block bootstrap (first four years daily returns, 30-day blocks, 2000 draws, seed 0) and the small-account check at 500 / 1000 / 2000 USDT (Bybit lots).
Report per row dev4 / 5y / most recent year / gate DD / losing years / book win rate. Diagnostic only - nothing is selected on it.
Write only under `research/diagnostics/m2_robustness/` (m2_robustness.py, m2_robustness.json, SUMMARY.md) and `tests/test_m2_robustness.py`;
relative paths without quoting; do not edit engine or leader files. SUMMARY.md: table M2 vs G2-manual per row and a verdict line on how late a
human can be before the edge is lost.
