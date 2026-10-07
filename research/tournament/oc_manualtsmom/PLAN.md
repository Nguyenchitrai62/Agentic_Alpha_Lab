# oc_manualtsmom PLAN (pre-registered BEFORE any outcome is computed)

No outcome of THIS task has been inspected. Rules below are frozen here.
Market data up to 2026-09-24 00:00 UTC may be read (assignment override; all
five years are research data; any finding needs prospective validation).
LIGHT job: one process, RAM < 1 GB, no 1m data (hourly bars only).

## Hypothesis (fixed here)

The honest MANUAL M5_human (15-minute reaction, night bar skipped, agents ON,
no bear filter; `research/diagnostics/oc_manualcap`, runs in
`oc_manualcap_runs.pkl`) earns 3.73 %/month at max yearly DD 17.9 and pooled
book win 0.65 — about 1.3 pp/month short of the MANUAL base (>= 5 %/month).
The daily BTC/ETH 30-day TSMOM sleeve (`research/tournament/oc_tsmom`, exact
code; daily rebalance at the next day open, taker, gate funding) earns
+0.9..+1.7 %/month standalone in 4/5 years, correlated +0.2..0.5 with the BOT.
Question: does overlaying / splitting the sleeve onto M5_human at sleeve
weights 0.25 / 0.50 / 1.00 of capital close the 1.3 pp gap while keeping
DD < 20 and win >= 55 %? Pre-registered direction: the sleeve adds return
every year (positive excess in >= 4/5 years) but also adds correlated DD, so
the base gate is expected to FAIL at high weights; this is a fixed-rule
combination, no fitted parameter, one run.

## Base (fixed here)

M5_human 4-phase runs from
`research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl`
(`{shift: {row: {run: {t, eq, eq_min}, wins: [...]}}}`), shifts s = 0..3.
Hourly eq/eq_min ONLY via `v388_bot_stop_distance.hourly` (imported, not
copied), grid G0 = 2021-09-24 04:00 UTC, g1 = Y1 + 12h = 2026-09-23 12:00 UTC.
Year-reset combination mirrors `reset_metric.year_reset` lines 18-19 exactly:
per shift s, E_s = e1_s[seg]/b_s, MN_s = m1_s[seg]/b_s with
seg = (index > a0) & (index <= a0+365d), b_s = last e1_s <= a0;
base_es = mean_s E_s, base_ms = mean_s MN_s.
Per year: R = 100*(es_end^(1/12)-1), DD = 100*max(1-ms/peakaccum(es)).
Base proof: recomputed yearly R/DD must EQUAL `oc_manualcap/results.json`
M5_human years_R / years_DD exactly (round-trip), else the run is invalid.
Full-path DD: continuous mix e,mn = v388.mix(runs, 'M5_human', g1),
fullDD = 100*max(1-mn/es-peak) over e.index > 2021-09-24 (must reproduce
oc_manualcap fullDD 17.79).
Anchors A in {2021-09-24, ..., 2025-09-24}; year = (a0, a0+365d] on the grid.

## Sleeve: exact oc_tsmom rebuild + official hourly marking (frozen)

Code copied EXACTLY from `research/tournament/oc_tsmom/run_tsmom.py`
(constants unchanged): coins BTCUSDT+ETHUSDT; hourly
`research/tournament/ext/hourly_ext.parquet` with t < 2026-09-24 00:00 UTC
only (asserted); day D = UTC day; O(sym,D) = open of bar t = D 00:00,
C(sym,D) = close of bar t = D 23:00 (missing day -> coin flat 0, no forward
fill); ret30(sym,D) = C(D)/C(D-30)-1, signal = sign (0 if any of 31 closes
missing); vol = std of 30 daily log returns ending D (ddof=1) * sqrt(365),
NaN/non-positive -> pos 0; pos(sym,D) = signal*min(0.10/vol,1.0), known at
close D, held over E = D+1 entered at O(E); g(E) = sum pos(E-1)*(O(E+1)/O(E)-1)
(missing open -> 0); cost(E) = 0.00055*sum|pos(E-1)-pos(E-2)| (pos before the
first holding day of each year = 0, i.e. entry paid); fund(E) =
0.0003*sum max(pos(E-1),0); r_s(E) = g-cost-fund.
Hourly marking copied EXACTLY from
`research/tournament/oc_tsmom_official/run_official.py::build_sleeve_hourly`
(worst-case: long at hour low, short at hour high; day-boundary eq == daily
sleeve; eq_min <= eq intraday; yearly-convention prev = 0 at each anchor for
cost; continuous stitched S_day levels for the full-path leg). Sleeve
cross-check: daily r_s per year must equal oc_tsmom r_sleeve (max abs gap
< 1e-6), else invalid.
Sleeve sub-account on the reset grid: F = S_eq[seg]/bS, FM = S_min[seg]/bS
with bS = S_day[a0] (eq_min normalised by the eq base, as in year_reset).

