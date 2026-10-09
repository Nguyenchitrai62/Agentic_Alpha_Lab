# audit_cboost — REPORT (blind replication of the oc_cascadeboost B7 dip boost on G2)

## What was done

Independent blind implementation of B7 (dip budget x1.5 for 7 days after a cascade bar:
|close-to-close log move| > 4.0 x trailing-90d sigma, closes only, market-wide per shift) on G2
(v421 rule inv k1.0 kd1.7 bear G2.0, per-(holding-bar) mult copied from the frozen spec,
budget unchanged), 4-phase engine via heavy_slot. REF from the engine reproduces v421
R2B1D17BFG2 bit-exact (5.41/16.91/16.82). replication.json saved BEFORE opening any
oc_cascadeboost output; comparison after. PLAN.md pre-registered before any outcome.

## Results (4-phase reset %/mo, yearly DD in brackets; Y4 = LABELLED DIAGNOSTIC, contaminated)

| row | 2021 | 2022 | 2023 | 2024 | dev4 | 2025-09-24..2026-09-23 (diagnostic, ONCE) | 5y | full-path DD |
|---|---|---|---|---|---|---|---|---|
| REF (G2) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601, W 2.588, DD 16.91 | 4.648 (12.90) | 5.410, W 2.588 | 16.82 |
| B7 (blind) | 2.955 (14.67) | 3.264 (17.92) | 8.537 (15.94) | 12.486 (11.01) | 6.738, W 2.955, DD 17.92 | 4.880 (13.81) | 6.364, W 2.955 | 17.75 |

No losing year in dev4 or 5y for either row; DD <= 20 everywhere.
B7 vs REF: dev4 +1.137 pp/mo, worst dev year +0.367 pp/mo, full-path DD +0.93 pp.
B7 Y4 diagnostic 4.880 < 5.0 gate (b) — and contaminated by construction (see below),
so it proves nothing either way.
Triggers: 2112 per-(sym, shift) trigger bars; windowed union tc per shift 264/266/263/255
(exact match); boosted (shift, T) time-bar share 38–55%/yr/shift; engine sized mean 1.319
(dev4, boosted sizing share 63.9%); engine n_miss = 0.
Pooled 5y: B7 book 5033 @ 0.5118 / rung 20939 @ 0.6827 / all 0.6496; Y4: book 1094 @
0.5375 / rung 4583 @ 0.6435 / all 0.6230.

## Comparison to oc_cascadeboost

Trigger counts exact, boost parquet 53877/53877 agree, engine R/DD identical to the digit
in all 5 years, pooled win rates / fills / sized mean / marked-close split / worst episode
identical. Verdict: PASS (see COMPARISON.md; no undisclosed notes).

## What failed / why

Nothing failed in the replication itself. The B7 boost replicates exactly but its Y4
diagnostic (4.88 < 5.0) is contaminated by construction (idea formed after the delay
replica covered all five years), agreeing with oc_cascadeboost's own
NEEDS PROSPECTIVE EVIDENCE. No prospective evidence is created by this audit (the replica
+placebo gate was out of scope and not redone; the engine replication is the clean part).

## Leakage checks

- Feature timing: triggers use ONLY closes with close_time <= tc (bars_4h_4shift closes);
  SIG window excludes the tested bar (no self-inclusion; trailing_sigma slices r[lo:i]);
  boost window strictly after tc (0 < T-tc <= 7d); truncation recompute from bars cut at
  2023-01-01 matches the full-history prefix (test_truncation_causality; their suite has the
  same test, tests/test_oc_cascadeboost.py:114).
- Label windows: none fit anywhere in this study (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N = 7 all frozen
  ex-ante, never scanned; no statistic from any test year feeds any choice.
- Fill timing: engine win_start=5, 1m trade-through only, nothing in the first 5 min,
  stop-first (inherited from the v421/v414 path; asserted in source).
- Costs: gate maker 0.0002 / taker 0.00055, longs 0.0001/8h, shorts 0 (inside engine).
- Coverage: 4h closes from 2020-08-01 give full 540-return windows for all of
  2021-09-24..; no skipped year, nothing imputed; missing trigger history -> mult 1
  (engine n_miss = 0).

## Cap / limit check (dip gross cap 2.0 and every G2 limit still bind under B7)

- `kw["sleeve_gross_cap"] = 2.0` for both REF and B7 (run_engine.py; theirs run_engine.py:180
  identical); risk budget 0.26*1*1.7, kd 1.7 corr-aware sizes, bear-book halving,
  win_start=5, trade-through + stop-first all identical; book leg byte-identical to G2.
- Direct per-fill cap-bind counter is not exposed by the engine (cap cuts inside
  eu.simulate); proxy reported (both studies): boosted share of (shift, T) time-bars
  38–55%, boosted share of engine sizings 63.9%, sized mean 1.319 — the boost binds where
  the sleeve earns, and larger boosted rungs hit the 2.0 cap at least as often as REF by
  construction. Method disclosed; no bind-frequency divergence found.

## Contamination (B7 idea vs all five years)

From oc_cascadeboost PLAN.md (frozen, pre-registered) and this audit's PLAN.md:
oc_cascadedelay's replica covered all five years incl. the post-release year BEFORE the
boost idea was formed (the boost is the deliberate mirror of the delay's decisive loss),
so every post-release-year number is a LABELLED DIAGNOSTIC. Selection is on dev4 only.
Only prospective paper (data that did not exist when the rules were frozen) can confirm B7.

## Vietnamese verdict (3 lines)

B7 tái tạo khớp hoàn toàn (dev4 6,74/WORST 2,96/DD 17,92; 5 năm 6,36), không leakage, mọi giới hạn G2 đều ràng buộc.
Nhưng Y4 chỉ là diagnostic nhiễm (4,88 < 5, ý tưởng hình thành sau khi thấy replica 5 năm) nên không đủ bằng chứng adopt.
Kết luận: PASS cho bản sao, đồng ý NEEDS PROSPECTIVE EVIDENCE — giữ B7 làm ứng viên, chờ log paper prospective.
