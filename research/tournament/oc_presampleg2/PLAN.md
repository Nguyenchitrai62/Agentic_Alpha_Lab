# oc_presampleg2 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08)

Assignment: docs/opencode/OPENCODE_W_oc_presampleg2.md + docs/opencode/OPENCODE_W_COMMON_20261007.md.
Write ONLY `research/tournament/oc_presampleg2/` and `tests/test_oc_presampleg2.py`.
Heavy work via heavy_slot (tag oc_presampleg2, never --leader). CPU only. Progress print >= every 10 min.

## Question

Can the FULL deployed G2 (book + dip sleeve) be replayed on the unseen pre-sample years 2018-2020?
Dip sleeve alone: done (oc_presample, oc_presample2: profitable most years, frozen rules).
Book member predictions exist only from 2021-09-24 (all cached members start there; verified
2026-10-08). So a full replay needs walk-forward retraining of the book on pre-sample data.

## Deployed G2 book (confirmed from code BEFORE any outcome, 2026-10-08)

`scripts/forward_v205.py::research_books_d2` (= v285 `D2_d20`, = oc_memberdrop FULL):
`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 + 0.2*(D+Dq)/2` (union index, missing -> 0.0).
Implicit FULL weights: A/Aq/B/Bq 0.2 each, D/Dq 0.1 each (sum 1.0).
- A/Aq = `member_A_O1_orders` / `member_Aq_O1_orders` (v240 O1: v144 builder + 17 TV + 6 ORDER-level
  whale-flow features on the PERP orders table `data/raw/aggflow_20260928_orders`).
- B/Bq = `member_B_tv` / `member_Bq_tv` (v233 T3: v144 builder + 17 TV + 5 Deribit OPTIONS-flow
  features `v150.OPT` on `data/raw/deribit_opt_20260926/BTC|ETH_options_4h.parquet`).
- D/Dq = `members_v154[D]` / `members_quarterly_D` (v154/v285: v144 builder + 5 Coinbase-premium
  features `v111.CB` on `data/raw/coinbase_20260925` 1h vs Binance SPOT 4h).
- v144 base (all members): v92 7d LO + v94 LS + v103 1d/3d LS + vol-target + xs, pooled HGBR
  (max_depth=4, lr=0.03, iter=400, min_leaf=300, l2=1.0, seed=0); quarterly members via the frozen
  v202 wrapper (each model predicts its own quarter, per-target cutoffs/embargoes relative to anchor).
- G2 dip sleeve + caps: the oc_presample2 G2 row (R2 depths 2.5/3/3.5/4/5 sg, B1 mult 1/(1+n),
  kd=1.7, budget 0.26*1.7=0.442 gap 0.02, gross cap G=2.0 per phase sub-account, close5 4-sg stop +
  8-sg backstop + TP 1.0 sg + next-4h-open timeout, stop-first, live offsets 16..238, gate costs
  maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h). R2 agent size = 1.0, scale = governor
  = 1.0 pre-2020 (no walk-forward R2 tables exist; labelled, same as oc_presample).

## Part A - feasibility (report before running anything heavy; read-only probes only)

For each of the 6 members list the DEFINING inputs (the features beyond the v144 price base) and
check existence for 2018-01-01 .. 2020-09-30 on the majors (BTC/ETH/BNB/XRP; SOL excluded: no
pre-2020-08 data anywhere). Probe = first/last timestamps of the source files, no outcomes.
Decision rule (pre-registered): a member is BUILDABLE iff (i) its defining inputs exist for >= 50%
of the test span 2018-01..2020-09, (ii) its base price panel (4h with taker-buy columns for the
v103 kline-flow features) exists from 2017, (iii) it can be trained walk-forward per-anchor with
data before A minus the frozen embargoes. Otherwise NOT AVAILABLE under frozen rules.
Substitution ban (pre-registered): a missing PERP-only input may NOT be silently swapped for its
SPOT equivalent inside a "frozen" member; any venue change is a disclosed proxy, not the member.
NaN rule (pre-registered, precedented: the frozen v92 stack already trains its 2017 prefix with
funding NaN): inputs that are PARTIALLY missing (NaN for some dates) are kept as NaN through the
frozen merge code; HGBR handles NaN natively. Inputs that are 100% missing for every pre-sample
anchor's train+test are NOT "kept as NaN" - the member is NOT AVAILABLE (it would be a different
member wearing the same name).

