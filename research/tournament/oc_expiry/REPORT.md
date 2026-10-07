# oc_expiry REPORT: Deribit options-expiry calendar vs dip fills + book P&L

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
outcome y1.0. Anchor years start each 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Expiries = last Friday of month 08:00 UTC
(68 expiries, 22 quarterly; pure calendar, zero leakage). Windows: WEEK
[Mon 00:00, Fri 08:00), PRE24 [E-24h, E), POST24 [E, E+24h). Book = rebuilt
forward_v205.research_books_d2 x next-4h-bar open returns, gross, no costs
(2190 bars/year; bar assigned by its open T).

## Verdict

NOT_PROMISING: WEEK dip spread (inside - outside y1.0) signs are 3+/2-
across the 5 years and LOYO passes only 3/5. No rule proposed.

## Tables

Dip mean y1.0, bps [inside n / outside n]; spread = in - out:
year   WEEK in/out/spread        PRE24 spread (n_in)      POST24 spread (n_in)
21-22  +23.4/+40.1/-16.6 (114)  n/a (<30)                -79.8 (51)
22-23  +40.5/-1.9/+42.3 (139)   n/a (<30)                n/a (<30)
23-24  +29.4/+41.1/-11.7 (164)  n/a (<30)                n/a (<30)
24-25  +63.7/+35.6/+28.2 (194)  -48.2 (30)               n/a (<30)
25-26  +24.5/+11.8/+12.7 (148)  +33.6 (84)               n/a (<30)
sign   3/5 (+) -> FAIL                              (PRE/POST too thin to judge)

LOYO WEEK spread (train = other 4y pooled; pass iff same non-zero sign):
held-out 21-22 FAIL / 22-23 pass / 23-24 FAIL / 24-25 pass / 25-26 pass
-> 3/5 -> FAIL.

Book gross u per 4h bar, bps [spread in-out; sums]:
year   WEEK spread (sum_in/sum_out)   PRE24 spread     POST24 spread
21-22  -0.69 (249/2956)               +7.66            +0.92
22-23  -2.96 (-339/3523)              -8.97            +2.15
23-24  -0.62 (654/5099)               -11.54           -0.34
24-25  -3.46 (-111/5828)              -3.11            +5.32
25-26  -2.90 (-78/4983)               -5.28            +1.29
Book WEEK spread is negative in 5/5 but tiny (~1-3 bps/bar vs ~4-8 bps
round-trip cost scale; descriptive only, not in the rule).

Worst dip-fill day per year, bps (sums over inside vs outside fills):
21-22 in -2155 / out -4300; 22-23 in -3317 / out -19236;
23-24 in -416 / out -4963; 24-25 in -707 / out -5070; 25-26 in -1475 / out -10180.
The worst days fall outside expiry weeks every year (fewer inside fills also
contribute; descriptive only).

Quarterly vs monthly WEEK split, pooled 5y (descriptive): quarterly-week
fills +72.7 bps (n=191) vs rest +25.7 -> spread +47.0; monthly-only weeks
+26.8 (n=568) vs rest +25.6 -> spread +1.2. The quarterly gap rests on 191
fills with no per-year consistency requirement and is not rule-grade.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, windows, or the decision
   rule. Only addition after the run: quarterly/monthly pooled split and the
   book/worst-day descriptives already listed in PLAN.md.
2. PRE24/POST24 dip windows are structurally thin (24h x 12 expiries/year x
   ~5 fills/day -> often < 30 inside fills -> null/FAIL by construction);
   only WEEK (114-194 inside fills/year, 11.5-19.6% share) is rule-grade.
3. Spreads mix signs with economically large magnitudes (+42/-17 bps vs
   ~4-8 bps costs) — the calendar does not separate dip outcomes stably.
4. In-sample walk-forward style over research data; no prospective claim.

## One-line verdict

NOT_PROMISING: expiry-week dip-fill spreads flip sign across years (3+/2-,
LOYO 3/5) and the 24h windows are too thin to judge — no expiry rule proposed.
