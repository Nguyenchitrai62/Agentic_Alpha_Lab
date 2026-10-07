# oc_bnbvenue — PLAN (written BEFORE computing outcomes; DIAGNOSTIC, no rule)

## Task
DIAGNOSTIC (no rule). `research/tournament/oc_topbook` found BNB's Bybit
top-of-book spread is ~10x Binance's (~1.27 vs ~0.13 bps) while
BTC/ETH/SOL/XRP are identical. Using the book-venue replay, `oc_bybittp` and
`oc_venuegap` results plus their per-coin tables, quantify BNB's share of the
Bybit-vs-Binance drag (book and dip legs) and estimate, as a hypothesis only,
the effect of trading BNB on Bybit with (a) unchanged rules, (b) BNB dip rungs
only (no BNB book), (c) no BNB at all, on the deployment configuration's 5y
return and DD (approximate from per-coin P&L shares in `oc_kpi_g2` /
`oc_contrib` true-pair tables). Outputs: REPORT.md + results.json.

## Path note (frozen)
The assignment text cites `research/tournament/oc_bookvenue` for "book fills
Binance vs Bybit prices". That path does NOT exist (verified by `ls`
2026-10-06: no `oc_bookvenue` under `research/tournament/`). The only existing
book-venue replay is `research/diagnostics/oc_bookvenue/` (REPORT.md +
results.json, R2B1D17BF engine s=0/s=2, base/s5/book_byb/book_bin) with test
`tests/test_oc_bookvenue.py`. This study uses THAT folder as the book-venue
source and records the substitution here, before any outcome is computed.

## Hypothesis (fixed here, diagnostic only)
BNB's structurally wider Bybit book (~1.14 bps extra spread per side) is real
but small against round-trip economics, and the measured Bybit-vs-Binance drag
lives overwhelmingly in the DIP ladder (deployment TP shortfall), not in book
execution (venue-identical fill rates and sub-bps matched prices). Expected
picture: BNB dip-rung gap is positive but small (same sign in most years,
dwarfed by XRP which carries the whole B1 net gap); BNB shows no TP shortfall
in the B1 replica (symmetric solo TPs); deployment book-venue effect is
~0 %/month, so scenarios (a)/(b)/(c) move the deployment 5y return only via
BNB's ~13-14% additive P&L share and barely move gate DD (BNB carries only one
of five DD windows). All scenario numbers are HYPOTHESIS arithmetic only —
no re-simulation, no routing recommendation.

## Inputs (fixed here, all in repo — no fetch, no 1m)
- `research/tournament/oc_topbook/results.json`: `venue_spread_comparison`
  (per-coin binance/bybit spread_mean, ratio).
- `research/diagnostics/oc_bookvenue/results.json` + REPORT.md: s=0/s=2
  full-window monthly + per-year monthly for base/s5/book_byb/book_bin;
  book execution counts (issues/fills/fill_rate/stops/TPs) and matched
  limit/fill/stop/TP bps diffs; dip counts (rung_fill/TP/SL/timeout);
  open_shift medians. S5 window = bar open T in [2021-11-15, 2026-09-23).
- `research/tournament/oc_venuegap/results.json`: `gap_total_sum`,
  `per_coin_year` gaps (bin-byb equal-weight rung-y sums), `per_year` gaps,
  `per_coin_depth` sums, `totals`, `open_shift_bps`/`level_shift_bps` side rows.
- `research/tournament/oc_bybittp/results.json`: `div_counts` per coin
  (both_tp/bin_only/byb_only/neither), `single_venue_tp`, `totals`,
  `byb_recovery`/`bin_cost` side rows.
- `research/tournament/oc_contrib/results.json`: `by_coin.pooled` +
  `by_coin[0..4]` (n/pnl_mix_pct/win, books+dips entering that anchor year),
  `by_sleeve`, `pooled.pnl_mix_pct`, `dd_episodes[].by_coin`, `per_year_entry_totals`.
- `research/tournament/oc_kpi_g2/results.json`: deployment baseline =
  R2B1D17BFG2 (`equity.full_path`: net_pct/eq_end/DD_4h/DD_1m/DD_gate;
  `equity.years[]` R per anchor; BF `reference_BF` as neighbour column only).
  BOT book definition reference: `research/diagnostics/r2_decompose5/
  r2_decompose5.py` (`forward_v205.research_books_d2`, read-only reference,
  not executed).
- Market-data boundary per assignment: data up to 2026-09-24 00:00 UTC; all
  five anchor years (2021-09-24..2025-09-24, +365 d) are research data;
  any finding needs prospective validation before real money.

## Exact causal / definitional rules (frozen)
1. No 1m data, no minute cubes, no engine runs, no fills_U/ext joins. The
   script reads ONLY the six published JSONs above (+ REPORT.md text for
   quoted context). One process, RAM < 1 GB (JSONs total < 5 MB).
2. Dip-leg BNB share (B1 replica, equal-weight rung-y sums, venue-native):
   `bnb_gap = sum(per_coin_year[BNB].gap)`; `total_gap = gap_total_sum`;
   `bnb_share_net = bnb_gap / total_gap`; per-coin 5y sums for all five coins;
   BNB yearly signs from `per_coin_year`; BNB share of B1 fills =
   `n_BNB / n_ALL` from `n_fills`-scale totals where available; divergent-TP
   BNB share = `13 / 57` bin-only, `12 / 79` byb-only from `div_counts`.
   Rung-y sums are NOT portfolio %/month (stated wherever used).
