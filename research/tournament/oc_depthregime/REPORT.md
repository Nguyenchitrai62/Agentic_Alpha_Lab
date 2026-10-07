# oc_depthregime REPORT — do deep dip rungs pay in any bar-open regime? (2026-10-06; PLAN pre-registered)

DIAGNOSTIC (no rule, no selection, no PROMISING verdict). Universe: R2B1D17BF
engine replicas `oc_kpi/events_s{0..3}.parquet` (4 phase sub-accounts, live
2021-09-24..2026-09-23+shift), FIFO rung pairing per symbol (copy of
oc_contrib: 21,389 rungs, 0 unpaired exits, 0 left open, 0 outside anchor
years). Year = FILL time in anchor year `[A_k,A_k+365d)`. `pnl` = exit
weight x engine ret (net of rung fees, fraction of sub-account equity);
`pnl_mix%` = `pnl_sub/4*100` (additive, as oc_contrib); `win` = ret > 0.
Groups: deep = {4.0,5.0} (3,711 rungs), shallow = {2.5,3.0,3.5} (17,678).
Replication: deep pooled -80.72 = -(36.22+44.50) and shallow +257.37 =
201.86+60.06-4.54 mix% matches oc_contrib depth table exactly. Regimes use
only data with time <= T0 = floor(fill_t to the standard 4h grid) except the
realised exit split: bear = v410 BTC open4 < MA1200 incl T0 min600
(NaN->bull); btc30 = open4BTC[T0]/open4BTC[T0-180]-1 up iff >0; sigma_terc =
per-coin sigma4 (4h-open returns trailing360/min120) vs walk-forward
p33/p66 cutoffs fitted on T < anchor-7d; n_evt = distinct other majors in the
SAME shift with a rung_fill in [fill_t-60min, fill_t] (event-based proxy for
B1 n — exact 1m `C<=O*(1-2.5sig)` n not recomputed, no 1m read per LIGHT);
hour = UTC bucket of fill_t; exit = realised kind (not pre-trade). 0 unknown
btc30, 0 unknown sigma. All five years are research data; findings need
prospective validation. Full numbers: `results.json`. Post-PLAN fix logged:
n_evt first counted fills pooled over shifts (every fill n2p, no variation);
corrected to same-shift counts (PLAN updated, script re-run).

## Year totals (deep vs shallow, mix% | n | win)

| year | deep | shallow |
|---|---|---|
| 2021 | -19.69 \| 749 \| 0.370 | +47.60 \| 3360 \| 0.700 |
| 2022 | -23.67 \| 811 \| 0.392 | +43.72 \| 3249 \| 0.766 |
| 2023 | -20.02 \| 839 \| 0.485 | +48.84 \| 3706 \| 0.784 |
| 2024 | -6.35 \| 584 \| 0.488 | +86.86 \| 3362 \| 0.766 |
| 2025 | -11.00 \| 728 \| 0.394 | +30.36 \| 4001 \| 0.699 |
| pooled | -80.72 \| 3711 \| 0.424 | +257.37 \| 17678 \| 0.742 |

## Deep mix% by regime per year (shallow in brackets, all mix%)

bear/bull: 2021 deep -15.36/-4.33 (sh +40.66/+6.94); 2022 -7.63/-16.04
(+17.12/+26.59); 2023 -2.14/-17.89 (+6.31/+42.54); 2024 -0.97/-5.38
(+4.97/+81.89); 2025 -6.18/-4.82 (+15.11/+15.24). Deep loses in all 10 cells.

btc30 up/down: 2021 deep -1.72/-17.97 (sh +16.06/+31.54); 2022 -7.95/-15.72
(+33.26/+10.46); 2023 -15.32/-4.70 (+39.83/+9.02); 2024 -3.47/-2.88
(+66.12/+20.74); 2025 -4.69/-6.31 (+16.09/+14.27). Deep loses in all 10 cells.

