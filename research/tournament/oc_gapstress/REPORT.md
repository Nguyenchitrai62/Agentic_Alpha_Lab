# oc_gapstress REPORT — instantaneous-gap stress on R2B1D17BF (2026-10-06; PLAN pre-registered, corrections C1-C4 logged in PLAN.md)

STRESS / reporting task (no selection rule, no verdict). Question: oc_kpi
measured R2B1D17BF's open exposure (dip rungs up to ~6.4x equity notional, book
up to ~1.3x). What does an instantaneous GAP do — an exchange outage or a flash
move that jumps straight through every stop-loss and the 8-sigma backstop?

## What was done (plain language)
From the oc_kpi shift replicas (`events_s0..s3`, `barsum_s0..s3`) we rebuilt,
per phase, every open position minute-by-minute: the book's signed quantity per
coin (fills/adds/reduces close out exactly on stop/TP/close; verified: zero
fills from a non-flat state, zero over-reductions, zero unpaired rung exits)
and every open dip rung (FIFO, long-only), marked with hourly closes and
expressed as fractions of current equity. Check: rebuilt book gross matches
barsum's recorded gross to a median 0.0006-0.0012 (max 0.07-0.16, from hourly
vs minute-0 mark timing). Samples tile the whole 5 years: every minute where
anything changed plus every 4h bar end (~17.5-19.3k open-state samples per
phase, 63.8k for the mix), minute-weighted so shares are exact shares of time.
At each sample we applied instant DOWN gaps of 5/10/20% to all five majors at
once and to each coin alone: everything open gaps, no stop helps, all of it is
then closed at the crashed price (0.055% taker fee). Loss is reported in % of
that minute's equity (positive = loss; over 100% = ruin — in reality
liquidation would strike first). Caps rerun the same minutes with dip notional
scaled down proportionally whenever it exceeds 3x / 2x equity. All five years
are research data; this needs prospective validation like everything else.
Repro: `research/tournament/oc_gapstress/{PLAN.md,compute_gapstress.py,
results.json}`; test `tests/test_tournament_oc_gapstress.py`.

Two engine conventions the deployment doc should know: (1) barsum's `t` is the
holding-bar START and its qty/open/equity are END-of-bar state; (2) barsum's
gross divides by indexed equity but omits the x bar-start-equity factor, so it
UNDERSTATES true current-equity exposure by that factor (1x early, up to ~58x
at the end). True maxima below are up to ~2.1x book / ~6.2x dip / ~7.1x
combined, vs barsum's 1.31 / ~6.3-weight-sum convention in oc_kpi.

## All-coin instant gap: loss distribution (% of equity, minute-weighted)

| scope | gap | median | p99 | max | median | p99 | max | median | p99 | max |
|---|---|---|---|---|---|---|---|---|---|
| | | uncapped | | | dip cap 3x | | | dip cap 2x | | |
| phase s0 | -5% | 0.42 | 6.68 | 35.9 | 0.42 | 6.68 | 23.3 | 0.42 | 6.68 | 18.7 |
| phase s0 | -10% | 0.83 | 13.28 | 71.5 | 0.83 | 13.28 | 46.3 | 0.83 | 13.28 | 37.1 |
| phase s0 | -20% | 1.66 | 26.4 | 142.5 | — | — | 92.4 | — | — | 74.1 |
| phase s1 | -10% | 1.04 | 14.53 | 57.3 | 1.04 | 14.53 | 38.5 | 1.04 | 14.53 | 33.3 |
| phase s2 | -10% | 0.83 | 13.52 | 56.2 | 0.83 | 13.52 | 40.0 | 0.83 | 13.52 | 36.1 |
| phase s3 | -10% | 0.91 | 13.85 | 69.3 | 0.91 | 13.85 | 41.3 | 0.91 | 13.85 | 35.4 |
| 4-phase mix | -5% | 0.43 | 6.63 | 29.3 | 0.43 | 6.63 | 19.7 | 0.43 | 6.63 | 16.8 |
| 4-phase mix | -10% | 0.85 | 13.19 | 58.3 | 0.85 | 13.19 | 39.1 | 0.85 | 13.19 | 33.5 |
| 4-phase mix | -20% | 1.70 | 26.3 | 116.3 | — | — | 78.0 | — | — | 66.8 |

Reading: a simultaneous -10% flash crash on a typical minute costs under 1% of
equity; 1% of minutes cost more than ~13%; the worst minutes (all dip ladders
full at once, e.g. 2025-08-14 and 2026-08-22) cost 57-71% of one phase's equity
and 58% of the mixed book. A -20% gap ruins the worst minute (>100%). Capping
dip notional at 3x/2x barely moves the median or p99 (the tail is thin) but
cuts the worst minute roughly in proportion (69 -> 41 -> 35% on s3).

## How often would a -10% all-coin gap hurt badly?