## Combinations (fixed here — 3 weights x 2 conventions = 6 rows)

Weights w in {0.25, 0.50, 1.00} (sleeve capital ADDITIONAL to the MANUAL
account; assignment-fixed, not tuned):
(a) overlay (sleeve on top of the full MANUAL account):
    combined_es(H) = base_es(H) + w*(F(H)-1),
    combined_ms(H) = base_ms(H) + w*(FM(H)-1);
(b) split capital ((1-w) MANUAL / w sleeve):
    combined_es(H) = (1-w)*base_es(H) + w*F(H),
    combined_ms(H) = (1-w)*base_ms(H) + w*FM(H).
Both start at 1.0 at each anchor by construction. Per year:
R = 100*(es_end^(1/12)-1), DD = 100*max(1-ms/peakaccum(es)).
Aggregates: 5y monthly R5 = (prod_y (1+tot_y))^(1/60)-1 from the year-reset
year nets (tot_y = es_end-1); worst year W = min yearly monthly; max yearly
DD = max yearly DD. Full-path DD (v388.mix-style, no reset): continuous base
mix e,mn from 2021-09-24; sleeve rebased to 1.0 at the grid start
(sleeve_cont = S_eq/s0, sleeve_low = S_min/s0); overlay:
combined_cont = e + w*(sleeve_cont-1), combined_low = mn + w*(sleeve_low-1);
split: combined_cont = (1-w)*e + w*sleeve_cont,
combined_low = (1-w)*mn + w*sleeve_low;
fullDD = 100*max(1-combined_low/peakaccum(combined_cont)).

## Win-rate metric (fixed here)

MANUAL win-rate metric = (book trades + sleeve daily trades) counted as
trades: per anchor year, book_nb/book_wb = pooled over the 4 phases from
oc_manualcap wins (sum_s wins_s[y].nb / .wb; book win = wb/nb); sleeve trade
= one holding day E of that year's day set with non-zero position
(|pos BTC|+|pos ETH| > 0 at E-1); sleeve win iff r_s(E) > 0 strict (net of
costs/funding; r_s == 0 counts as a loss). Combined year win =
(book_wb + sleeve_wins)/(book_nb + sleeve_trades); pooled 5y win likewise
(sums over years). Sleeve trades are new daily decisions a human places (ONE
rebalance order per coin per day holds), so counting them as trades is the
honest MANUAL metric. Cross-check: pooled book_nb/book_win must equal
oc_manualcap M5_human (3744 / 0.6482).

## Decision rule (fixed here)

- DEFAULT rule (header, on the per-year combined-minus-base monthly excess,
  overlay AND split rows separately): PROMISING iff (a) excess > 0 in >= 4 of
  5 anchor years (strict), AND (b) LOYO holds in >= 4 of 5 (pooled excess over
  the other 4 years keeps the full-5y pooled sign, strict). NaN = miss.
- OPERATIVE question (assignment): BASE_HIT iff R5 >= 5.0 %/month AND max
  yearly DD < 20 (plus full-path DD < 20 reported as a side condition) AND
  pooled win >= 55 %. Reported per row; the REPORT one-line verdict answers
  whether any row hits the MANUAL base. No selection or tuning on the scores:
  all 6 rows are scored once.

## Deliverables (fixed here)

`research/tournament/oc_manualtsmom/`: PLAN.md (this file), run_manualtsmom.py,
results.json, REPORT.md (tables + one-line verdict).
Test: `tests/test_oc_manualtsmom.py` (sleeve-exactness vs oc_tsmom; base proof
vs oc_manualcap; day-boundary eq == daily sleeve; eq_min <= eq; recompute of
aggregates, win metric, PROMISING/BASE_HIT flags; full-path DD recompute).
One process, no 1m data, RAM < 1 GB. Post-hoc changes, if any, logged in
REPORT.md (none expected: fixed rule, one run).

## Amendment log (append-only; original above frozen)

(none yet)
