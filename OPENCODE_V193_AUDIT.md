# v193 blind audit - adversarial (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v193_audit/` and `tests/test_v193_audit.py`. Use
relative paths without quoting. Do NOT open v193/ until part A is saved (`replication.json`). Base: your engine_user
replication (`v191_audit/` or `v192_audit/`).
A: pipeline P2 = (A+B)/2 books, book limits 10 bps resting minutes 2..238 (no fallback), book SL/TP m = 4; sleeve ladder
(k 2.5/3/3.5/4 sigma_4h, bids minutes 16..238, maker on trade-through), rung SL at L(1 - 5 sigma_4h) (taker, fill
min(SL, minute open)), TP at L(1 + sigma_4h) (maker), else next 4h open (taker, funding if settlement). Budget: fills in
(minute, rung, asset) order; a fill is taken iff sum over rungs still open at that minute (exit minute > fill minute) of
rn * (5 sigma_4h(asset) + 0.02) plus the new rung's rn * (5 sigma_4h(asset) + 0.02) <= X; rn = s g 0.25/4/1.657.
X = 0.03, 0.05, 0.08. Report per X: monthly_dev4, 5y, last year, yearly nets and 1m DDs, gate DD, rungs, stops/TPs,
liquidation count; selection = best dev4 with DD <= 20 and no losing year in the first four years. Save `replication.json`.
B: compare with `v193/v193_result.json`. Adversarial checks: (1) the budget uses only exits already happened; (2) gap
fills at the stop: count stops filled at an open below the stop and the loss vs the stop; (3) the largest 1m-marked
intrabar drawdown bars (dates, sleeve vs books contribution); (4) the share of the X = 0.08 gain vs X = 0.03 coming
from the top 5% sleeve bars; (5) any leakage. Write COMPARISON.md with a verdict. Do not edit leader files.
