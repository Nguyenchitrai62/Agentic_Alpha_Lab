# oc_tsmom_official PLAN (pre-registered BEFORE any outcome is computed)

Post-hoc informed OFFICIAL-METRIC check, labelled as such (sleeve, base rows
and weights are chosen AFTER seeing `oc_tsmom` and `oc_tsmomcombo`). No
outcome of THIS task has been inspected; the rules below are fixed here.
Market data up to 2026-09-24 00:00 UTC may be read (assignment override; all
five years are research data; any finding needs prospective validation).
LIGHT job: one process, RAM < 1 GB, no 1m data (hourly bars only).

## Hypothesis (fixed here, descriptive)

`oc_tsmomcombo` found R2B1D13BF + 0.10x the oc_tsmom BTC/ETH 30-day TSMOM
sleeve at 5.07 %/month and max yearly DD 14.49 on a DAILY grid that
understates DD by 0.7-2.8 pp vs the official hourly+eq_min convention.
Question: recomputed on the OFFICIAL metric (hourly marking with intraday
lows/highs, year_reset convention, conservative DD from the combined eq_min),
does any R2B1D13BF / R2B1D14BFX5 / R2B1D17BFG2 + sleeve combination reach the
stretch (max yearly DD < 15 with >= 5 %/month)? This is REPORTING ONLY.

## Sleeve: exact oc_tsmom rebuild (frozen; constants unchanged)

Code copied from `research/tournament/oc_tsmom/run_tsmom.py`:
coins BTCUSDT+ETHUSDT; hourly `research/tournament/ext/hourly_ext.parquet`
with t < 2026-09-24 00:00 UTC only; day D = UTC day;
O(sym,D) = open of bar t = D 00:00, C(sym,D) = close of bar t = D 23:00
(missing day -> coin flat 0, no forward fill);
ret30(sym,D) = C(D)/C(D-30)-1, signal = sign (0 if any of 31 closes missing);
vol = std of 30 daily log returns ending D (ddof=1) * sqrt(365),
NaN/non-positive -> pos 0; pos(sym,D) = signal*min(0.10/vol,1.0), known at
close D, held over E = D+1 entered at O(E);
g(E) = sum pos(E-1)*(O(E+1)/O(E)-1) (missing open -> 0);
cost(E) = 0.00055*sum|pos(E-1)-pos(E-2)| (pos before first holding day = 0);
fund(E) = 0.0003*sum max(pos(E-1),0);
r_s(E) = g-cost-fund. Anchors A in {2021-09-24,...,2025-09-24}, year =
holding days E in [A,A+365d) with O(E),O(E+1) available.

## NEW: hourly marking of the sleeve (frozen)

Hourly grid = the v388 hourly grid (1h, g0 = 2021-09-24 04:00 UTC,
g1 = 2026-09-23 12:00 UTC = Y1+12h). Let S(E) be sleeve equity (per 1.0
notional) at E 00:00; S compounds r_s at day boundaries exactly, so
S(E+1) = S(E)*(1+r_s(E)). cost(E), fund(E) are charged at the day open.
For grid points H in (E 00:00, E+1 00:00] with position p = pos(E-1):

- eq(H): 1 - cost(E) - fund(E) + sum_sym p(sym)*(PX(sym,H)/O(sym,E)-1),
  times S(E), where PX = close of the hourly bar t = H-1h; at the day
  boundary H = E+1 00:00 exactly, PX = O(E+1) (execution price), so the
  day-end eq equals S(E+1) exactly (no close/next-open gap).
- eq_min(H) (worst-case mark): same formula but PX replaced per coin by
  low(sym,H-1h) if p > 0, high(sym,H-1h) if p < 0 (missing OHLC -> 0
  contribution for that coin that hour). At day boundaries eq_min uses the
  closing hour's worst (stays conservative, may sit below eq — same
  convention as v388 eq_min <= eq on the grid).

Sleeve eq/eq_min are single continuous hourly series (no phases).

