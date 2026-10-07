# oc_xsrev PLAN (pre-registered BEFORE any outcome is computed)

Idea #40 (NEW): a daily cross-sectional reversal (XSREV) sleeve on the five
majors as a market-neutral diversifier. Written before any outcome statistic
is computed. No outcomes have been inspected; the rule below is fixed here.

## Hypothesis (fixed here)

The deployed BOT (book + dip ladder, R2B1D17BF) earns from mean reversion of
single-coin dips plus a 4h book. A cross-sectional 1-day reversal sleeve
(long yesterday's losers, short yesterday's winners, dollar-neutral) could be
market-neutral and diversify drawdowns. Pre-registered direction: overlaying
0.25x of the sleeve on R2B1D17BF does not worsen the per-year max drawdown
while the sleeve itself earns a positive mean and stays uncorrelated with the
base. PROMISING only under the decision rule below.

This is a fixed-rule sleeve: no fitted parameter, no optimisation, one run.

## Data (fixed here, all in repo)

- Hourly: `research/tournament/ext/hourly_ext.parquet` (35 coins), rows with
  `t < 2026-09-24 00:00 UTC` only. Coins used: BTCUSDT, ETHUSDT, SOLUSDT,
  BNBUSDT, XRPUSDT only. Daily aggregates are built from hourly bars (no 1m
  data). One process, RAM < 1 GB.
- Base: `research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl`
  (shifts s=0..3, strategy R2B1D17BF, {t,eq,eq_min}) via
  `research/diagnostics/r2_decompose5/reset_metric.py`-convention helpers and
  `v388_bot_stop_distance.hourly/mix` exactly (same as oc_tsmom
  `sample_reset_base`, Variant B primary). g1 = 2026-09-23 12:00 UTC
  (Y1 + 12h, same as oc_tsmom).
  `research/tournament/oc_kpi/results_equity.json` is the published reference
  for cross-check only (not recomputed from).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective validation).

## Exact causal definitions (frozen)

Day D = UTC calendar day [D 00:00, D+1 00:00). From hourly bars (t = bar open):

1. `O(sym,D)` = open of the hourly bar with t = D 00:00 UTC (next-day execution
   price). `C(sym,D)` = close of the hourly bar with t = D 00:00 + 23h (the
   day's last hourly close, i.e. price at D+1 00:00). A day with either bar
   missing for a coin is NaN for that coin that day (no forward fill across
   days; within-day missing hourly bars are NOT patched).
2. 1-day return at close D: `ret1(sym,D) = C(sym,D)/C(sym,D-1) - 1`, using only
   closes with dates <= D. NaN if either close is NaN or C(D-1) == 0.
3. Ranking at close D (known at close D, no lookahead): rank the five majors
   by ret1(sym,D) ascending (worst = smallest). Coins with NaN ret1 are never
   selected (weight 0). Ties broken deterministically by symbol name
   alphabetical (ascending) so the rule is reproducible. Selection:
   LONG the worst 2 valid coins, SHORT the best 2 valid coins; the middle coin
   (or any NaN coin) gets 0. If fewer than 4 valid coins on day D, select
   among valid only (up to 2 worst long, up to 2 best short, disjoint; with
   <= 2 valid, longs take priority for the worst 1..2 and no shorts overlap).
4. Weights (fractions of sleeve equity, fixed): each selected long `+0.25`,
   each selected short `-0.25`, all others `0.0`. Fully selected day:
   gross 1.0x, net 0.0 (dollar-neutral). Thin days (NaN) have gross < 1.0x;
   counts reported. `w(sym,D)` is known at close D and is held over day
   E = D+1 only, entered at O(sym,E).
5. Holding-day gross return for day E (open-to-open):
   `g(E) = sum_sym w(sym,E-1) * (O(sym,E+1)/O(sym,E) - 1)`, computed only
   where both opens exist and O(E) != 0; a coin with a missing/zero open
   contributes 0 to g(E) that day (documented; counts reported). Single-day
   holding: no intra-day path.
6. Costs (gate model): rebalance at each day-E open pays taker on the traded
   notional: `cost(E) = 0.00055 * sum_sym |w(sym,E-1) - w(sym,E-2)|`
   (weights as fractions of sleeve equity; position before the first holding
   day of each year is 0, so entry is paid). Funding (adverse gate rule):
   `fund(E) = 0.0003 * sum_sym max(w(sym,E-1), 0)` (0.0001 x 3 settlements
   per day on longs; shorts pay/receive nothing).
7. Sleeve daily net return: `r_s(E) = g(E) - cost(E) - fund(E)`. Per anchor
   year the sleeve equity starts at 1.0 at the open of A_k and compounds:
   `eq(E+1) = eq(E) * (1 + r_s(E))` over holding days E in the year.
8. Anchor years: Y_k = holding days E with E 00:00 in [A_k, A_k+365d),
   A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24} (UTC).
   The last year needs O(2026-09-24) which does not exist in hourly_ext, so
   its final holding day is missing by construction (reported n_days).
