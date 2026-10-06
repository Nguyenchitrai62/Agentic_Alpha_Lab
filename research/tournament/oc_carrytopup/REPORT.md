# oc_carrytopup REPORT — delivery-week carry top-up (IDEAS3_20261006 idea 2)

Question: can an EXTRA spot + short pair (f = 0.125/coin), entered 7d
before each BTC/ETH quarterly delivery iff ann. basis >= 4 %/yr and held
to delivery, harvest residual premium on idle equity? Method frozen in
PLAN.md (one allocation row, no tuning). Repro:
`research/tournament/oc_carrytopup/{PLAN.md,analyze_carrytopup.py,results.json}`;
test `tests/test_oc_carrytopup.py`. 4h data only, one process.

## Why it fails (fee arithmetic, visible before the tables)

A 4 %/yr basis over ~6.8d locks a premium of only ~0.07-0.08 % of
allocated, while the assignment-fixed fee drag is 0.275 % (spot 0.1 % x2
+ futures 0.055 % + 0.02 %). Break-even needs ~16 %/yr late-week basis;
the max entered basis (36 % Binance, 18 % Bybit) still netted at most
+0.33 % alloc on a single pre-window trade. The base sleeve works
because ~90d of the same 4 %/yr locks ~1 % premium; 7d cannot.

## Per anchor year (grouped by ENTRY; ret_alloc = P&L per allocated unit)

Binance proxy (50 contracts -> 14 entered, 32 skipped, 4 no_overlap =
Dec-26/Mar-27 contracts whose 7d entries lie past the last spot bar,
0 incomplete). ALL entered top-ups are BTC (ETH never clears 4 %/yr in
the final 7d on either venue):

| year | n / sum_alloc | acct %/mo f=0.125 | worst MtM (alloc) |
|---|---|---|---|
| 2021-09-24 | 1 / -0.001716 | -0.0018 | -0.21% |
| 2022-09-24 | 1 / -0.001497 | -0.0016 | -0.29% |
| 2023-09-24 | 4 / -0.000510 | -0.0005 | -0.20% |
| 2024-09-24 | 2 / -0.001968 | -0.0021 | -0.31% |
| 2025-09-24 | 3 / -0.005518 | -0.0057 | -3.71% |

5y pooled (11 in-window trades, sum -0.011209; 3 pre-window +0.000118
excluded): -0.1401 % total = -0.0023 %/month (arith and geom). Years
positive: 0/5. Only 3 trades ever positive (max +0.33 % alloc,
pre-window Mar-21 BTC).

Bybit inverse (48 contracts -> 13 entered, 29 skipped, 4 no_overlap,
0 incomplete; coin-settlement convexity not modelled, as in bybitq):

| year | n / sum_alloc | acct %/mo f=0.125 | worst MtM (alloc) |
|---|---|---|---|
| 2021-09-24 | 1 / -0.000481 | -0.0005 | -0.20% |
| 2022-09-24 | 3 / -0.002820 | -0.0029 | -0.75% |
| 2023-09-24 | 4 / -0.001865 | -0.0019 | -0.38% |
| 2024-09-24 | 2 / -0.000171 | -0.0002 | -0.20% |
| 2025-09-24 | 2 / -0.002615 | -0.0027 | -2.75% |

5y pooled (12 in-window, sum -0.007952; 1 pre-window -0.001491
excluded): -0.0994 % total = -0.0017 %/month. Years positive: 0/5.
Worst MtM is small (account units x0.125: worst -0.46 % Binance 2025,
delivery-week basis blowout) — the sleeve is harmless to DD, it just
loses money.

## Stacked cash check (base f = 0.25 + top-up f = 0.125, per venue)

Base pairs reused verbatim (Binance: oc_cashcarry 33 trades; Bybit:
bybitq inverse series). Spot legs are bought with USDT cash; legs sized
f x mix equity at entry (oc_carrycombo convention), C_live(t) =
sum_open f*Eq(entry)/Eq(t); indexed C_idx(t) = 0.25*B + 0.125*U:

| venue | max C_idx (bar, B/U) | max C_live (bar) | UTA bar C_live | borrow? |
|---|---|---|---|---|
| Binance | 1.125 (2021-09-24, 4/1) | 1.1482 (2024-06-24) | 1.0892 | YES |
| Bybit inv | 1.125 (2021-12-24, 4/1) | 1.1486 (2024-06-24) | 1.0886 | YES |

During quarterly roll weeks the base sleeve alone already holds 4 pairs
(front + next per coin = 1.00 indexed); ANY add-on pushes spot cost
past the account (1.125 indexed, ~1.15 live) -> USDT must be borrowed
(interest unmodelled). Eq source: oc_kpi_g2/barsum_s0..s3 mean equity.

## Verdict

CLOSE (rule was USEFUL iff >= 4/5 years net > 0 on each venue AND no
borrow) — fails both legs: (a) net <= 0 after fees in 5/5 years on BOTH
venues (needs >= 4/5 positive on each), and (b) the stacked spot cost
needs USDT borrowing on both stacks. Direction closed: no follow-up
sizing/threshold work — a 7d window cannot out-earn the 0.275 % drag at
any defensible threshold, and roll-week cash is already full from the
base sleeve. (Post-hoc log: live cash formula corrected per PLAN.md
amendment 1; conclusion unchanged — indexed max alone already borrows.)
