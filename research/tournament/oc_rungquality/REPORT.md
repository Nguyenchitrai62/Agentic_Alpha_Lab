# oc_rungquality — REPORT (2026-10-08; PLAN frozen before any outcome)

Dip-rung quality filter (IDEAS5 #9, rank 9): skip rungs whose trailing-90d pre-anchor
per-(coin, depth) stop-given-fill rate > p80 (F1); F2 = F1 + fill rate < p20 (chronic
non-fillers). Depths/stops/TP unchanged, skip-only veto (never re-peg). Existing engine
fill ledgers + 1m-derived replica only — no new data pull.

STATUS: DONE. Stats built from 21,389 FIFO-paired oc_kpi fills (matches oc_ladderfill to the
fill); base reproduction gate passes exactly (n = 22312, sum5y = 7.718304); BOTH variants FAIL
the replica + placebo gate -> NO 4-phase engine run (negative result, valid per IDEAS5 —
the oc_crashgate path). No post-hoc change (one pre-report bugfix, logged below, did not
touch any frozen rule or threshold).

## Trailing quality stats (frozen rule; T in [A-97d, A-7d), exit < A-7d, min_n = 10)

| anchor | stats fills | p80 stop-rate | p20 fill-rate | F1 cells | F2 cells |
|---|---|---|---|---|---|
| 2021-09-24 | 0 (pre-registered empty: window predates the ledger) | NaN | 0.0 | 0 | 0 |
| 2022-09-24 | 349 | 0.0000 | 0.00222 | 0 | 5 (all five 5.0-depth cells) |
| 2023-09-24 | 872 | 0.1667 | 0.00685 | 4 (BTC4.0/5.0, ETH5.0, XRP5.0) | 6 (+SOL5.0, BNB5.0) |
| 2024-09-24 | 1455 | 0.1611 | 0.01204 | 5 (ETH5.0, BNB3.5/4.0/5.0, XRP5.0) | 7 (+BTC5.0, SOL5.0) |
| 2025-09-24 | 848 | 0.0000 | 0.00444 | 2 (BNB2.5/3.0) | 7 (+BTC5.0, ETH5.0, SOL4.0/5.0, XRP5.0) |

F2 is dominated by deep-rung vetoes (the 5.0 depth fills rarely); F1 vetoes high-stop cells
(mostly deep rungs, once BNB shallow cells in 2025 when p80 = 0).

## Replica + placebo gate (reused D0+B1 ledger; 4-phase-mean w*y10 units)

| year x variant | n | skipped | base | filt | timing pct | block pct |
|---|---|---|---|---|---|---|
| 2021 F1 / F2 | 4171 | 0 / 0 | 0.911273 | 0.911273 / 0.911273 | 100.0 / 100.0 | 100.0 / 100.0 |
| 2022 F1 / F2 | 4059 | 0 / 305 | 0.832599 | 0.832599 / 0.728231 | 100.0 / 71.9 | 100.0 / 71.1 |
| 2023 F1 / F2 | 5352 | 352 / 473 | 2.099814 | 1.963508 / 1.925448 | 45.9 / 40.2 | 40.9 / 21.6 |
| 2024 F1 / F2 | 3958 | 350 / 401 | 3.197390 | 2.979661 / 2.921633 | 10.3 / 18.1 | 49.7 / 67.2 |
| 2025 F1 / F2 | 4772 | 702 / 959 | 0.677229 | 0.565342 / 0.532728 | 57.1 / 54.7 | 0.9 / 10.1 |

- dSum5y: F1 -0.466 (FAIL vs +0.273); F2 -0.699 (FAIL). Sum-half: F1 2/5 (FAIL; only the
  two no-skip ties 2021-2022 pass), F2 1/5 (FAIL; only the 2021 tie). Gate (both legs): FAIL.
- Placebo reading guide (frozen definition): pct = 100*(1+#{perm_sum >= actual})/1001 on raw
  sums at fixed skipped-fill count — LOW pct means the selected skip beats random skipping of
  the same size; HIGH pct means worse than random. No year reaches the >= 95 worse-than-random
  flag; the single standout is F1-2025-block pct 0.9 (the BNB-shallow veto beats random-block
  skipping, p ~ 0.009) — yet it still loses vs keeping the rungs (0.565 < 0.677), so it is a
  "less-bad removal", not an edge. 2021-2022 F1 rows are degenerate (k = 0, pct 100.0 by
  construction, disclosed).
- Engine stage NOT run per the binding gate rule (same negative-outcome path as oc_crashgate).
  Consequently there is no dev4 robust pick, no 5y %/month, no full-path DD and no engine win
  rates to report; the G2 reference was not re-run (nothing passed to compare against it).

## Why it failed (diagnostic, same ledger)

Skipped fills are WINNERS in every active year (fill-level y10 > 0 share / mean):

| year | F1 skipped win / mean bps | F2 skipped win / mean bps |
|---|---|---|
| 2022 | n/a (no skip) | 0.813 / +28.0 (305 deep fills) |
| 2023 | 0.798 / +19.8 | 0.803 / +17.9 |
| 2024 | 0.771 / +39.6 | 0.796 / +49.1 |
| 2025 | 0.651 / +7.2 | 0.673 / +2.3 |

Stops are rare overall (~4% of fills), so even the worst p80 stop-rate cells are net winners
(+7..+40 bps) — the veto amputates profitable rungs. Chronic non-fillers (deep 5.0 rungs) win
67-81% when they do fill. Same mechanism as the oc_rungcap failure (removed 4th/5th rungs won
72-83%): in this dip family, adverse selection is not concentrated enough in any (coin, depth)
cell for a skip to pay for its exposure loss (round-trip 4-8 bps << the +7..+49 bps removed).

## Leakage checklist

- Feature timing: T = fill_t minus shift-grid fill minute (ladderfill-exact copy); trailing
  windows use only fills with T AND exit_t < anchor - 7d; truncation-tested in
  tests/test_oc_rungquality.py (post-cutoff exit excluded; later data cannot move kept stats).
- Label windows: no labels fit anywhere (replica exits are mechanical stop/TP/timeout legs).
- Fit windows: p80/p20 quantiles computed inside each anchor's own trailing W(A) only —
  strictly pre-anchor; 2021 empty window yields an empty skip set (pre-registered, never imputed);
  no test-year statistic feeds any choice; thresholds (p80/p20) frozen, never scanned.
- Fill timing: replica live 16..238 strict trade-through + stop-first inherited from both ledgers;
  the veto is a pre-placement skip (bot-executable static per-year blocklist, no intrabar read).
- Coverage: 2021 no-skip disclosed; 2022-2025 full 90d windows; stats ledger (oc_kpi, n = 21389
  paired) vs eval ledger (k2placebo D0+B1, n = 22312) mismatch disclosed in PLAN (same D0 family;
  stats noise is conservative — it can only dilute a real cell effect, and the failure is a
  same-ledger winner-removal, not a mismatch artefact).
- Gate costs: inside replica outcomes (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h,
  shorts 0). No engine run, so no engine-cost row.

## What failed and why

Both pre-registered variants fail at the screen with margin (F1 dSum -0.466 / 2-of-5; F2 dSum
-0.699 / 1-of-5; need +0.273 and 4-of-5): the (coin, depth) cells flagged by trailing stop
rates or chronic non-filling are still solid winners when traded, so skipping them removes
+0.11..+0.28 yearly sum units per active year for no tail benefit measurable at this stage.
No timing/block placebo supports the selection (best non-degenerate row is a "less-bad removal"
in one year). Direction closed: rung QUALITY as trailing (coin, depth) stop/fill rates carries
no dip edge in this family — consistent with oc_rungcap (quantity cap) and oc_rungspace
(spacing) failing for the same winner-removal reason.

## Post-hoc log

- 2026-10-08 (before REPORT, after the first gate run): fixed a loop-variable shadowing bug in
  compute_replica_gate.py (the block-placebo setup reused `k`, overwriting the stored
  k_skipped with n_y - 1; all sums/percentiles used the true count and are unchanged —
  verified identical dSum/percentiles on rerun). Added a regression test
  (test_run_variant_k_matches_skipped_and_sums). No frozen rule, threshold, window, gate or
  dataset changed; the original (buggy-k) numbers are superseded only in the k_skipped column.

## Repro

`research/tournament/oc_rungquality/{PLAN.md,quality.py,build_stats.py,compute_replica_gate.py,
results.json,tmp/quality_stats.json,tmp/replica_rungquality.json,tmp/pairs_all.parquet}` +
`tests/test_oc_rungquality.py` (10 tests pass). CPU-only, peak RAM < 1 GB, no heavy_slot needed
(no 1m reads; stored ledgers only). results.json = replica gate output (no engine rows exist).

## Vietnamese verdict

F1 rớt ngay từ screen (dSum -0,466, chỉ 2/5 năm do 2 năm hòa không-skip; cần +0,273 và 4/5),
F2 còn tệ hơn (-0,699, 1/5) vì các rung sâu ít-khớp bị loại đều là lệnh thắng 67-81%.
Kết luận: REJECT cả hai biến thể rung-quality ở dạng đăng ký trước, không chạy engine,
đóng hướng này (cùng nguyên nhân winner-removal như oc_rungcap/oc_rungspace).
