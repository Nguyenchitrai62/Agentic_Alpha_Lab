# oc_tsmomvar PLAN (pre-registered BEFORE any outcome is computed)

No outcome of THIS task has been computed or inspected. Prior `oc_tsmom`
outcomes (BTC/ETH 30d sleeve: combined return higher 5/5, DD not-worse 0/5,
corr +0.17..+0.47) motivate the direction but no V1/V2 statistic below has
been scored. Exactly 2 variants are pre-registered here; then the direction
is closed (no further variants).

## Hypothesis (fixed here)

The 30-day BTC/ETH TSMOM sleeve adds return but is positively correlated
with R2B1D17BF, so the 0.25x overlay worsens yearly DD. Either (V1) spreading
the same rule over all five majors (equal risk per coin) or (V2) slowing to a
90-day lookback with a long-only signal (flat when negative; shorts earn
nothing under the adverse gate funding rule) may decorrelate the sleeve
(corr < 0.15) while staying positive on average. PROMISING only under the
decision rule below.

This is a fixed-rule study: no fitted parameter, no optimisation, one run
per variant.

## Data (fixed here, all in repo)

- Hourly: `research/tournament/ext/hourly_ext.parquet` (35 coins), rows with
  `t < 2026-09-24 00:00 UTC` only. V1 coins: BTCUSDT, ETHUSDT, SOLUSDT,
  BNBUSDT, XRPUSDT. V2 coins: BTCUSDT, ETHUSDT. Daily aggregates from hourly
  bars only (no 1m data). One process, RAM < 1 GB.
- Base: `research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl`
  (shifts s=0..3, strategy R2B1D17BF, {t,eq,eq_min}) via
  `research/diagnostics/r2_decompose5/reset_metric.py` helpers and
  `v388_bot_stop_distance.hourly/mix` exactly (same code path as
  `research/tournament/oc_tsmom/run_tsmom.py`).
- `research/tournament/oc_kpi/results_equity.json` is a published reference
  for cross-check only.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective validation).

## Exact causal definitions (frozen; oc_tsmom code reused exactly otherwise)

Day D = UTC calendar day [D 00:00, D+1 00:00). From hourly bars (t = bar open):

1. `O(sym,D)` = open of the hourly bar with t = D 00:00 UTC (next-day
   execution price). `C(sym,D)` = close of the hourly bar with t = D 00:00 +
   23h (price at D+1 00:00). A day with either bar missing for a coin makes
   that coin flat/zero for any holding day needing it (no forward fill across
   days; within-day missing hourly bars are NOT patched: if O or C is missing
   the day is NaN for that coin).
2. V1 (5-coin 30d, equal risk): `ret30(sym,D) = C(sym,D)/C(sym,D-30) - 1`
   using only closes with dates <= D. `signal(sym,D) = +1` if ret30 > 0, `-1`
   if ret30 < 0, `0` if ret30 == 0 or any of the 31 closes C(D-30)..C(D) is
   NaN. Realised 30d vol: log returns `r_d = ln(C_d/C_{d-1})` for the 30 days
   ending D (d = D-29..D); `vol(sym,D) = std(r, ddof=1) * sqrt(365)`. Fewer
   than 30 non-NaN returns, or NaN/non-positive std -> vol NaN -> position 0.
   `pos(sym,D) = signal(sym,D) * min(0.10/vol(sym,D), 1.0)` (10% annualised
   vol target per coin, cap 1.0x per coin, equal risk; NaN -> 0).
3. V2 (BTC/ETH 90d long-only): `ret90(sym,D) = C(sym,D)/C(sym,D-90) - 1`;
   `signal(sym,D) = +1` if ret90 > 0, else `0` (flat when ret90 <= 0, == 0,
   or any of the 91 closes C(D-90)..C(D) is NaN; never short). Realised 90d
   vol: log returns for the 90 days ending D (d = D-89..D);
   `vol90(sym,D) = std(r, ddof=1) * sqrt(365)`; fewer than 90 non-NaN
   returns, or NaN/non-positive std -> NaN -> position 0.
   `pos(sym,D) = signal(sym,D) * min(0.10/vol90(sym,D), 1.0)` (same 10%
   target and 1.0x cap; long-only so pos >= 0 always).
4. Both variants: `pos(sym,D)` is known at close D and held over day E = D+1
   only, entered at O(sym,E).
5. Holding-day gross return for day E (open-to-open):
   `g(E) = sum_sym pos(sym,E-1) * (O(sym,E+1)/O(sym,E) - 1)`, computed only
   where both opens exist; a coin with a missing open contributes 0 that day
   (counts reported). Single-day TSMOM: no intra-day path.