sigma tercile low/mid/high: 2021 deep -18.95/-0.74/0.00 n=685/64/0;
2022 -23.89/+0.73/-0.51 n=756/41/14; 2023 -16.36/-3.67/0.00 n=756/83/0;
2024 -1.36/-3.57/-1.42 n=309/213/62; 2025 -10.10/-0.90/-0.00 n=670/54/4.
Deep loses everywhere it has size (low holds 85% of deep rungs and loses big
every year); mid/high positives are single-year tiny cells (best: 2022 mid
+0.73 on n=41, win 0.68; high has 0 fills in 2021/2023).

n_evt n0/n1/n2p: 2021 deep -1.82/-1.67/-16.20 n=44/72/633;
2022 -8.10/-1.06/-14.50 n=130/80/601; 2023 -2.27/+0.23/-17.98 n=100/70/669;
2024 -1.47/-0.58/-4.30 n=87/82/415; 2025 -0.97/-1.48/-8.56 n=56/37/635.
Deep loses in 14/15 cells; the single positive (2023 n1 +0.23, n=70) is tiny
and negative in the other four years. Idiosyncratic n0 flushes lose in all 5
years (pooled deep n0 -14.63 mix%, win 0.43 on n=417). Joint n2p holds 80% of
deep rungs and 76% of the deep loss (pooled -61.54 of -80.72).

hour h00_05/h06_11/h12_17/h18_23: deep positives in 3/20 cells only, each in
one year and small (2022 h06_11 +0.45 n=85; 2023 h12_17 +0.72 n=148; 2024
h00_05 +0.44 n=183) and negative in the other four years of that bucket.

exit (realised, NOT pre-trade): deep rung_tp +8.24/+8.26/+11.57/+11.09/+5.51
(all 5 years, win 1.0 by construction, n=197-281/yr) vs rung_sl
-10.02/-15.40/-21.57/-5.45/-5.37 and rung_timeout
-17.92/-16.53/-10.03/-11.98/-11.13 (timeouts are 55-63% of deep rungs every
year). TP-positive is selection bias, not a keep rule: only ~30% of deep
rungs ever reach TP.

## Plain paragraph

Deep 4.0/5.0σ rungs lose money in every anchor year (-19.7/-23.7/-20.0/-6.3/
-11.0 mix%) and there is no bar-open regime where they pay: they lose in all
10 bear/bull cells, all 10 BTC-30d up/down cells, every sigma-tercile cell
that has any size (low-vol environments hold 85% of deep fills and lose the
most), all 5 idiosyncratic n0 years and 4/5 n1 years (the one positive is
+0.23 mix% on 70 rungs in 2023), and 17/20 hour buckets (the 3 positives are
one-year-only small cells). Joint n2p flushes carry most of the loss but
cutting only them would still leave a losing deep book, and the n0/n1
remnants lose every year too; sigma-high rarely even fills a deep rung
(80 fills in 5 years). The only deep-positive split is the realised exit —
rungs that reach take-profit (+5.5 to +11.6 mix%/yr) — which cannot be known
at the bar open and covers only ~30% of deep rungs while stops and timeouts
lose in all 15 year-cells. Shallow rungs, by contrast, are positive in all 5
years in every regime above. A conditional rule cannot rescue the deep rungs
from these regimes: nothing observable at the bar open separates a paying
deep environment from a losing one.

## Verdict

VERDICT (descriptive, no selection): deep rungs lose in ALL bar-open regimes
tested — no keepable regime exists (including idiosyncratic n0 flushes); the
realised-TP split is the only deep-positive cut and is not tradeable ex ante.

## Caveats

Additive `pnl_mix` (compounding gap as in oc_contrib); exit-time pairing is
FIFO per symbol (max fill/exit weight diff not re-logged here — pairing code
is the oc_contrib copy and totals replicate it exactly); n_evt is an
engine-fill co-occurrence proxy, not the exact 1m B1 flush count (LIGHT: no
1m read — same-minute ties across coins counted as joint, disclosed); sigma
cutoffs drift down over the years (BTC p33 1.40% in 2021 -> 0.99% in 2025)
so tercile labels are year-relative, not absolute-vol labels.
