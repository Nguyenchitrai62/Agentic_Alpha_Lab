# oc_ddanat4p REPORT — where the 18.33 gate DD comes from (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Gate: R2B1D17BF (dips x1.7 inv-rule, budget 0.26x1.7, bear-book filter) 4-phase
reset metric from `v411/v411_runs.pkl` (yearly DD 12.42/16.23/**18.33**/8.26/12.81,
full-path 16.9 — reproduced to 0.05pp by `run_mix.py`, pkl-only). Phases 1-3
re-ran with the EXACT oc_ddanat17 replica (`run_phase.py`, shift only, one heavy
process at a time): all four phases bit-for-bit vs v411 (rel_diff 0.0; s=0
episodes identical to oc_ddanat17). Live 2021-09-24..2026-09-23(+shift); 1m read
to 2026-09-24 00:00 UTC. All five years are research data; findings need
prospective validation. Repro: `research/tournament/oc_ddanat4p/{PLAN.md,
run_mix.py,run_phase.py,make_results.py,results.json,mix_episodes.json,attrib_s0..s3.json}`.
Post-hoc changes (logged in results.json): close-trough extension + crash-bar
attribution window (11:00,16:00], because the max-DD pair is a 1-hour mark
artifact (mixed 4h closes move only 0.2% 11:00->12:00; the marked collapse prints
first, closes follow by 16:00).

## (1) Mixed-path episodes (reset-at-anchors chaining; per-phase own DD in window)
| episode (UTC) | mixed 4h / 1m DD | s0 | s1 | s2 | s3 | synchronous? |
|---|---|---|---|---|---|---|
| 2023-04-17 -> 2023-06-15 | 15.4 / 16.2 | 16.5 | 14.5 | 17.6 | 17.1 | yes (all >85% of mixed) |
| 2023-07-14 -> 2023-10-02 | 13.3 / 13.8 | 13.9 | 15.7 | 10.6 | 14.3 | mostly (s2 lighter) |
| **2024-01-03 11:00 -> 16:00 (gate 18.33)** | 16.5 / **18.3** | **5.5** | **20.4** | **24.9** | **24.2** | **NO — s0 sits out, s1-3 crash** |
| 2025-10-07 -> 2025-10-17 | 11.7 / 12.8 | 7.2 | 17.9 | 13.6 | 13.6 | partly (s0 light) |

The gate number is the 2024-01-03 BTC flash-crash (~-10% in hours): a ONE-BAR
-19/-24/-23% close-to-close loss on phases 1-3 (bars ending 13:00/14:00/15:00)
vs -0.7% on s0 (bars 12:00/16:00: book -1.50, dip +0.02). No liquidation
(liq=0 all phases). oc_ddanat17's s=0 anatomy misses the gate driver entirely.

## (2) Crash-window attribution per phase, bars ending (11:00,16:00] (% of window-start equity)
| phase | bars | book long | book short | dip | of which rung_sl / rung_tp / timeout |
|---|---|---|---|---|---|
| s0 | 12:00,16:00 | -1.50 | 0.00 | +0.02 | sl -1.52 / tp +1.36 / timeout +0.18 (5 small XRP stops, 28 exits) |
| s1 | 13:00 | -1.49 | 0.00 | -17.47 | sl -18.28 / tp +2.14 (18 stops in ONE bar) |
| s2 | 14:00 | -2.41 | 0.00 | -21.70 | sl -22.13 / tp +0.70 (22 stops in ONE bar) |
| s3 | 15:00 | -2.27 | 0.00 | -21.01 | sl -21.43 / tp +0.41 (22 stops in ONE bar) |

Dip per coin (crash bar): s1 BTC -6.97 / ETH -4.46 / SOL -3.14 / XRP -1.87 /
BNB +0.30; s2 BTC -7.13 / ETH -4.64 / XRP -4.24 / SOL -3.50 / BNB -1.92; s3
BTC -7.33 / ETH -4.99 / BNB -3.26 / XRP -2.79 / SOL -2.65. BTC-led MULTI-coin
stop cascade at x1.7 size (worst single rungs -1.5..-2.2%; the loss is breadth:
18-22 stops per bar, not one rung) — unlike oc_ddanat17's single-coin (SOL/XRP)
s=0 cascades. Book shorts are exactly 0.0 in every crash bar (books long/flat only).

## (3) What a rule must cut + rejected levers
To bring 18.33 below 15 needs >=3.34pp of mixed equity = >=13.4pp summed over
the s1-3 crash bars, i.e. cut ~25% of their -60.2 combined dip loss (e.g. halve
in-crash rung stops net of TPs, or cap single-bar dip loss per phase at
~-12/-13%; dips x~1.0 instead of x1.7 would about do it, at the cost of the
return the x1.7 buys). The book has almost nothing to cut (shorts 0.0).
Rejected levers that touched it: cooldown v417-C TESTED on this strategy:
18.33->18.45, full 16.9->17.42 (stops cascade WITHIN one bar — 18-22 in the same
crash minutes — a next-bar fill block cannot touch open rungs, and it eats the
+0.4/+0.7/+2.1 TP offsets; transfer false); XRP-stop v417-X: 18.33->18.37
(XRP ~1/5 of crash dip; a -10% flash blows through 5.5σ); bear book BF is
already IN the gate (shorts 0.0, halved longs still -1.5..-2.4; zeroing longs
saves ~2pp of 18.33); wider stops (v388 S5/S6) hold losers longer into a flash
past 6σ — wrong direction; governor (v110/v141, 90-day own-DD, 2-bar lag):
pre-crash DD~0 so g=1 at the crash bar — can only de-risk AFTER the first -20%
bar. A rule that works must limit same-bar dip inventory/loss per phase
(per-phase sleeve circuit-breaker on open-rung marked loss, or a hard concurrent-dip-gross cap per coin).

## Verdict
VERDICT: The 18.33 gate DD is the 2024-01-03 flash crash, a one-bar BTC-led multi-coin dip stop cascade (-17/-22/-21% dip) on phases 1-3 while phase 0 lost -1.5% — asynchronous across phases, book-neutral (shorts 0.0), and untouched by every tested lever (cooldown, XRP stop, bear filter, wider stops, governor); only a same-bar per-phase dip-loss cap (~-12%) or ~25% less in-crash dip exposure brings it below 15%.
