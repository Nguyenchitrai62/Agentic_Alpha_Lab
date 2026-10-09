# audit_cboost — COMPARISON (Part B, opened ONLY after replication.json was saved)

Blind replication of oc_cascadeboost B7 vs their frozen outputs.
Thresholds (pre-registered): R diff > 0.10 pp, DD diff > 0.5 pp,
trigger counts exact, boosted (shift, T) time-bars exact (100% mult agreement).

## Triggers (no fits in this study; frozen threshold/windows/N/boost)

| shift | ours distinct tc (windowed 2021-09-24..) | theirs (REPORT.md) | match |
|---|---|---|---|
| 0 | 264 | 264 | YES |
| 1 | 266 | 266 | YES |
| 2 | 263 | 263 | YES |
| 3 | 255 | 255 | YES |
Raw per-(sym, shift) trigger rows: ours 2112 (2112 trigger bars, 0 non-finite closes,
2420 NaN-sigma bars never firing, disclosed in tmp/trigger_counts.json).
Windowed union counts agree EXACTLY (the all-history counts 338/341/344/328 differ only
by the pre-window tail back to 2020-08, which never enters any anchor year).

## Boost parquet (53,877 rows, union of shift grids 2020-08-01..2026-09-23)

Our boost_mult_4shift.parquet vs theirs, inner-joined on (shift, T):
boosted_B7 flags 53877/53877 agree, mult_B7 53877/53877 agree.
Boosted time-bar share per (year, shift): ours 38.45–54.66% vs theirs 38–55% (REPORT.md).
Sized mean multiplier (engine, dev4 window): ours 1.319311 (boosted sizing share 63.86%)
vs theirs 1.319 (63.9%) — agrees to their 3dp rounding.

## Engine (4-phase reset %/mo, yearly DD)

| year | REF ours | REF theirs | B7 ours | B7 theirs (dev / last_year) |
|---|---|---|---|---|
| 2021 | 2.588 (10.86) | 2.588 (10.86) | 2.955 (14.67) | 2.955 (14.67) |
| 2022 | 3.282 (16.91) | 3.282 (16.91) | 3.264 (17.92) | 3.264 (17.92) |
| 2023 | 6.045 (15.81) | 6.045 (15.81) | 8.537 (15.94) | 8.537 (15.94) |
| 2024 | 10.677 (8.27) | 10.677 (8.27) | 12.486 (11.01) | 12.486 (11.01) |
| 2025-09-24..2026-09-23 (diagnostic) | 4.648 (12.90) | 4.648 (12.90) | 4.880 (13.81) | 4.88 (13.81) |
dev4: REF 5.601 / B7 6.738 (theirs 5.601 / 6.738). 5y: REF 5.41 / B7 6.364.
Full-path DD: REF 16.82 (marked 16.82 / close 16.05) / B7 17.75 (marked 17.75 / close 16.96)
(theirs identical incl. the marked/close split).
Worst marked episode both rows: peak 2023-04-17 -> trough 2023-06-14 (theirs; ours trough
2023-06-14 21:00, depth 17.75 B7 / 16.82 REF — same 2023 crash leg, deepened ~0.9pp).
Pooled 5y fills: B7 book 5033 @ 0.5118 / rung 20939 @ 0.6827 / all 0.6496 (theirs identical);
Y4: B7 book 1094 @ 0.5375 / rung 4583 @ 0.6435 / all 0.6230 (theirs identical).
Max R diff 0.000 pp, max DD diff 0.00 pp — all far inside thresholds.

## Multiplier vectors

53877/53877 (shift, T) mults agree between our parquet and theirs (see above); engine
lookup is the same causal rule (exact match, fallback latest grid time <= T, missing -> 1;
theirs run_engine.py:89-99, ours run_engine.py boost_at). Engine n_miss = 0 both rows
(all sizings matched exactly, same as their 0 replica misses).

## Look-ahead audit (each with a test in tests/test_audit_cboost.py)