Expected directions (to VERIFY with probes, not outcomes; verdict follows the probes either way):
- A/Aq: defining input = PERP order-level flow (`aggflow_20260928_orders`, starts 2020-01-01) ->
  0% of span -> expect NOT AVAILABLE.
- B/Bq: defining inputs = TV (100%, price-derived) + Deribit options (BTC from 2019-01-01,
  ETH from 2019-03-21 -> ~60% of span) -> expect BUILDABLE WITH DISCLOSED PARTIAL OPTIONS
  (frozen v233 recipe run as-is, options NaN where the archive has nothing).
- D/Dq: defining input = Coinbase premium (BTC/ETH 1h from 2017-08-01, market-wide join on t ->
  ~100%) -> expect BUILDABLE (frozen v154/v285 recipe on the spot-stitched panel).
- Base panel: perp 4h starts 2019-09..2020-02 per coin (too late); spot prefix
  (`spot_majors_20260925/*_spot_4h_2017`, HAS taker-buy columns, verified 2026-10-08) + presample
  1m-built 4h (same construction as oc_presampleflow) covers 2017-08..2020-09 -> panel OK.

## Part B - pre-sample book + 4-phase engine (ONLY if Part A finds TV/price members buildable)

Single pre-registered variant PB + one reference row DIP0. No tuning, no selection; any change
after seeing an outcome is a disclosed extra row.

