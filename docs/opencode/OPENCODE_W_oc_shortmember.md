# OpenCode task oc_shortmember - retrain the whale-flow book member on a SHORT-horizon label (where the book's skill actually lives)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_shortmember/` and `tests/test_oc_shortmember.py`.
Print progress every 10 minutes. CPU training (HGB) + 4-phase engine via heavy_slot.

## Why
research/tournament/oc_bookichorizon: the deployed book's IC is stable and positive at h = 1..18 four-hour bars (4/4 dev years for every
member) but unstable at the 7-day label h = 42 that the A / Aq (whale-flow) members are TRAINED on (oc_staleness: A = v92-base + TV(17) +
order-level flow(6), label y42; D = Coinbase premium with labels y6 / y18). Training A directly on a short label might sharpen the signal.
(Old evidence: v94 long/short horizon ensemble helped; v103 1d/3d flow model +0.5 pp; v147 12 h horizon neutral - different engine.)

## Rows (pre-registered; only these)
Rebuild member A exactly as deployed (find the builder used for the cache member_A_O1_orders - research_books_d2 / pipe_setup /
scripts/forward_v205.py; reproduce its cached predictions on the standard grid first: Spearman >= 0.999 per anchor, else stop and report),
then retrain with the label changed (vol-normalised forward return over h bars, same normalisation as y42):
- AS6: label h = 6 (1 day).    - AS18: label h = 18 (3 days).
Replace A AND Aq (the quarterly refit uses the same label change) in the blend research_books_d2 (all other members unchanged), bear
filter, G2 engine (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0; reproduce 5.41 / 16.91 / 16.82 first). Selection on dev4 with the robust
criterion vs G2; the most recent year scored once for the chosen row + G2. Also report the member IC at h = 1, 6, 18, 42 per year for A vs
AS6 / AS18. Vietnamese 3 lines.