1. Feature timing: PASS. Triggers use closes with close_time <= tc only; SIG[i] = std of
   r[i-540..i-1] with the tested bar EXCLUDED (theirs boost_rule.py:40-43 docstring
   "tested bar EXCLUDED"; ours boost_rule.trailing_sigma slices r[lo:i]); truncation
   recompute from bars cut at 2023-01-01 matches the full-history prefix on real 4h bars
   (test_truncation_causality); their suite has the same test
   (tests/test_oc_cascadeboost.py:114 test_truncation_causality_real_bars).
2. Window timing: PASS. Boosted iff 0 < T-tc <= 7d strict (theirs boosted_mask docstring
   "exists tc with 0 < T - tc <= n_days", searchsorted side="left" - 1, boost_rule.py:85-96;
   ours boosted_mask identical construction); holding-bar key T=H=idx+4h on that shift's
   grid in both engines; boundary unit-tested (test_boost_rule_synthetic: tc-1m/ tc /
   tc+4h / tc+7d / tc+7d+4h -> F/F/T/T/F).
3. Fit windows: PASS (vacuous). No fits anywhere: threshold 4.0, windows 540/120,
   boost 1.5, N=7 frozen ex-ante, never scanned; no statistic from any test year feeds any
   choice; trigger union counts identical to oc_cascadedelay (264/266/263/255 — no refit).
4. Multiplier application point: PASS. `mult * 1.7 * tilt(i, a) * base_size(i, a, r, f)`
   inside sleeve_fill_size (holding-bar decision), budget 0.26*1*1.7 unchanged,
   sleeve_gross_cap 2.0, win_start=5 (theirs run_engine.py:174-183; ours run_engine.py —
   same lines). Dip gross cap 2.0 and every other G2 limit bind in both: the cap parameter
   is set identically and no code path alters it; book leg byte-identical to G2.
   Cap-bind frequency note: neither implementation exposes a per-fill cap-bind counter
   (the cap cuts inside eu.simulate, engine_user.py:699-700); reported proxy — boosted
   share of (shift, T) time-bars 38–55% (both), boosted share of engine sizings 63.9%
   (both), sized mean 1.319 (both): the boost binds exactly where the sleeve earns, and
   larger boosted rungs can only hit the 2.0 cap at least as often as REF by construction.

## Contamination (summary; detail in REPORT.md)

B7's idea was formed AFTER oc_cascadedelay's replica had covered all five years incl. the
post-release year (stated in oc_cascadeboost PLAN.md before any outcome and in this
audit's PLAN.md). Hence every 2025-09-24..2026-09-23 number (B7 Y4 4.88 diagnostic) is a
LABELLED DIAGNOSTIC, not clean evidence — both studies agree. New evidence must come from
controls, unseen years, frictions and prospective paper. This audit did NOT redo the
replica+placebo gate (out of scope: assignment tasks name the 4-phase engine re-run only);
the engine replication is the clean part of this audit (frozen spec, no fits).

## Verdict: PASS

Triggers exact, boost parquet 53877/53877 agree, engine R/DD identical to the digit in all
5 years, pooled win rates / fills / sized mean / worst episode identical, no look-ahead
found, cap and every G2 limit bind in both implementations. No notes beyond the
pre-registered contamination label (which both studies carry) and the disclosed proxy-only
cap-bind reporting.

## Nhận xét tiếng Việt (3 dòng)
B7 tái tạo khớp từng chữ số (dev4 6,74/WORST 2,96/DD 17,92; 5 năm 6,36; Y4 diagnostic 4,88), trigger và parquet khớp 100% nên kết luận PASS.
Mọi giới hạn G2 (cap 2,0, budget, win_start, stop-first) đều ràng buộc ở cả hai bản; không phát hiện leakage.
Y4 chỉ là diagnostic nhiễm (ý tưởng hình thành sau khi thấy replica 5 năm) nên đồng ý NEEDS PROSPECTIVE EVIDENCE của oc_cascadeboost.
