# v180 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v180_audit/` and `tests/test_v180_audit.py`.
Do NOT open v180/ until part A is saved (`replication.json`). Base: the v179 spec in OPENCODE_V178_V179_AUDIT.md
(use the `v178_v179_audit/` replication if it exists, else implement it).
A: candidates = every v178 ladder rung fill (k 2.5/3/3.5/4; fill minute f in 16..238). Features at minute f-1 (all
sigma-scaled as in v173 but one minute earlier): depth = (close(f-1)/open(T) - 1)/sigma; r5 = (close(f-1)/close(f-6) -
1)/sigma; r15 with f-16; vspike = volume(f-5..f-1)/(5*mean volume(0..f-6)); taker15 = taker_buy(f-15..f-1)/volume(f-15..f-1);
rng = (high(f-1)-low(f-1))/close(f-1)/sigma; breadth = other assets with depth <= -2 at f-1; btc_depth at f-1; trend =
open(T)/mean(last 42 4h opens incl. open(T)) - 1; r1d = (open(T)/open(T-24h) - 1)/sigma; last non-zero settled funding at
or before t; k; asset code. y = the rung's normal-cost net return. Per anchor HGB(max_depth=3, lr 0.03, 300 iters,
min_samples_leaf 50, l2 1.0, random_state 0) on candidates with T + 4h < anchor - 1 d and T >= 2020-03-02; a test rung
stays live iff pred > 0. Then the v179 budget loop (normal and stress costs, same gate mask for both). Report IC, kept
counts, monthly, 4h and 1m-marked DD. Save `replication.json`.
B: compare with `v180/v180_result.json`; verify every feature uses data <= minute f-1; write COMPARISON.md.
Do not edit leader files.
