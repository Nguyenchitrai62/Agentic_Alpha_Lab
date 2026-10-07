# oc_expirycb PLAN (pre-registered BEFORE any outcome is computed)

Combination screen (post-hoc informed, labelled): `oc_expirybook` + `oc_cbpremium` on the BOT book.

## Hypothesis (fixed here)

- `oc_expirybook/REPORT.md`: halving the book in the 48h before monthly Deribit expiry (last Friday 08:00 UTC, `[E-48h, E)`, both sides, x0.5) is PROMISING as assigned: DD not worse 4/5 AND total P&L >= 98% of base 4/5 (2021 fails both; 2022-2025 window losses halve into small gains).
- `oc_cbpremium/REPORT.md`: Coinbase-premium book-long tilt (longs x1.15 when z > 1, x0.85 when z < -1, else x1.0; shorts/flats unchanged) is NOT PROMISING as assigned: P&L higher 5/5 BUT DD not worse only 2/5 (return-only tilt, buys variance).
- Hypothesis: applying BOTH rules (premium tilt first, expiry halving after, exactly as each report defines them) keeps the expiry rule's DD benefit while adding the premium return: vs the common BASE, DD not worse in >= 4/5 AND P&L higher in >= 4/5. This is a post-hoc informed combination (the parents' outcomes were known when this screen was specified), so it is labelled as such and needs prospective validation; there is no new fitted parameter.

## Inputs (read-only, never edited)

- Book: `forward_v205.research_books_d2` rebuilt EXACTLY as `research/tournament/oc_dvolshort/compute_dvolshort.py::research_books_d2` (also mirrored in `oc_expirybook` and `oc_cbpremium`): `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2`, union index, missing -> 0.0, from `artifacts/research/engine_real/` (`member_A_O1_orders`, `member_Aq_O1_orders`, `member_B_tv`, `member_Bq_tv`, `members_v154[D]`, `members_quarterly_D`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Premium: `data/raw/coinbase_20260925/BTC-USD_1h.parquet` (Coinbase BTC-USD 1h) + Binance BTCUSDT 1h closes from `research/tournament/ext/hourly_ext.parquet`. Only bar STARTs < CUTOFF are used.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the old RULES.md hidden-year cut; all five years are research data, findings still need prospective validation).
- No 1m data, one process, RAM < 1 GB (4h + hourly inputs only).

## Exact causal definitions (fixed before seeing numbers)

