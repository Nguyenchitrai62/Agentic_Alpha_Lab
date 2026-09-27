# v212 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v212_audit/` and `tests/test_v212_audit.py`. Use relative
paths without quoting. Do NOT open v212/ until part A is saved (`replication.json`). Base: your independent v210 trade-mode
replication (T2).
A: extend your T2 re-implementation with ONE in-position limit order slot per asset, decided at each decision bar while in a
position (after the tighten rule; an existing slot order expires when i >= issue + 2 bars; it is cancelled when the position
closes). With w = |quantity| * open(minute 0) (weight at the bar start), off = max(0.001, 0.25 sigma_4h):
- ADD (S1, S3): signal on the position's side, position in profit at the open ((open - avg entry) * side > 0), fewer than 1 add
  so far, |target| >= 1.5 w, and (|target| - w) * equity * 10k >= min notional -> buy (long) limit at open * (1 - side*off) for
  weight |target| - w. On fill: new average entry; SL = avg * (1 - side*4 sigma_d_entry) unless the stop is already at break-even
  (then keep the tighter of the two); TP = avg * (1 + side*8 sigma_d_entry).
- REDUCE (S2, S3; checked only if no ADD is issued): fewer than 1 reduce so far and (|target| <= 0.5 w or the signal (|target| >=
  0.05) is not on the position's side) -> sell (long) limit at open * (1 + side*off) for 50% of the current quantity.
- a slot order issued at bar i may fill only from minute 5 of bar i (minute 0 on later bars) on a strict trade-through (maker);
  in the minute scan the order is: stop, take-profit, slot fill, partial, break-even trigger (next minutes re-scanned after a slot
  fill or a break-even move).
Report ref_v205, v210_T2, S1..S3 (dev4, worst first-four monthly, gate DD, fills, stops, tps, adds, reduces, scale orders);
robust selection over S1..S3; most recent year only for the selected row. Check causality. Save `replication.json`.
B: compare with `v212/v212_result.json` (return > 0.01pp/month, DD > 0.05pp, counts exact or explain). COMPARISON.md with
PASS/FAIL. Do not report the most recent year of non-selected rows. Do not edit leader files.