6. Costs (gate model, both variants): rebalance at each day-E open pays taker
   on traded notional: `cost(E) = 0.00055 * sum_sym |pos(sym,E-1) -
   pos(sym,E-2)|` (weights as fractions of sleeve equity; position before the
   first holding day of each year is 0, so entry is paid). Funding (adverse
   gate rule): `fund(E) = 0.0003 * sum_sym max(pos(sym,E-1), 0)` (0.0001 x 3
   settlements per day on longs; shorts pay/receive nothing, so V2 longs pay
   and V1 shorts are free exactly as in oc_tsmom).
7. Sleeve daily net: `r_s(E) = g(E) - cost(E) - fund(E)`. Per anchor year the
   sleeve equity starts at 1.0 at the open of A_k and compounds:
   `eq(E+1) = eq(E) * (1 + r_s(E))` over holding days E in the year.
8. Anchor years: Y_k = holding days E with E 00:00 in [A_k, A_k+365d),
   A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24} (UTC).
   The last year needs O(2026-09-24) which does not exist in hourly_ext, so
   its final holding day is missing by construction (reported n_days).
9. Base daily returns (same daily grid as oc_tsmom primary Variant B):
   per-shift normalised year segments F (F(a0) = 1.0) from
   v388.hourly(runs[s]["R2B1D17BF"], g0 = 2021-09-24 04:00 UTC,
   g1 = 2026-09-23 12:00 UTC), F = mean_s (e1_s / b_s) with
   b_s = last hourly value <= a0. `r_b(E) = F(E+1 00:00)/F(E 00:00) - 1`.
   Base year equity starts 1.0 and compounds r_b over the same holding days E
   as the sleeve (intersection of available days per year; year 0 drops the
   2021-09-24 partial day where the mix grid starts at 04:00). Base monthly %
   = eq_b_end^(1/12)-1; base max yearly DD = max peak-to-trough on the base
   year path (daily-00:00 grid, no 1m marking; labelled as such).
10. Combined (overlay): `r_c(E) = r_b(E) + 0.25 * r_s(E)` (0.25x sleeve on top
    of base, same weight as oc_tsmom for both variants). Combined equity
    starts 1.0 per year, compounds r_c. Combined monthly % and max yearly DD
    from the combined path. Comparison like-for-like (same days, same grid).
11. Per-year sleeve stats (descriptive): total return (eq_s_end - 1), monthly %
    (eq_s_end^(1/12)-1), Sharpe = mean(r_s)/std(r_s)*sqrt(365) (0.0 if std is
    0/NaN), maxDD on the sleeve year path, n_days, per-coin avg |pos|,
    mean cost/fund bps/day.
12. Correlation (operative): Pearson corr over the year's holding days of
    r_s(E) vs r_b(E) (NaN if either leg is constant; NaN counts as a miss,
    never imputed).
13. LOYO stability (operative, default-rule spirit): for each held-out year h,
    pooled mean sleeve daily return over the other 4 years; PASS_loyo(h):
    pooled mean over the other 4 years has the same (strict) sign as the
    full-5y pooled mean (NaN or zero = FAIL).

## Evaluation (fixed here — exactly 2 variants)

Per variant v in {V1, V2} and year Y_k:

- PASS_pos(v,Y_k): sleeve monthly %(v,Y_k) > 0 (strict).
- PASS_corr(v,Y_k): corr_sleeve_base(v,Y_k) < 0.15 (strict; NaN = FAIL).
- DIV_pass(v,Y_k) = PASS_pos AND PASS_corr.
- DECISION RULE (assignment-specific + header default, operative):
  variant v is PROMISING iff (a) DIV_pass in >= 4 of 5 anchor years, AND
  (b) PASS_loyo in >= 4 of 5 held-out pools. Otherwise NOT PROMISING.
  Combined-vs-base return/DD and Sharpe are DESCRIPTIVE ONLY (reported in the
  per-year table, not part of the gate). NaN counts as a miss.
- Cross-checks (must hold, else the run is invalid): recomputed base annual
  nets within 0.5pp/month of oc_kpi published R (same reset convention);
  monthly compounding reproduces each year's net exactly (residual ~0);
  oc_tsmom sleeve series reproduced exactly when V-code is run in
  BTC/ETH-30d-long/short mode (parity check in the test file).

## Deliverables (fixed here)

research/tournament/oc_tsmomvar/: PLAN.md (this file), run_var.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_tsmomvar.py (causality on 4h-equivalent daily closes, caps,
hand cases, recompute, base sanity, V2-long-only and V1-parity checks).
No commits, no edits outside these two paths. One process, no 1m data,
RAM < 1 GB. Post-hoc changes, if any, are logged in REPORT.md (none expected:
two fixed rules, one run each).

## Amendment log (append-only; original above is frozen)

(none yet)
