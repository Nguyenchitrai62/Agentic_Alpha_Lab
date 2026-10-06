# oc_bidttl REPORT (2026-10-06)

## Setup

Exact oc_dipexit D0 replica (TP 1sg, close5 stop 4sg, 8sg backstop, timeout at
next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding) with
oc_b1deeper B1 sizes w = 1/(1+n_fill), majors x R2 depths 2.5..5.0, live
offsets 16..238 strict trade-through, 5 anchor years 2021-09-24..2025-09-24,
all four clock phases (4h grid from 2020-08-01 00:00 UTC + 0/1/2/3h).
TTL variant: live window cut to 16..135 (120 min; bid still unfilled at minute
136 cancelled, no replacement same bar); filled rungs unchanged. Both arms
pass through a v421-style G = 2.0 gross-cap walk per (phase, bar) ordered by
(f, k, coin), cut to room, skip when full (equity = 1 constant; open + new <=
G; D0 exits <= 240 so pools are per-bar independent; oc_rearm-exact).
PRIMARY = cap-adjusted wk*y sums; 4-phase means per year.

## Fidelity

n_candidates 22312 (= oc_placebo_dip ledger exactly); phase-0 uncapped base
raw sums 2.388052 / 0.182865 / 3.809764 / 2.579274 / 0.711509 = placebo ref to
1e-6. Cap binds hard in w units (equity 1): 22312 candidates -> 8945 base-kept
/ 4296 TTL-kept. Checksum 8f05bb705e65e2ca.

## Results per year (4-phase means, cap-adjusted wk*y)

| year | S_base | S_ttl | delta | DD_base | DD_ttl | W_base | W_ttl | lost n (win / sum) | extra n (sum) | sum>= | dd_ok |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 0.5069 | 0.3482 | -0.1587 | 0.3463 | 0.2764 | -0.2638 | -0.1999 | 869 (58.6% / +0.6348) | 0 (+0.0) | no | yes |
| 2022-09-24 | 0.2708 | 0.1472 | -0.1236 | 0.4639 | 0.4598 | -0.2432 | -0.2625 | 840 (64.8% / +0.4943) | 0 (+0.0) | no | yes |
| 2023-09-24 | 1.2960 | 0.6924 | -0.6036 | 0.2379 | 0.2261 | -0.1925 | -0.1794 | 1099 (69.2% / +2.4144) | 0 (+0.0) | no | yes |
| 2024-09-24 | 1.1702 | 0.7957 | -0.3745 | 0.2409 | 0.1428 | -0.1816 | -0.1270 | 938 (62.9% / +1.4981) | 0 (+0.0) | no | yes |
| 2025-09-24 | 0.0637 | -0.0148 | -0.0785 | 0.3105 | 0.3345 | -0.1648 | -0.1551 | 903 (59.1% / +0.3141) | 0 (+0.0) | no | no (+0.024) |

Full pooled path (all phases, cap-adjusted): base n=8945 sum=13.2304 DD=1.4857
win=67.4%; TTL n=4296 sum=7.8746 DD=1.1853 win=72.0%. 5y 4-phase-mean sum
delta dSum5y = -1.3389 (gate +0.273). Years sum>=base: 0/5; years DD not worse
by >1pp: 4/5.

## Notes

- Late fills (f >= 136) are the WINNERS every year (win 59-69%, positive net
  +0.31..+2.41): the thesis fails in the predicted clean way (IDEAS3#8:
  "fails cleanly if late fills are the winners").
- Extra fills from freed cap headroom are exactly 0 in all 5 years: TTL
  candidates are a strict subset of base and the cap walk on the shared
  prefix is identical, so no other coin's rung ever gains room.
- TTL win rate is higher (72.0% vs 67.4% pooled) but on ~half the fills and
  far lower sums; DD improves slightly in 4/5 years from lower exposure, yet
  fails the DD leg in 2025 (+0.024 > 0.01).

## Verdict

VERDICT: NOT PROMISING — 2-hour dip-bid TTL loses cap-adjusted 4-phase-mean sums in 0/5 years with 5y delta -1.339 (gate +0.273); late fills win 59-69% every year and freed cap enables zero extra fills.