- CUTOFF = 2026-09-24 00:00 UTC. Grid = inner join of the rebuilt book index with the opens index (dropna all), sorted 4h, restricted to `T in [2021-09-24, CUTOFF)`; bars with any coin missing a forward open are dropped (same as oc_dvolshort/oc_expirybook/oc_cbpremium: the last grid bar has no forward open and is dropped). `w[T,s]` is known at the close of bar `T` and is held over `[T, T+1)`. Forward exit `open[T+1]` must be at/before CUTOFF.
- Anchors: `A_k = 2021-09-24 .. 2025-09-24` (UTC). Years partition, no orphan bars: `Y_k = [A_k, A_{k+1})` for k = 0..3, `Y_4 = [A_4, A_4+365d)` (== `[A_4, CUTOFF)`; same bounds construction as the parents).
- Returns: `R1[T,s]` = `open[T+1]/open[T] - 1` (simple open-to-open, 4h).
- v410 bear regime FIRST (audited v410 rule, BTC-only, causal at close of T): on the FULL `opens_v154` BTCUSDT history compute `MA1200[T] = mean(open_BTC[T-1199..T])`, `rolling(1200, min_periods=600)`; `bear[T] = (open_BTC[T] < MA1200[T])` (strict; NaN -> False; `open[T]` inclusive, known at the close of T, exactly as v410, oc_expirybook, oc_cbpremium). One regime flag per bar, applied to all 5 coins.
- BASE (common control, = deployed book with v410): `w_base[T,s] = 0.5*w_raw[T,s]` if `bear[T] and w_raw[T,s] > 0`, else `w_raw[T,s]`. Shorts (`<0`), flats (`==0`) unchanged.
- Premium feature (exactly as `oc_cbpremium`, which copies `oc_optctx.load_premium`, BTC-only): inner join Coinbase and Binance hourly grids on bar START `t` (both with `t < CUTOFF`), `prem[t] = cb_close[t]/bin_close[t] - 1`; `mean24[t] = mean(prem[t-23..t])`, `rolling(24, min_periods=20)`; `z[t] = (mean24[t] - mean(W)) / std(W, ddof=1)`, `W` = up to 2160 prior `mean24` values (90 days of hourly samples, current excluded via `.shift(1)`), `rolling(2160, min_periods=1728)`; std == 0 -> NaN. Grid `end[t] = t + 1h`.
- Premium as-of (strict, exactly as oc_cbpremium/oc_optctx: bars strictly before T): an hourly premium row with start `t` (end `t+1h`) is usable at `T` iff its end is strictly before `T` (implemented as `end <= T - 1s`, i.e. `searchsorted(ends_ns, Tns - 1e9, side='left') - 1`). For 4h-aligned `T` the last usable hourly bar is `[T-2h, T-1h]` (1-2h staleness by design). `z(T)` = `cbprem_z90` of the last usable row (NaN if none / warm-up). One signal per bar, applied to all 5 coins.
- PREMIUM-ONLY (exactly as oc_cbpremium RULE, v410 first): for each (T, sym), if `w_base[T,s] > 0` and `z(T)` finite: `mult = 1.15 if z > 1 else (0.85 if z < -1 else 1.0)`; `w_prem[T,s] = mult * w_base[T,s]`. If `w_base <= 0` or `z` NaN, `w_prem = w_base` (shorts/flats/NaN-z bit-identical). Bear-row longs keep their v410 x0.5 inside `w_base`; the premium tilt multiplies on top.
- Expiry calendar (pure function of year/month, no market input; exactly as oc_expirybook): `E(y,m)` = last Friday of month m, 08:00 UTC, for 2021-01 .. 2026-09. Friday == weekday 4; `back = (last_day.weekday() - 4) % 7`.
- Expiry window (half-open, on bar-open time T; exactly as oc_expirybook): `in_exp(T)` = True iff T in `[E - 48h, E)` for some expiry E. The calendar is known years in advance: zero leakage by construction.
- EXPIRY-ONLY (exactly as oc_expirybook RULE): `w_exp[T,s] = 0.5 * w_base[T,s]` if `in_exp(T)` else `w_base[T,s]` (both sides, longs and shorts; flats stay 0).
- BOTH (this screen; expiry halving applied AFTER the premium tilt, per the assignment): `w_both[T,s] = 0.5 * w_prem[T,s]` if `in_exp(T)` else `w_prem[T,s]`. Multiplication commutes, so this equals premium-tilted expiry-halved weights; turnover is computed per path with its own prev chain (see costs).
- Costs (exactly as oc_dvolshort/oc_expirybook/oc_cbpremium): maker 0.0002 per unit turnover. Per (T,s) in global grid order: `cost_v[T,s]` = `0.0002*|w_v[T,s]-w_v_prev[s]|` (first grid bar prev = 0.0) separately for v in {base, exp, prem, both} with each path's OWN prev chain. Net cell: `pnl_v = w_v*R1 - cost_v`. No funding, vol target, governor, sleeve, SL/TP, or compounding across bars in the per-cell sums; the equity path below compounds per-bar portfolio returns. NOTE on the assignment text: it says "0.05% per unit turnover" in the combination paragraph; the shared code it tells us to reuse (`oc_dvolshort`) and both parent reports use maker 0.0002 (0.02%). To keep base/expiry-only/premium-only exactly reproducible against the parents, this screen uses 0.0002 and logs the discrepancy here (no 0.0005 variant; LIGHT single run).
- Book path per variant: per-bar portfolio return `rp_v[T] = sum_s pnl_v[T,s]` over the 5 coins. Per anchor year, equity reset to 1.0 at the year's first bar and compounded in grid order: `eq[i+1] = eq[i]*(1+rp_v[T_i])`. Full 5y path compounds the same way from the first bar of year 1 (context only). maxDD = peak-to-trough `max(1-eq_trough/running_peak)`. Worst week = minimum 42-bar (7-day) compounded return inside the year: `min_{i>=42}(eq[i]/eq[i-42]-1)`.
- Coverage: share of year bars with finite `z(T)` (expected 100%: premium grids start 2020-08, fully warmed up long before 2021-09-24); expiry share of bars per year (~6.6%).

