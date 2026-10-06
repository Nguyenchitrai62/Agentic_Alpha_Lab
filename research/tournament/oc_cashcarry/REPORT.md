# oc_cashcarry REPORT — locked cash-and-carry on idle equity (BTC/ETH quarterlies)

Question: can idle equity earn a locked cash-and-carry basis without hurting
the BOT? Method is frozen in PLAN.md (written before outcomes): one entry per
quarterly contract (next-quarter when front has <= 7d left, else first
availability), ENTER iff annualised basis ln(F/S)*365/DTE >= 4 %/yr, long spot
+ short quarterly in equal notional (f per coin, rows 0.25/0.50), hold to
delivery (settlement = spot 4h close of the delivery bar). Fees: spot 0.1% /
side, futures 0.055% entry + 0.02% delivery (drag 0.275% of allocated).
Delivery futures pay NO funding, so the AGENTS.md perp-funding rule is
irrelevant here — the basis is locked at entry. Coins: BTC + ETH only (the
only majors with USDT-margined quarterly delivery files in
`data/raw/qbasis_20261003`; SOL quarterlies start 2024-09, BNB/XRP are
coin-margined `cm_*`, unused). Repro:
`research/tournament/oc_cashcarry/{PLAN.md,analyze_cashcarry.py,results.json}`;
test `tests/test_oc_cashcarry.py`. 4h data only, one process.

## Trades

50 contracts seen (25 BTC + 25 ETH expiries, 2021-03 .. 2027-03) -> 33 entered,
13 skipped (basis < 4 %), 2 incomplete (deliveries 2026-12/2027-03, past the
last spot bar; excluded, no P&L imputed). All 33 entered trades are net
positive (min +0.18% on allocated; the locked gross of a positive-basis pair
held to delivery is mathematically > 0, minus the 0.275% fee drag).
8 pre-window trades (entered before 2021-09-24, sum +0.292 on allocated) are
excluded from the pooled 5-year stats (in results.json separately).

## Per anchor year (grouped by ENTRY; ret_alloc = P&L per allocated unit)

| year | BTC n / mean basis / sum | ETH n / mean basis / sum | year sum | worst MtM (alloc) | acct +%/mo f=0.25 | acct +%/mo f=0.50 |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2 / 8.9% / 0.0261 | 2 / 8.0% / 0.0209 | 0.0470 | -1.01% | 0.098 | 0.196 |
| 2022-09-24 | 3 / 5.6% / 0.0424 | 1 / 5.7% / 0.0105 | 0.0528 | -0.71% | 0.110 | 0.220 |
| 2023-09-24 | 4 / 13.3% / 0.1579 | 4 / 12.7% / 0.1381 | 0.2960 | -2.65% | 0.617 | 1.233 |
| 2024-09-24 | 4 / 7.4% / 0.0638 | 4 / 7.4% / 0.0581 | 0.1219 | -0.39% | 0.254 | 0.508 |
| 2025-09-24 | 1 / 4.2% / 0.0058 | 0 (all 5 skipped, basis < 4%) | 0.0058 | -2.17% | 0.012 | 0.024 |

5-year pooled (25 in-window trades, sum 0.5234 on allocated): at f = 0.25 the
sleeve adds +13.09% over 5 years = +0.218 %/month arithmetic (+0.213 %/month
geometric); at f = 0.50 it adds +26.17% = +0.436 %/month arithmetic
(+0.416 %/month geometric). The filter idles correctly: in the most recent
year only 1 of 6 opportunities cleared 4 %/yr, so the sleeve contributed
~+0.01 %/month — no forced risk when there is no premium.

## Drawdown impact (basis widening while open)

Worst 4h-close MtM per year on allocated capital: -1.01 / -0.71 / -2.65 /
-0.39 / -2.17%. In account units that is x f: at f = 0.25 the worst is -0.66%
(2023), at f = 0.50 it is -1.33% (2023). Small next to the BOT's own DD
(~17%): the sleeve cannot add more than ~0.7% (f = 0.25) account DD even if
its worst widening coincided with the BOT's worst minute.

## Margin interaction (Bybit unified cross, 5x, Hedge Mode)

Haircuts 5% BTC / 10% ETH are an ASSUMPTION (no Bybit spot-haircut table was
found in this repo). Short quarterly needs IM at 5x on its mark; spot needs
no IM (it is collateral). Bound checked at EVERY 4h close 2021-09-24 ..
2026-09-23 on stored phase data (`oc_kpi_g2/barsum_s0..s3`, book_gross +
equity; `v421_runs.pkl` present and noted in results.json): BOT gross <=
book_gross(t) + 2.0 dip cap (oc_margin measured mix max 3.41, per-phase max
3.78), carry short added time-varying, both-coins-active worst case:

| f | worst IM/equity s0 | s1 | s2 | s3 | blocked 4h closes |
|---|---|---|---|---|---|
| 0.25 | 0.53 | 0.53 | 0.57 | 0.67 | 0 (all phases) |
| 0.50 | 0.55 | 0.55 | 0.60 | 0.72 | 0 (all phases) |

Zero blocked closes at either allocation (limit 0.95; worst minute
2023-10-24, still >= 28% free). The pair is delta-hedged (spot long +
futures short, net ~= 0 ex-basis), so a uniform gap moves both legs together
and the incremental gap loss is only the basis widening above; extra
maintenance is 0.5% x carry gross (~0.5-1.0% of equity). The BOT's free margin
is the funding source: median ~93% of equity is free (oc_margin), so the
f = 0.25/0.50 spot purchases come from idle cash, not from BOT margin.

## Verdict

USEFUL ADD-ON: YES — small, honest, nearly risk-free yield, not a
goal-changer. Expected add +0.21 %/month geometric at f = 0.25 (+0.42 at
f = 0.50), worst incremental account DD about -0.7% (-1.3% at f = 0.50), zero
margin blocks on every 4h close of all 5 years. Honest context: ~57% of the
5-year gain came from 2023's high-basis regime, and the most recent year paid
~+0.01 %/month (filter stayed out) — this sleeve harvests idle-equity premium
when it exists (roughly +0.1 to +0.6 %/month in normal years) and idles
otherwise. It closes ~4-8% of the gap to the 5 %/month BOT goal, at no
measurable cost to DD or margin. Suggested deployment: f = 0.25 per coin
(spot + short each), entered exactly by the PLAN.md roll rule; needs the same
prospective paper check as everything else (venue is Binance data, live is
Bybit; delivery/settlement mechanics must be confirmed on the live venue).
