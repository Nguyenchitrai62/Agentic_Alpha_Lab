# oc_calendar REPORT — near-vs-far quarterly roll-down spread (IDEAS3 #4)

Rule (frozen in PLAN.md, one post-hoc entry-timing correction logged there,
CORR-1): at each oc_cashcarry roll date, per coin, if annualised
basis(far) - annualised basis(near) >= 0.02 (2 pp/yr), long near / short far
in equal USD notional f = 0.125, hold to the near delivery (near settles via
delivery, far closed at market in the same hour = same delivery bar); fees
taker 0.00055 per leg per side + delivery 0.0002 (drag 0.00185 per allocated
unit); no funding. Two venues, same rule: BINANCE proxy (`um_*` quarterlies
+ Binance spot 4h, delivery 08:00 UTC on code date) and BYBIT inverse
(`inv_*` quarterlies + Bybit spot 4h grid, delivery = inventory
deliveryTime). Repro: `research/tournament/oc_calendar/{PLAN.md,
analyze_calendar.py,results.json}`; test `tests/test_oc_calendar.py`.
4h/hourly data only, one process.

## Per anchor year (grouped by ENTRY; sum_alloc = net return on allocated)

Binance proxy: 48 pairs seen, 48 NO_FAR_AT_ROLL, 0 considered, 0 entered,
0 incomplete. The far quarterly is never listed at the roll date (Binance
lists the next quarterly only ~3 months before its own delivery, i.e. about
a week AFTER the near contract's roll date), so the spread as specified can
never be entered on the Binance proxy chain.

| year | considered / entered | sum_alloc | worst MtM (alloc) | acct %/mo f=0.125 | max spread seen |
|---|---|---|---|---|---|
| 2021-09-24 | 0 / 0 | 0.0 | None | 0.0 | None (no far at roll) |
| 2022-09-24 | 0 / 0 | 0.0 | None | 0.0 | None (no far at roll) |
| 2023-09-24 | 0 / 0 | 0.0 | None | 0.0 | None (no far at roll) |
| 2024-09-24 | 0 / 0 | 0.0 | None | 0.0 | None (no far at roll) |
| 2025-09-24 | 0 / 0 | 0.0 | None | 0.0 | None (no far at roll) |

5-year pooled (Binance): 0 trades, sum 0.0 on allocated, 0.0 %/mo at
f = 0.125. Positive years: 0/5.

Bybit inverse: 44 pairs seen (42 considered, 2 incomplete past the last spot
bar, 0 no_far). The curve is tradeable but never steep enough: the largest
far-minus-near spread in any year is 0.012008 (1.2 pp, 2024-09-24), below
the 0.02 gate, so 0 spreads entered in all five years.

| year | considered / entered | sum_alloc | worst MtM (alloc) | acct %/mo f=0.125 | max spread seen |
|---|---|---|---|---|---|
| 2021-09-24 | 8 / 0 | 0.0 | None | 0.0 | 0.009816 |
| 2022-09-24 | 8 / 0 | 0.0 | None | 0.0 | 0.006428 |
| 2023-09-24 | 8 / 0 | 0.0 | None | 0.0 | 0.010815 |
| 2024-09-24 | 8 / 0 | 0.0 | None | 0.0 | 0.012008 |
| 2025-09-24 | 6 / 0 | 0.0 | None | 0.0 | 0.010963 |

5-year pooled (Bybit): 0 trades, sum 0.0 on allocated, 0.0 %/mo at
f = 0.125. Positive years: 0/5.

## Correlation with the base carry returns

Base series: `oc_cashcarry/results.json` (Binance, 5y sum 0.5234 on
allocated) and `bybitq/results_bybit_carry.json` inverse (Bybit, 5y sum
0.4973). Spread sums are identically 0.0 on both venues, so both Pearson
rows are undefined (null): per-year-sums r = null on both venues (spread
series has zero variance, n = 5); matched same-delivery per-trade r = null,
n_matched = 0 on both venues. There is nothing to correlate with: the
spread sleeve is flat zero while the base carry earned its +0.20 %/mo.

## Verdict

CLOSE — 0/5 positive years on Binance (structurally unenterable: far leg
never listed at the roll date) and 0/5 on Bybit (curve never reaches the
2 pp/yr gate; best 1.2 pp). The verdict rule requires net > 0 in >= 4/5
years on BOTH venues. This is the clean fail IDEA 4 anticipated: no spread
edge exists at these tenors/gates on either quarterly chain. Do not deploy;
do not re-tune the threshold on this data (that would be fitting to the
test years). If the direction is ever revisited, it needs a different
tenor (e.g. Bybit weekly-dated linears, a new pre-registered study), not a
lower gate on these quarterlies.