## Evaluation (fixed here)

- Per anchor year report: `n_bars`, expiry share; book P&L net (base / expiry-only / premium-only / both); worst week (base / expiry / premium / both); maxDD (base / expiry / premium / both, per-year reset paths). Full-path maxDD and total P&L for the four variants as context (not part of the rule).
- DECISION RULE (assignment-specific for this combination; replaces the default same-sign/LOYO rule): the combination keeps the expiry DD benefit while adding the premium return iff (a) maxDD not worse (`DD_both <= DD_base`, tolerance 1e-12 for float noise) in >= 4/5 years, AND (b) total book P&L strictly higher (`pnl_both > pnl_base`) in >= 4/5 years. NaN on either side counts as FAIL. One-line verdict (PROMISING-style wording only if both legs pass; otherwise NOT PROMISING). The default tournament LOYO rule is N/A by construction: neither parent has a fitted parameter (pure calendar + fixed 0.5 factor; fixed z = +/-1 multipliers with fixed v410 regime), so there is nothing to leave out; the combination adds no new parameter either.
- Sanity cross-checks (context, not part of the rule): expiry-only vs oc_expirybook and premium-only vs oc_cbpremium per-year P&L/maxDD reproduce the parents (same grid, same costs); both-vs-singletons reported descriptively.
- Cost context: weights average << 1, so per-cell sums are in portfolio-return units; the per-year equity paths above are the scale that matters.

## Causality / alignment tests (tests/test_oc_expirycb.py)

- test_books_match_parents: rebuilt books equal the parent formula cell by cell on the common index (same files, same math).
- test_premium_and_bear_causal: sampled `z(T)` recomputed from premium panels truncated to rows with end < T are unchanged; bear[T] recomputed from opens truncated to `<= T` is unchanged; NaN-`z` rows never tilted; shorts/flats bit-identical base vs prem except via expiry; tilted longs exactly 1.15x/0.85x base; expiry-only exactly 0.5x base on window bars both sides and bit-identical off-window; both = 0.5x prem on window bars and bit-identical prem off-window.
- test_expiry_calendar_hand_checked: Sep 2025 -> Fri 2025-09-26 08:00 UTC; Feb 2024 (leap) -> Fri 2024-02-23 08:00 UTC; Jun 2026 -> Fri 2026-06-26 08:00 UTC; every expiry a Friday 08:00 UTC; window flags equal `[E-48h, E)` membership.
- test_grid_bounds_costs_partition: no `T` at/after CUTOFF; years partition the grid without gaps/overlaps; pnl columns finite; per-sym costs equal 0.0002*|w - w_prev| (first prev = 0) on all four paths; decision counts in results.json match recomputation.

## Deliverables

`research/tournament/oc_expirycb/`: PLAN.md (this file), `compute_expirycb.py`, `panel.parquet` (per-(T,sym) raw/base/exp/prem/both weights, bear flag, z, mult, in_exp, forwards, net cells; small), `results.json`, `REPORT.md` (tables + one-line verdict). No tuning on results; any post-hoc change logged in REPORT.md. No commits. LIGHT job: one process, 4h + hourly inputs only (no 1m), RAM < 1 GB.

## Post-hoc log

- (none yet; filled only if definitions change after outcomes are seen)
