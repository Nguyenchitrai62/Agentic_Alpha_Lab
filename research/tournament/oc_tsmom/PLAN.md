# oc_tsmom PLAN (pre-registered BEFORE any outcome is computed)

Idea #36 (NEW): a daily time-series-momentum (TSMOM) sleeve as a diversifier.
Written before any outcome statistic is computed. No outcomes have been
inspected; the rule below is fixed here.

## Hypothesis (fixed here)

The deployed BOT earns from mean reversion (dip ladder) plus a 4h book. A
slow trend sleeve (30-day time-series momentum on BTC+ETH, vol-targeted) could
be uncorrelated and diversify drawdowns. Pre-registered direction: overlaying
0.25x of the sleeve on R2B1D17BF raises the per-year return without worsening
the per-year max drawdown. PROMISING only under the decision rule below.

This is a fixed-rule sleeve: no fitted parameter, no optimisation, one run.

## Data (fixed here, all in repo)

- Hourly: `research/tournament/ext/hourly_ext.parquet` (35 coins), rows with
  `t < 2026-09-24 00:00 UTC` only. Coins used: BTCUSDT, ETHUSDT only. Daily
  aggregates are built from hourly bars (no 1m data). One process, RAM < 1 GB.
- Base: `research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl`
  (shifts s=0..3, strategy R2B1D17BF, {t,eq,eq_min}) via
  `research/diagnostics/r2_decompose5/reset_metric.py` helpers and
  `v388_bot_stop_distance.hourly/mix` exactly (same as oc_kpi/run_kpi.py).
  `research/tournament/oc_kpi/results_equity.json` is the published reference
  for cross-check only (not recomputed from).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective validation).

## Exact causal definitions (frozen)

Day D = UTC calendar day [D 00:00, D+1 00:00). From hourly bars (t = bar open):

1. `O(sym,D)` = open of the hourly bar with t = D 00:00 UTC (next-day execution
   price). `C(sym,D)` = close of the hourly bar with t = D 00:00 + 23h (the
   day's last hourly close, i.e. price at D+1 00:00). A day with either bar
   missing for a coin contributes that coin as flat/zero for any holding day
   that needs it (no forward fill across days; within-day missing hourly bars
   are NOT patched: if O or C is missing the day is NaN for that coin).
2. 30-day return at close D: `ret30(sym,D) = C(sym,D)/C(sym,D-30) - 1`, using
   only closes with dates <= D. `signal(sym,D) = +1` if ret30 > 0, `-1` if
   ret30 < 0, `0` if ret30 == 0 or any of the 31 closes C(D-30)..C(D) is NaN.
3. Realised 30-day vol at close D: log returns `r_d = ln(C_d/C_{d-1})` for the
   30 days ending D (d = D-29..D); `vol(sym,D) = std(r, ddof=1) * sqrt(365)`
   (365-day annualisation, crypto trades every day). If fewer than 30 returns
   are non-NaN, or std is NaN/non-positive, vol is NaN -> position 0.
4. Position for the next day: `raw = 0.10 / vol(sym,D)` (10% annualised vol
   target); `pos(sym,D) = signal(sym,D) * min(raw, 1.0)` (cap 1.0x per coin;
   NaN vol or NaN signal -> 0). pos(sym,D) is known at close D and is held
   over day E = D+1 only, entered at O(sym,E).
5. Holding-day gross return for day E (open-to-open):
   `g(E) = sum_sym pos(sym,E-1) * (O(sym,E+1)/O(sym,E) - 1)`, computed only
   where both opens exist; a coin with a missing open contributes 0 to g(E)
   that day (documented; counts reported). Single-day TSMOM: no intra-day path.
6. Costs (gate model): rebalance at each day-E open pays taker on the traded
   notional: `cost(E) = 0.00055 * sum_sym |pos(sym,E-1) - pos(sym,E-2)|`
   (weights as fractions of sleeve equity; position before the first holding
   day of each year is 0, so entry is paid). Funding (adverse gate rule):
   `fund(E) = 0.0003 * sum_sym max(pos(sym,E-1), 0)` (0.0001 x 3 settlements
   per day on longs; shorts pay/receive nothing).
7. Sleeve daily net return: `r_s(E) = g(E) - cost(E) - fund(E)`. Per anchor
   year the sleeve equity starts at 1.0 at the open of A_k and compounds:
   `eq(E+1) = eq(E) * (1 + r_s(E))` over holding days E in the year.
8. Anchor years: Y_k = holding days E with E 00:00 in [A_k, A_k+365d),
   A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24} (UTC).
   The last year needs O(2026-09-24) which does not exist in hourly_ext, so
   its final holding day is missing by construction (reported n_days).
9. Base daily returns: continuous 4-phase mix `e,mn = v388.mix(runs,
   "R2B1D17BF", g1)` with g1 = 2026-09-23 12:00 UTC (same as oc_kpi). Base
   daily return for calendar day E: `r_b(E) = e(E+1 00:00)/e(E 00:00) - 1`
   sampled on the hourly grid (e starts 2021-09-24 04:00, so day 2021-09-24
   runs 04:00 -> next 00:00; stated in results). Base year equity starts 1.0
   and compounds r_b over the same holding days E as the sleeve (intersection
   of available days). Base monthly % = eq_b_end^(1/12)-1; base max yearly DD
   = max peak-to-trough on the base year path (4h-close grid, no 1m marking;
   labelled as such; oc_kpi 1m-marked DDs are the published reference).