9. Base daily returns (same daily grid as oc_tsmom, Variant B reset
   convention = user-facing year metric): per-shift normalised year segments
   F (F(a0) = 1.0; F = mean over shifts of e1_s / b_s with
   b_s = last hourly value <= a0), daily returns from F:
   `r_b(E) = F(E+1 00:00)/F(E 00:00) - 1` sampled on the hourly grid
   (e starts 2021-09-24 04:00/08:00, so day 2021-09-24 is partial; stated in
   results). Base year equity starts 1.0 and compounds r_b over the same
   holding days E as the sleeve (intersection of available days). Base
   monthly % = eq_b_end^(1/12)-1; base max yearly DD = max peak-to-trough on
   the base year path (daily-00:00 grid, no 1m marking; labelled as such;
   oc_kpi 1m-marked DDs are the published reference).
10. Combined (overlay): `r_c(E) = r_b(E) + 0.25 * r_s(E)` (0.25x sleeve on top
    of base). Combined equity starts 1.0 per year, compounds r_c. Combined
    monthly % = eq_c_end^(1/12)-1; combined max yearly DD from the combined
    path. Comparison is like-for-like (same days, same grid).
11. Per-year sleeve stats (descriptive + gate inputs): total return
    (eq_s_end - 1), monthly % (eq_s_end^(1/12)-1), Sharpe =
    mean(r_s)/std(r_s)*sqrt(365) (0.0 if std is 0/NaN/non-finite),
    maxDD on the sleeve year path, n_days, per-day mean cost/funding in
    bps, mean gross exposure, thin-day counts.
12. Correlation: Pearson corr over the year's holding days of r_s(E) vs
    r_b(E) (NaN if either leg is constant; reported; NaN counts as a miss,
    never imputed).
13. LOYO stability (descriptive, satisfies the default-rule spirit): for each
    held-out year h, pooled mean daily sleeve return over the other 4 years;
    PASS_loyo(h): pooled mean > 0 (strict; NaN = FAIL). Reported as
    `match x/5`. LOYO is DESCRIPTIVE ONLY (not part of the operative gate).

## Evaluation (fixed here — one variant only)

- PASS_pos(Y_k): sleeve monthly %(Y_k) > 0 (strict; equivalently total > 0).
- PASS_corr(Y_k): |corr_sleeve_base(Y_k)| < 0.15 (strict; NaN = FAIL).
- PASS_dd(Y_k): combined max yearly DD(Y_k) <= base max yearly DD(Y_k)
  (strictly not worse; exact <=, no tolerance; both in %; NaN = FAIL).
- DECISION RULE (assignment-specific, operative): PROMISING iff
  (a) PASS_pos in >= 4 of 5 anchor years, AND
  (b) PASS_corr in >= 4 of 5 anchor years, AND
  (c) PASS_dd in >= 4 of 5 anchor years. Otherwise NOT PROMISING.
  NaN counts as a miss, never imputed. All other stats (Sharpe, turnover,
  LOYO, excess return) are DESCRIPTIVE ONLY.
- Cross-checks (must hold, else the run is invalid): recomputed base annual
  nets compound from stored daily returns (residual ~0); reset base monthly
  reproduces oc_kpi published R within 0.05pp/month (same convention as
  oc_tsmom); hourly cap asserted (no t >= 2026-09-24 00:00 UTC loaded).

## Causality / correctness tests (tests/test_oc_xsrev.py)

- test_rank_uses_only_past_closes: synthetic closes; shifting C(D) changes
  only ret1/ranks at D and D+1 (weights held over E = D+1, D+2), never
  earlier; weight for E depends only on closes <= E-1 and executes at O(E).
- test_data_cap: no hourly row with t >= 2026-09-24 00:00 UTC is loaded;
  holding days never reach beyond available opens.
- test_hand_cases: (i) distinctly ordered 1d returns -> worst-2 long +0.25,
  best-2 short -0.25, middle 0, ties alphabetical; (ii) NaN ret1 coin never
  selected; (iii) one-day open-to-open gain with no rebalance and no funding
  (short-only day) gives exact r_s; (iv) long day deducts exactly
  0.0003*pos funding; (v) full rebalance 0->w pays 0.00055*|dw| turnover.
- test_recompute: results.json per-year sleeve/combined/base series recomputed
  independently from stored daily series equal the stored values (abs tol);
  PASS_pos/PASS_corr/PASS_dd counts and the promising flag match the AND rule.
- test_base_sanity: recomputed base year nets compound from the stored daily
  returns (residual ~0); v411 pkl keys are exactly {t,eq,eq_min}; reset base
  matches oc_kpi R within 0.05pp/month.

## Deliverables

research/tournament/oc_xsrev/: PLAN.md (this file), run_xsrev.py,
results.json, REPORT.md (tables + one-line verdict).
tests/test_oc_xsrev.py. No commits, no edits outside these two paths. One
process, no 1m data, RAM < 1 GB. Post-hoc changes, if any, are logged in
REPORT.md (none expected: single fixed rule, one run).

## Amendment log (append-only; original above is frozen)

- (none yet)
