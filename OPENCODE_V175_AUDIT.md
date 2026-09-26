# v175 blind audit - adversarial (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v175_audit/` and `tests/test_v175_audit.py`.
Do NOT open v175/ until part A is saved (`replication.json`). Base: your v171/v172 audit replications.
A: holding bar T = t + 4h, sigma(t) as v171 (360 4h open-to-open returns, min 120, grid from 2020-02-01).
Limit bid L = open(T) * (1 - k sigma(t)), live in minute offsets 16..238 of T; filled at L if any of those minutes has
1m low < L (strict). r = open(T+4h) * (1 - s_out) / L - 1 - 0.0002 - 0.0005 - funding settled at T+4h, s_out =
max(0.0002, 0.25*(high-low)/open) of minute 0 of T+4h. k per anchor from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe of
0.25 * sum_sym r (window [2020-02-01 + 30 d, anchor - 1 d]). Rows: books (engine_real, v170 60-minute execution,
target 0.25, governor) + g * sleeve at size 0.25 and 0.15; sleeve alone per anchor (k, net, DD, events).
Save `replication.json`.
B: compare with `v175/v175_result.json`. Adversarial checks with numbers: (1) look-ahead; (2) how often the price is
ALREADY below L at the first live minute (open of minute 16 < L): such a bid would be marketable (taker at a lower
price) - report count and the effect of re-pricing those fills at the minute-16 open with taker fee 0.0005 instead;
(3) fills where the minute's low is below L by more than 2% (gaps) - count and whether the model's fill price L is
conservative there; (4) share of the result from the top 5% events per year; (5) exit at T+4h+15 min sensitivity;
(6) 2021 drawdown: dates and whether the sleeve and the books lose together. Write COMPARISON.md with a verdict.
Do not edit leader files.
