# oc_bullshort — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

v410's bear-book filter halves book LONG targets while BTC 4h open < its
1200-bar mean and lifted the weak years. oc_bookic found the mirror weakness:
the BOT book short leg lost in 2023 (a bull year, -0.0378 gross, the only
negative year-leg; SOL/BNB/BTC shorts). Hypothesis: also gating book SHORTS
in bull regimes (BTC 4h open > its 1200-bar mean) cuts bull-market short
losses at small gross cost — i.e. the mirror rule helps on the same
vectorised book P&L that v410 used for longs.

## Inputs (read-only, never edited)

- Books: rebuilt EXACTLY as `scripts/forward_v205.py::research_books_d2`
  (`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2` with A=`member_A_O1_orders`,
  Aq=`member_Aq_O1_orders`, B=`member_B_tv`, Bq=`member_Bq_tv`;
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2` with D=`members_v154[D]`,
  Dq=`members_quarterly_D`; union index, missing -> 0.0) from
  `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  history from 2017 so every scored year has a full 1200-bar window).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old tournament-harness dev cutoff; all five anchor years are research data,
  findings still need prospective validation).
- No 1m data, one process, RAM << 1 GB (two small 4h frames only).

## Exact causal definitions (fixed now, before seeing numbers)

- Grid: inner join of books index with opens index (dropna all), sorted 4h
  grid. Weight `w_c[t]` is known at the close of bar `t`.
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. The last grid
  bar has no forward return and is dropped. Same timing as oc_bookic/bookvol.
- Trend (causal, mirrors v410 exactly): on the FULL BTC opens history,
  `MA1200[t] = mean(BTC_open[t-1199..t])` via
  `rolling(1200, min_periods=600).mean()`; `bear[t] iff BTC_open[t] < MA1200[t]`,
  `bull[t] iff BTC_open[t] > MA1200[t]` (strict; equality or NaN-MA -> neither,
  weight unchanged). Flag at `t` uses `open[t]` inclusive, i.e. known at the
  close of bar `t` — same timing as v410's decision-row transform.
- Filtered weights (applied to the raw book BEFORE vol scaling):
  `B0[t] = w[t]*0.5 where bear[t] and w[t] > 0, else w[t]` (v410 bear-long
  filter; book shorts unchanged);
  `B1[t] = B0[t]*0.5 where bull[t] and B0[t] < 0, else B0[t]` (mirror: shorts
  halved in bull);
  `B2[t] = 0 where bull[t] and B0[t] < 0, else B0[t]` (mirror: shorts flat in
  bull). Exactly 2 test variants (B1, B2) vs baseline B0.
- Unscaled book P&L per variant: `u_V[t] = sum_c wV_c[t]*r_c[t]` (gross).
- Deployed vol scale, per variant on its OWN trailing P&L (what the deployed
  engine would do after filtering): `sig_V[t] = std(u_V[t-360..t-1], ddof=1)
  * ANN`, `ANN = sqrt(6*365)`, min_periods 120; `s_V[t] = min(2,
  0.25/sig_V[t])`; NaN or sig <= 0 -> 1.0. Window ends at `t-1` (strictly
  before `t`: every input `w[s], open[s], open[s+1]` for `s <= t-1` is known at
  the close of `t-1`). Scaled weights `wsV_c[t] = wV_c[t]*s_V[t]`.
- Turnover (L1, undrifted — disclosed simplification as in oc_bookvol):
  `TO_V[t] = sum_c |wsV_c[t] - wsV_c[t-1]|`, first grid bar vs flat 0.
  Cost `0.0005 * TO_V[t]` (0.05% per unit turnover, as assigned).
- Variant net: `pn_V[t] = sum_c wsV_c[t]*r_c[t] - 0.0005*TO_V[t]`.
- Equity: compounded from 1.0 at the grid start, `eq[t+1] = eq[t]*(1+pn[t])`
  (weights are fractions of equity).
- Anchor years: `A_k = 2021-09-24 .. 2025-09-24`, partition `[A_k, A_{k+1})`
  for k=0..3 and `[A_4, A_4+365d)` for the last (leap-day fix as in
  oc_bookic/bookvol: 2023-09-24..2024-09-24 spans Feb-29, so literal +365d for
  all would orphan 6 bars; fixed here before seeing outcomes).
- Per (variant, year) on year bars: net return `= prod(1+pn)-1`; max DD on the
  year-rebased equity (start 1.0): `max(1 - eq/running-peak)`; Sharpe
  `= mean(pn)/std(pn,ddof=1)*ANN` (rf 0; NaN if < 30 bars or std == 0);
  long-leg gross `= sum of wsV_c[t]*r_c[t] over (c,t) with wsV_c[t] > 0`;
  short-leg gross `= same with wsV_c[t] < 0` (scaled gross BEFORE costs;
  costs reported separately at variant level, not allocated to legs).

## Decision rule (assignment default, applied to return AND DD vs B0)

- Per-year effects vs B0: `dRet_y = Ret_V,y - Ret_B0,y` (positive = V earns
  more); `dDD_y = DD_B0,y - DD_V,y` (positive = V draws down less). NaN or
  `<= 0` counts as FAIL (the common sign must be an improvement, not merely
  consistent).
- LOYO stability (no fitted parameters exist, so LOYO is a stability check):
  `LOYO_h` passes for a metric iff `sign(d_h) == sign(mean_{k!=h} d_k)` and
  that training mean is `> 0` (NaN -> fail).
- Variant V (B1 or B2) is PROMISING iff ALL FOUR hold: dRet > 0 in >= 4/5 years
  AND dDD > 0 in >= 4/5 years AND LOYO-Ret passes in >= 4/5 held-out years AND
  LOYO-DD passes in >= 4/5. Sharpe and leg splits are descriptive only.
- First-four-year (2021-2024) sensitivity is reported descriptively (repo
  selection window) but is NOT part of the verdict.

## Resources / constraints

- Write ONLY to `research/tournament/oc_bullshort/` (+ `tests/test_oc_bullshort.py`).
  No commits, no edits outside these paths.
- One process; only 4h opens + book parquets are loaded. No 1m data.

## Outputs

- `research/tournament/oc_bullshort/`: PLAN.md (this file),
  `compute_bullshort.py`, `results.json`, REPORT.md (tables + one-line
  verdict). No tuning on results; any post-hoc change logged in REPORT.md.