10. Combined (overlay): `r_c(E) = r_b(E) + 0.25 * r_s(E)` (0.25x sleeve on top
    of base). Combined equity starts 1.0 per year, compounds r_c. Combined
    monthly % = eq_c_end^(1/12)-1; combined max yearly DD from the combined
    path. Comparison is like-for-like (same days, same grid).
11. Per-year sleeve stats (descriptive): total return (eq_s_end - 1), monthly %
    (eq_s_end^(1/12)-1), Sharpe = mean(r_s)/std(r_s)*sqrt(365) (0.0 if std is
    0/NaN), maxDD on the sleeve year path, n_days, per-coin avg |pos|.
12. Correlation (descriptive): Pearson corr over the year's holding days of
    r_s(E) vs r_b(E) (NaN if either leg is constant; reported).
13. LOYO stability (descriptive, satisfies the default-rule spirit): for each
    held-out year h, pooled excess = mean over the other 4 years of
    (r_c - r_b) daily, equivalently 0.25*mean(r_s); and pooled sign of mean
    sleeve daily return. PASS_loyo(h): pooled mean sleeve return over the
    other 4 years has the same sign as the full-5y pooled mean (strict; NaN =
    FAIL). Reported only.

## Evaluation (fixed here — one variant only)

- PASS_ret(Y_k): combined monthly %(Y_k) > base monthly %(Y_k) (strict).
- PASS_dd(Y_k): combined max yearly DD(Y_k) <= base max yearly DD(Y_k)
  (strictly not worse; exact <=, no tolerance; both in %).
- DECISION RULE (assignment-specific, operative): PROMISING iff
  (a) PASS_ret in >= 4 of 5 anchor years, AND
  (b) PASS_dd in >= 4 of 5 anchor years. Otherwise NOT PROMISING.
  NaN counts as a miss, never imputed. Sleeve standalone sign, Sharpe,
  correlation and LOYO are DESCRIPTIVE ONLY (not part of the gate).
- Cross-checks (must hold, else the run is invalid): recomputed base annual
  net per year within 0.5pp/month of oc_kpi published R ordering sanity
  (exact equality NOT required: different daily grid vs hourly reset_metric);
  monthly compounding reproduces each year's net exactly (residual ~0).

## Causality / correctness tests (tests/test_oc_tsmom.py)

- test_signal_uses_only_past_closes: synthetic closes; shifting C(D) changes
  only signals at D..D+30, never earlier; position for E depends only on
  closes <= E-1 and executes at O(E).
- test_data_cap: no hourly row with t >= 2026-09-24 00:00 UTC is loaded;
  holding days never reach beyond available opens.
- test_hand_cases: (i) straight-up 30d trend -> signal +1, vol-scaled weight
  matches 0.10/vol capped at 1.0; (ii) straight-down -> -1; (iii) zero vol
  (flat closes) -> position 0; (iv) one-day open-to-open gain with no
  rebalance and no funding (short) gives exact r_s; (v) long day deducts
  exactly 0.0003*pos funding; (vi) full rebalance 0->w pays 0.00055*w.
- test_recompute: results.json per-year sleeve/combined/base series recomputed
  independently from daily closes/opens equal the stored values (abs tol);
  PASS_ret/PASS_dd counts and the promising flag match the AND rule.
- test_base_sanity: recomputed base year nets compound from the stored daily
  returns (residual ~0); v411 pkl keys are exactly {t,eq,eq_min}.

## Deliverables

research/tournament/oc_tsmom/: PLAN.md (this file), run_tsmom.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_tsmom.py. No commits, no edits outside these two paths. One
process, no 1m data, RAM < 1 GB. Post-hoc changes, if any, are logged in
REPORT.md (none expected: single fixed rule, one run).

## Amendment log (append-only; original above is frozen)

- 2026-10-06 (after the first scoring run, before REPORT.md): base definition
  corrected. The pre-registered §9 sampled the CONTINUOUS 4-phase mix
  (v388.mix) daily. Validation against oc_kpi showed gaps up to 0.83pp/month
  (2023: 5.499 vs published 4.669): the four phase sub-accounts diverge, so
  ratio-of-means (continuous mix) != mean-of-ratios (reset_metric year
  convention = what a user starting that year gets). The assignment points at
  reset_metric.py, so the PRIMARY base is now Variant B: per-shift normalised
  year segments F (F(a0) = 1.0), daily returns from F — reproducing oc_kpi R to
  0.024pp/month. Variant A (pre-registered continuous mix) is kept in
  results.json as a sensitivity. Sleeve definition, costs, gate and day sets
  are unchanged. The decision is identical under both bases (ret 5/5, dd 0/5),
  so the correction does not shop the verdict; it aligns the counterfactual
  with the published year metric.