- Book PB (frozen recipes, fresh module copies - the v233/v240 pattern: importlib _load, override
  ONLY the price-panel loader to the spot-stitched panel and the anchor list to pre-sample anchors;
  features/model/label/embargo/merge code UNCHANGED):
  `o1' = (B_ps + Bq_ps)/2` (A,Aq dropped), `d' = (D_ps + Dq_ps)/2`,
  `PB = 0.8*o1' + 0.2*d'` (research_books_d2 weights with missing members dropped and
  renormalised: annual sleeve B alone, quarterly sleeve Bq alone, D weight kept iff D buildable).
  FALLBACK (pre-registered, labelled): if D_ps fails to build, `PB = o1'` and the fallback is stated.
  Quarterly anchors for the book (v202 cadence shifted to pre-sample, frozen rhythm): quarterly on
  the 24th from 2018-03-24 (first anchor with >= 6 months of spot history) through 2020-06-24; each
  model predicts its own quarter; per-target cutoffs/embargoes unchanged (relative to each anchor).
  Annual members use the same recipe with annual anchors 2018-09-24, 2019-09-24 (train: everything
  before A - 7d embargo). Coins: BTC/ETH/BNB/XRP as available (warm-up: no book weight before a
  coin's first spot bar + 60 days, same rule as oc_presample; SOL excluded).
- Engine (replica level, NOT the v421 stack - pre-registered label): the oc_presample2 G2 core is
  vendored VERBATIM into `presampleg2.py` (dip leg bit-gated, see below) and extended with a book
  leg in the same audited style. Book-leg mechanics (frozen HERE, engine_user-inspired, user
  trade-mode compliant): at each 4h close, target = PB weight (final vol-targeted units, same as
  research_books_d2); delta vs drifted position -> ONE resting limit order 10 bps better than the
  minute-0 price, live minutes 5..59 of the holding bar (no fill in the first 5 min), strict
  1m trade-through fill (maker 0.0002), expire unfilled (position unchanged). Every open book
  position carries SL = entry*(1-3*sg_d) market taker + TP = entry*(1+6*sg_d) limit maker
  (engine_user defaults m_sl=3.0, TP=2*m; sg_d = daily sigma = std of 4h open-to-open over 360 bars
  known at the decision * sqrt(6)); checked every 1m; stop-first (both touched -> stop). No R2
  tables, no grid policy, no bear scaler pre-2020 (all fit on 2021-2026; disclosed). Gross cap 2.0
  across book+dip (G2 cap; disclosed proxy: shared cap, not per-sub-account). Gate costs + adverse
  funding; $10k minimum-notional + cross-margin liquidation check per AGENTS.md.
- Windows (oc_presample2 yearly windows, equity reset per year per phase): Y2018 = 2018-01-01 ..
  2019-01-01, Y2019, Y2020p = 2020-01-01 .. 2020-09-01 (rungs/book opened on bars with open in the
  interval), Y2017-partial as an extra row (first-trading-date .. 2018-01-01). 4 clock phases
  s in {0,1,2,3} on the ORIGIN=2020-01-01 grid (identical to oc_presample2).
- Rows: DIP0 = dip sleeve alone (must match oc_presample2 G2 cells; full 16-cell check, not 1 cell);
  PB = pre-sample book + frozen G2 dip. Metrics per (row, year): 4-phase MEAN %/month (geometric),
  MEAN DD + WORST-phase DD (1m-marked incl. open positions), fills/stops/wins; book-vs-dip P&L
  attribution (separate equity legs: book-only, dip-only, combined - same trades, attribution by
  sleeve, labelled).
- Fidelity gates (BEFORE any PB number is looked at): (G1) the vendored dip core replays ALL 16
  oc_presample2 G2 cells (Y2017/Y2018/Y2019/Y2020p s{0..3}) bit-for-bit on all simulate-level
  fields; if it mismatches, stop and report. (G2) v421-stack reproduction is OUT OF SCOPE for
  pre-sample years (no G2 books exist before 2021-09-24; the common-header v421 check applies to
  2021-2026 overlays, stated here so the omission is explicit, not hidden).

## Metrics / reporting

Per (row, year, phase): %/month geometric = 100*(E_end^(30.4375/N_days)-1); max DD % from 1m-marked
equity incl. open positions; fills, stops, TPs, timeouts, win rate (ret > 0 after costs); peak gross;
end equity. Per (row, year): 4-phase means (same convention as oc_presample2) + book-vs-dip split.
Spot-vs-perp caveat on every number (fills/exits on SPOT 1m, perp gate costs).

## Leakage / execution statement (to verify in REPORT)

Features at bar t use bars/trades/candles <= t only (frozen feature functions, imports unchanged);
fits use only rows with label end < anchor - embargo (frozen cutoffs); fills use strict 1m
trade-through at minutes >= 5 (book) / 16..238 (dip); exits evaluated f+1..240 + next-bar open;
no test-year statistic enters any choice (weights 0.8/0.2 frozen; blend fallback pre-registered).

## Protocol / resources

Scripts ONLY in `research/tournament/oc_presampleg2/`: `probe.py` (Part A read-only availability
probes -> `tmp/probe.json`), `presampleg2.py` (vendored G2 dip core + book leg + yearly driver ->
`results.json`), scratch under `tmp/` only. Data stores read-only. One coin's 1m slice in RAM at
a time (float32); HGBR fits are CPU small-job; any step expected > 0.4 GB goes through
`scripts/heavy_slot.py` (tag oc_presampleg2, never --leader). Progress printed >= every 10 min.
Tests: `tests/test_oc_presampleg2.py` (synthetic hand checks: strict fill, stop-first, funding,
budget/cap, book limit fill/expiry, SL/TP levels; causality: sigma excludes the bar, train rows
end before anchor-embargo, no fill in minutes 0..4; truncation: legs open only on bars with open
in [S, E)). Run `.venv/Scripts/python.exe -m pytest tests/test_oc_presampleg2.py -q`.
Outputs: `results.json`, `REPORT.md` (Part A matrix + Part B tables + 3-line Vietnamese verdict).
No commits; no edits outside `research/tournament/oc_presampleg2/` (+ the one test file).
Git is read-only (never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
