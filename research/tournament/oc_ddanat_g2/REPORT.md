# oc_ddanat_g2 REPORT — where the G2 16.91 gate DD comes from (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Gate: R2B1D17BFG2 (D17BF + dip gross cap G = 2.0) 4-phase reset metric from
`v421/v421_runs.pkl` (yearly DD 10.86/**16.91**/15.81/8.27/12.90, full-path
16.82 — reproduced to 0.05pp by `run_mix.py`, pkl-only). Phases 0-3 re-ran
with the EXACT oc_kpi_g2 wiring (`run_phase.py`, +attrib collection, one heavy
process at a time): all four phases bit-for-bit vs v421 (rel_diff 0.0) and
event-identical vs oc_kpi_g2 (20026/19839/20313/18781 events). Live
2021-09-24..2026-09-23(+shift); 1m read to 2026-09-24 00:00 UTC. All five years
are research data; findings need prospective validation. Repro:
`research/tournament/oc_ddanat_g2/{PLAN.md,run_mix.py,run_phase.py,
make_results.py,results.json,mix_episodes.json,attrib_s0..s3.json}`. No
post-hoc changes (the max-DD pair is a 2-month grind, not a 1h mark artifact;
close trough 06-15 10:00 shown for reference only).

## (1) Mixed-path episodes, reset-chained ranking (per-phase own DD in window)
| episode (UTC) | mixed 4h / 1m DD | s0 | s1 | s2 | s3 | synchronous? |
|---|---|---|---|---|---|---|
| 2023-04-17 -> 2023-06-15 (**gate 16.91**; year-1 reset mark trough 06-14 21:00, close trough 06-15 10:00: 15.3/16.2 close) | 16.2 / **16.9** | 16.9 | 15.6 | 17.4 | 18.0 | **yes** (all >92% of mixed, troughs within 3h) |
| 2023-07-14 -> 2023-10-02 | 13.4 / 13.9 | 14.4 | 15.4 | 10.6 | 14.6 | mostly (s2 lighter) |
| 2024-01-03 11:00 -> 16:00 (flash crash) | 14.1 / 15.8 | 5.5 | 18.9 | 19.8 | 20.5 | NO — s0 sits out, s1-3 crash |
| 2024-07-05 -> 2024-07-16 | 12.3 / 12.6 | 13.1 | 13.8 | 13.8 | 4.5 | partly (s3 sits out) |

Full-path continuous mix gives the same four (16.05/16.82, 13.39/13.80,
12.81/14.71, 12.58/12.87). The gate episode is a **slow grind** (~59 days,
~354 phase-bars), not a one-bar event like 2024-01-03 for D17BF. No
liquidation (liq=0 all phases).

## (2) Episode attribution per phase, bars ending (peak, trough] (% of window-start equity; attrib_sum vs own eq-change in brackets)
Gate 2023-04-17 -> 2023-06-15 (book long + dip ~50/50; shorts OFFSET the loss):

| phase | book long | book short | dip (sl / timeout / tp) | attrib_sum [eq_chg] |
|---|---|---|---|---|
| s0 | -9.26 | +2.69 | -9.86 (-12.37 / -9.15 / +11.66) | -16.43 [-15.78] |
| s1 | -9.40 | +1.92 | -8.53 (-10.58 / -11.40 / +13.45) | -16.01 [-15.61] |
| s2 | -10.61 | +1.73 | -7.40 (-10.80 / -6.52 / +9.92) | -16.29 [-15.83] |
| s3 | -9.23 | +0.45 | -9.39 (-15.01 / -5.18 / +10.80) | -18.18 [-17.42] |

Dip per coin (gate window, book/dip): s0 BNB -3.77/-5.68, ETH -3.05/-2.89,
BTC -2.49/-0.48, SOL +1.59/-0.56, XRP +1.15/-0.26; s1 BNB -4.33/-6.59, ETH
-2.40/-2.66; s2 BNB -6.00/-4.28; s3 BNB -5.94/-6.97, BTC -2.09/-2.94. BNB-led,
broad BTC/ETH participation; dip loss is stops AND timeouts (-5..-11 timeout:
rungs that never recovered in the grind — the opposite of a one-bar cascade),
partly offset by +10..+13 TPs. Book shorts are POSITIVE on all phases
(+0.45..+2.69, +6.8 summed): the bear-book filter already helps here.

Next three (summary; full per-coin/exit tables in results.json):
- 2023-07-14 -> 2023-10-02 (slow chop): s0 L -5.30/S -5.17/dip -4.45;
  s1 L -7.43/S -1.97/dip -5.80 (ETH dip -7.28); s2 L -2.39/S -7.72/dip +0.29;
  s3 L -4.13/S -8.23/dip -2.39. Book long AND short both bleed (whipsaw).
- 2024-01-03 11:00 -> 16:00 (ONE-BAR flash crash, G2 cap helped: mixed 15.81
  vs BF 18.33): s0 L -1.50/S 0.0/dip +0.02 (sits out); s1 L -1.49/dip -16.75
  (sl -17.04, BTC dip -6.87); s2 L -2.41/dip -16.65 (sl -16.75); s3 L -2.27/
  dip -17.28 (sl -17.28, all stops, zero TP offset). BTC-led multi-coin stop
  cascade, 1 bar per phase — same mechanism as D17BF's 18.33, cut ~2.5pp by
  the G=2.0 cap but still the second-deepest G2 episode on s1-3.
- 2024-07-05 -> 2024-07-16 (11-day short squeeze grind): s0 S -11.59
  (XRP book -4.35, SOL -3.07)/dip -1.94; s1 S -11.51/dip -2.21; s2 S -11.09/
  dip -2.78; s3 S -4.54/dip +0.05 (sits out). Book SHORTS are the loss.

## (3) What a rule must cut to bring G2 below 15
Cut >= 1.91pp of mixed reset-path equity in the 2023-04-17 -> 2023-06-15
window = >= 7.64pp summed over the four phase windows (~11% of their -66.9
combined loss, e.g. cut ~1/4 of the dip stop+timeout net of TPs, or ~1/4 of
the -38.5 summed book-long loss, or skip ~40 bars of the BNB book/dip bleed).
Book shorts already offset +6.8 summed and have nothing to cut; the dip TP
offset (+10..+13 per phase) must be preserved. A same-bar dip-loss cap (the
fix for the 2024-01-03 cascade) does NOT touch the gate: the gate is a 59-day
book-long + dip-timeout grind, synchronous across all four phases, with no
single bar, coin, or exit kind holding the 1.91pp alone.

## Verdict
VERDICT: The G2 16.91 gate DD is the synchronous 2023-04-17 -> 2023-06-15 slow
grind (book longs ~-9..-11 plus dip stops+timeouts net of TPs ~-7..-10 per
phase, BNB-led, shorts offsetting), not a one-bar crash; bringing it below 15
needs ~11% of that window's combined loss cut from book-long or dip-hold
exposure, while the leftover one-bar 2024-01-03 cascade (15.81) is already
2.5pp smaller than BF thanks to the G=2.0 cap.