3. Book-leg venue effect (deployment engine, single-phase s=0/s=2):
   `book_eff = monthly(book_byb) - monthly(base)`;
   `dip_eff = monthly(book_bin) - monthly(base)`;
   `gap = monthly(s5) - monthly(base)`; `residual = gap - book_eff - dip_eff`;
   per-year same differences. Book execution venue-identity from fill_rate
   diff (pp), stops/TPs diff (counts), matched limit/fill median/mean (bps).
   oc_bookvenue has NO per-coin book table, so BNB-specific book execution
   drag is reported as UNKNOWN from that source (not imputed); the only
   BNB book bound is the topbook spread diff
   `spread_extra = byb_mean - bin_mean` (~1.14 bps per side) stated as a
   per-fill upper bound, not a portfolio drag.
4. Deployment baseline: G2 `full_path` (net_pct 2538.74, eq_end 26.3874,
   DD_gate 16.82) and per-anchor R (2.588/3.282/6.045/10.677/4.648); 5y
   monthly geo mean `R5 = eq_end^(1/60) - 1` (60 anchor-months approximation,
   labelled as such). BNB P&L share: `bnb_add = by_coin.pooled.BNB.pnl_mix_pct`
   (39.332), `tot_add = pooled.pnl_mix_pct` (287.278),
   `bnb_share_add = bnb_add / tot_add`; yearly BNB mix% from `by_coin[y].BNB`.
5. Scenarios (hypothesis arithmetic ONLY, linear/proportional, no
   re-simulation, no compounding re-fit, funding excluded as in oc_contrib):
   (a) BNB-on-Bybit unchanged rules: cost ≈ BNB dip rung gap in rung-y units
   (`bnb_gap` vs Bybit rung P&L `totals.byB.sum`) translated to a monthly
   scale ONLY via the deployment dip_eff scale as an explicitly labelled
   proportional illustration (bnb_share_net * dip_eff per phase), plus the
   spread bound `spread_extra` per BNB book fill; verdict band "<0.1 %/month
   on single-phase scale" if the arithmetic lands there, else report the
   number with the same caveat. (b) BNB dip-only (drop BNB book): BNB book
   P&L is NOT separated per coin in oc_contrib, so report the feasible bound:
   overall book share `book_add / tot_add` applied proportionally to BNB
   (`bnb_book_est = bnb_add * book_add/tot_add`, `bnb_dip_est` remainder) as
   an ASSUMED-even-split illustration, plus the no-assumption bound
   (drop between 0 and full `bnb_add`). (c) No BNB: drop full `bnb_add`
   (yearly BNB mix% listed); illustrative monthly haircut
   `R5 * bnb_share_add` order-of-magnitude only. DD: BNB window shares from
   `dd_episodes[].by_coin` (share_of_window per episode); gate-DD effect is
   DIRECTIONAL ONLY (no re-simulation; state which episodes BNB carries).
6. Cross-checks the script must assert: venuegap per-coin 5y sums add to
   `gap_total_sum` (±0.01); contrib yearly BNB mix% sums to pooled BNB
   (±0.05); contrib pooled sleeves add to pooled total (±0.5); kpi G2
   `eq_end` reproduces `R5` band 5-6 %/month; topbook BNB ratio band 9-11x
   with other coins 0.95-1.05x.
7. Money: rung-y sums unitless fractions; mix% = 1/4-capital additive
   (oc_contrib); %/month = geometric monthly means. No fees/funding beyond
   what each source already nets (quoted per source).

## Decision rule (fixed: DIAGNOSTIC, no PROMISING rule)
No PROMISING/NOT-PROMISING verdict (assignment marks this DIAGNOSTIC, so the
default >=4/5 same-sign + >=4/5 leave-one-year-out rule does NOT apply). The
REPORT answers: (i) BNB share of dip-leg gap (B1 rung-y + deployment TP
shortfall context); (ii) BNB share of book-leg gap (aggregate + why
per-coin is unknown + spread bound); (iii) scenario (a)/(b)/(c) hypothesis
numbers on the G2 5y return and DD with all approximations labelled;
(iv) which leg a BNB-venue fix would have to live in. One-line verdict = the
(iv) sentence (descriptive, hypothesis-only).

## Protocol (fixed)
- PLAN.md written before any outcome computation (this file). Then script
  `compute_bnbvenue.py` (stdlib json only; reads the six JSONs; writes
  `results.json`; prints the cross-checks). Then REPORT.md renders
  results.json tables + one-line verdict. Tests
  `tests/test_oc_bnbvenue.py` (synthetic hand checks of share/scenario
  helpers + boundary/cross-check guards; no repo data in tests).
- No commits; no edits outside `research/tournament/oc_bnbvenue/` (+ the one
  test file). No `../Kronos`, no backend/bot edits, no orders.

## Resource / leakage guardrails
- ONE process, RAM < 1 GB, no 1m files, no bulk downloads, no GPU.
- Only files WRITTEN: `research/tournament/oc_bnbvenue/` (PLAN.md,
  compute_bnbvenue.py, results.json, REPORT.md) + `tests/test_oc_bnbvenue.py`.
- Post-2025-09-24 boundary: all five years are research data per assignment;
  no model/threshold is fitted here (diagnostic ratios only); any future
  routing claim needs prospective validation.
- Repro: `compute_bnbvenue.py` prints inputs/gaps/shares/scenarios and writes
  results.json; REPORT.md renders the same tables.