| scope | minutes with loss > 20% (share of open min / share of ALL live min) | loss > 50% |
|---|---|---|
| phase s0 | 0.119% / 0.112% (~49 h in 5 y) | a few minutes (2e-6 of live) |
| phase s1 | 0.301% / 0.252% (~110 h in 5 y) | none |
| phase s2 | 0.131% / 0.116% (~51 h in 5 y) | a few minutes (2e-6 of live) |
| phase s3 | 0.124% / 0.105% (~46 h in 5 y) | a few minutes (2e-6 of live) |
| 4-phase mix | 0.062% / 0.062% (~27 h in 5 y) | ~1e-6 of live (a couple of minutes) |

Caps do not change these shares (the >20% minutes sit below 3x dip; only the
extreme tip above 50% is shaved).

## Worst 10 minutes for a -10% all-coin gap (loss%, gross/dip/book x equity)

phase s0: 2024-02-28 17:31 71.5 (7.11/6.17/0.94); 2026-08-22 05:10 65.1
(6.48/5.66/0.82); 2026-08-22 05:11 61.9; 2025-08-14 12:34 60.2
(5.99/5.43/0.56); 2025-09-25 17:57 46.3; 2025-09-25 18:19 46.1; 2025-08-14
12:35 45.6; 2025-09-25 18:20 45.2; 2022-08-19 06:38 44.4 (4.42/4.42/0.0);
2023-04-19 08:22 44.2.

phase s1: 2025-08-14 12:34 57.3 (5.70/5.46/0.24); 2024-02-28 17:31 49.7;
2025-08-14 12:35 49.4; 2024-03-05 19:39 40.2; 2023-04-19 08:22 39.9; 2024-03-05
19:53 39.9; 19:41 39.6; 19:38 39.1; 2023-04-19 08:11 38.9; 2024-03-05 19:54 38.7.

phase s2: 2025-08-14 12:35 56.2 (5.59/5.13/0.46); 12:34 53.5; 2023-04-19 08:22
52.6 (5.24/4.52/0.72); 08:11 51.2; 2022-08-19 06:38 49.6; 2023-04-19 08:23 48.9;
2025-08-14 12:36 47.4; 2023-04-19 08:21 46.7; 08:34 45.3; 2025-08-14 12:41 45.0.

phase s3: 2026-08-22 05:11 69.3 (6.90/5.79/1.11); 05:10 68.7; 2025-08-14 12:34
63.0 (6.27/5.81/0.46); 12:35 60.7; 12:36 53.0; 12:37 48.4; 2024-06-07 18:04
43.2; 2025-09-22 06:02 40.3; 2025-08-14 12:40 39.3; 2024-06-07 18:01 39.2.

4-phase mix: 2025-08-14 12:34 58.3 (5.80/5.34/0.47); 2026-08-22 05:10 50.4;
2025-08-14 12:35 49.8; 2026-08-22 05:11 46.9; 2024-02-28 17:31 45.7; 2023-04-19
08:22 43.8; 08:23 41.2; 2022-08-19 06:38 40.8; 2025-08-14 12:36 39.9; 2025-09-25
17:58 39.1. (Full rows with equity in results.json.)

Every worst minute is a calm-market dip-ladder pile-up (dip 3-6x, book under
1.7x), never a book-only event: the book alone peaks at 1.9-2.1x and its worst
solo minutes stay well below the dip-driven ones.

## One coin gaps -10% (max over 5 y, % of equity)

| scope | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| phase s0 | 17.0 | 19.3 | 18.9 | 22.6 | 24.0 |
| phase s1 | 17.5 | 19.1 | 15.1 | 19.6 | 18.8 |
| phase s2 | 21.5 | 16.3 | 18.9 | 21.6 | 27.2 |
| phase s3 | 16.6 | 15.6 | 18.7 | 21.6 | 20.4 |
| 4-phase mix (median/p99/max) | 0.54/6.69/13.9 | 0.0/3.06/11.8 | 0.0/2.14/13.8 | 0.0/4.75/17.7 | 0.0/2.33/17.5 |

A single-coin -10% gap never costs more than ~27% of a phase (17.7% of the
mix) — diversification across coins works; the danger is only the all-coin,
all-ladder-full coincidence.

## Exposure maxima reached (true fractions of current equity)

Phase book gross max 1.94-2.12, dip max 5.13-6.17, combined 5.59-7.11; mix
coverage 98.9% of minutes with something open (per phase 83.5-93.5%).
Positions are open nearly all the time, so there is almost nowhere to hide —
but the typical minute's net exposure is small (median gap loss < 1%).

Summary: R2B1D17BF shrugs off a simultaneous -10% gap on a normal minute
(<1% equity) and survives 99% of minutes with <13-15% damage, but the rare
minutes when every dip ladder is full would cost 45-70% of equity (58% on the
mixed book, ruin at -20%); capping dip notional at 2-3x halves the worst
minute without touching everyday behavior, and single-coin gaps are never
fatal on their own.