## Base + combination on the official metric (frozen)

- Base legs: R2B1D13BF + R2B1D14BFX5 from
  `research/parallel/rounds/parallel-20260906-r2/v424/v424_runs.pkl`,
  R2B1D17BFG2 from `.../v421/v421_runs.pkl` (shifts s = 0..3, keys
  {t,eq,eq_min}). Hourly eq/eq_min ONLY via `v388_bot_stop_distance.hourly`
  (imported, not copied). Base proof: call
  `research/diagnostics/r2_decompose5/reset_metric.py::year_reset` per row
  and year and require exact reproduction of the official numbers
  (`v424_result.json` / `v421_result.json`: D13BF R 4.971 / DD 14.98,
  D14BFX5 5.067 / 15.34, D17BFG2 5.41 / 16.91) before combining.
- Year-reset combination (overlay; mirrors year_reset lines 18-19 exactly):
  per shift s, E_s = e1_s[seg]/b_s, MN_s = m1_s[seg]/b_s with
  seg = (index > a0) & (index <= a0+365d), b_s = last e1_s <= a0;
  base_es = mean_s E_s, base_ms = mean_s MN_s;
  sleeve F = S[seg]/bS, FM = SM[seg]/bS with bS = last S <= a0
  (eq_min normalised by the eq base, as in year_reset);
  combined_es(H) = base_es(H) + w*(F(H)-1),
  combined_ms(H) = base_ms(H) + w*(FM(H)-1) (simultaneous conservative low).
  Per year: R = 100*(es_end^(1/12)-1), DD = 100*max(1-ms/peakaccum(es)).
  Weights w in {0.10, 0.25} (3 rows x 2 = 6 combos, fixed by assignment;
  primary focus R2B1D13BF, the combo-study stretch candidate).
- Full-path DD (v388.mix-style, no reset): continuous base mix
  e,mn = v388.mix(runs,row,g1) from 2021-09-24, sleeve rebased to 1.0 at the
  grid start; combined_cont(H) = e(H) + w*(sleeve_cont(H)-1),
  combined_low(H) = mn(H) + w*(sleeve_low_cont(H)-1);
  full-path DD = 100*max(1-combined_low/peakaccum(combined_cont)).
- Aggregates: 5y geometric monthly = (prod_y (1+tot_y))^(1/60)-1 from the
  year-reset year nets; worst year = min yearly monthly; max yearly DD =
  max yearly DD. Cross-checks (must hold, else invalid): sleeve daily r_s
  equals oc_tsmom r_sleeve per year (max abs gap < 1e-6); w = 0 reproduces
  the base year nets; compounding residuals ~0.

## Decision rule (fixed here)

REPORTING ONLY: no PROMISING / NOT-PROMISING selection is made (post-hoc
informed official-metric check per the assignment). The header default
(4-of-5 same-sign years + 4-of-5 LOYO) is evaluated DESCRIPTIVELY ONLY on
the per-year combined-minus-base monthly excess (sign consistency across
the 5 anchor years; LOYO = pooled excess over the other 4 years keeps the
full-5y sign), with no gate attached. The operative question is the
stretch flag: 5y R >= 5.0 AND max yearly DD < 15 on the official metric,
reported per combo. NaN counts as a miss, never imputed.

## Deliverables (fixed here)

`research/tournament/oc_tsmom_official/`: PLAN.md (this file),
run_official.py, results.json, REPORT.md (tables + one-line verdict).
Test: `tests/test_oc_tsmom_official.py` (sleeve-exactness vs oc_tsmom;
hourly-marking properties: day-boundary eq == daily sleeve, eq_min <= eq
intraday, causality of signal/positions; base proof vs official numbers;
recompute of aggregates, stretch flags and full-path DD from stored
series). One process, no 1m data, RAM < 1 GB. Post-hoc changes, if any,
logged in REPORT.md.

## Amendment log (append-only; original above frozen)

(none yet)
