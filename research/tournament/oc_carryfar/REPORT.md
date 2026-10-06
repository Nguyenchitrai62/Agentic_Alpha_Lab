# oc_carryfar REPORT — FAR tenor (second-next quarterly at the same roll times)

Question: does entering the SECOND-next quarterly (~6 mo to delivery) at the
same roll times beat the base next-quarterly rule? Method frozen in PLAN.md
(written first): same 7-day roll times E_k, same 4 %/yr entry threshold on
the FAR contract's own annualised basis, same hold-to-delivery, same fees
(spot 0.1 %/side, futures 0.055 % entry + 0.02 % delivery), same sizing
(f per open pair, rows 0.25/0.50). Repro:
`research/tournament/oc_carryfar/{PLAN.md,analyze_carryfar.py,results.json}`;
test `tests/test_oc_carryfar.py`. 4h data only, one process.
Base recomputed in-script and matches the frozen results bit-for-bit
(Binance pooled 0.523436, Bybit-inverse pooled 0.497293).

## Per anchor year — Binance proxy (um_ delivery quarterlies)

| year | base n / basis / DTE / sum | far n / basis / DTE / sum | diff (far-base) | worst MtM alloc base / far | max pairs base / far | acct +%/mo f=0.25 base / far |
|---|---|---|---|---|---|---|
| 2021-09-24 | 4 / 8.4% / 92.5d / 0.0470 | 4 / 8.3% / 92.7d / 0.0463 | -0.0007 BASE | -1.01% / -1.01% | 4 / 4 | 0.098 / 0.096 |
| 2022-09-24 | 4 / 5.6% / 96.3d / 0.0528 | 5 / 5.5% / 110.7d / 0.0839 | +0.0310 FAR | -0.71% / -0.67% | 3 / 4 | 0.110 / 0.175 |
| 2023-09-24 | 8 / 13.0% / 97.8d / 0.2960 | 8 / 12.9% / 181.8d / 0.5942 | +0.2982 FAR | -2.65% / -5.64% | 4 / 4 | 0.617 / 1.238 |
| 2024-09-24 | 8 / 7.4% / 97.8d / 0.1219 | 8 / 7.7% / 181.8d / 0.3030 | +0.1812 FAR | -0.39% / -3.28% | 4 / 4 | 0.254 / 0.631 |
| 2025-09-24 | 1 / 4.2% / 97.8d / 0.0058 | 3 / 5.9% / 181.8d / 0.0432 | +0.0375 FAR | -2.17% / -0.55% | 4 / 4 | 0.012 / 0.090 |

FAR wins 4/5 years (only 2021 goes to base, by 0.0007). 5-year pooled on
allocated: FAR 1.07064 vs base 0.523436 — at f = 0.25 the sleeve adds +26.77%
(+0.446 %/mo arithmetic, +0.425 %/mo geometric) vs base +13.09% (+0.218,
+0.213). Mean FAR DTE 146d overall (182d once full 6-mo histories exist
from 2023; 2021-2022 Binance-vision histories truncate it to ~93-111d).

## Per anchor year — Bybit inverse (live-venue quarterly chain)

| year | base n / sum | far n / basis / DTE / sum | diff (far-base) | worst MtM alloc base / far | max pairs base / far | acct +%/mo f=0.25 base / far |
|---|---|---|---|---|---|---|
| 2021-09-24 | 3 / 0.0411 | 4 / 6.3% / 188.8d / 0.0399 | -0.0012 BASE | -0.42% / -1.29% | 4 / 6 | 0.086 / 0.083 |
| 2022-09-24 | 3 / 0.0411 | 1 / 4.1% / 188.8d / 0.0530 | +0.0119 FAR | -0.74% / -6.13% | 3 / 2 | 0.086 / 0.110 |
| 2023-09-24 | 8 / 0.2845 | 8 / 11.8% / 188.8d / 0.5139 | +0.2295 FAR | -2.49% / -3.97% | 4 / 6 | 0.593 / 1.071 |
| 2024-09-24 | 8 / 0.1242 | 8 / 7.6% / 188.8d / 0.2859 | +0.1617 FAR | -0.52% / -1.08% | 4 / 6 | 0.259 / 0.596 |
| 2025-09-24 | 1 / 0.0064 | 2 / 4.5% / 188.8d / 0.0390 | +0.0326 FAR | -1.36% / -1.01% | 4 / 6 | 0.013 / 0.081 |

FAR wins 4/5 years (only 2021 to base, by 0.0012). 5-year pooled: FAR 0.931737
vs base 0.497293 — at f = 0.25 the sleeve adds +23.29% (+0.388 %/mo arithmetic,
+0.372 %/mo geometric) vs base +12.43% (+0.207, +0.202). Bybit serves full
contract lifetimes, so FAR holds are true ~189d throughout (no truncation).

## Capital intensity and interim risk (the price of the extra return)

- Simultaneous allocation (sum of open pairs' f): Binance FAR max 2 per coin
  / 4 total (= 1.0x equity at f = 0.25). Bybit FAR transiently hits 3 per
  coin / 6 total (= 1.5x equity at f = 0.25) during ~7-day roll weeks (three
  ~189d holds overlapping) — the PLAN's "about two per coin" expectation is
  exceeded on the live venue; reported, not hidden.
- Worst 4h-close MtM on allocated is roughly 2x base: Binance 2023 -5.64%
  vs -2.65% (account at f = 0.25: -1.41% vs -0.66%); Bybit 2022 single FAR
  pair drew down -6.13% before paying +5.30% (account -1.53% vs -0.18%).
  Longer holds mean deeper basis-widening episodes.

## Margin interaction (oc_utamargin UTA rule, 4h proxy, f = 0.25)

IM = (G2 gross + carry short)/5, balance = Eq - 0.05 x spot, blocked iff
IM > 95% balance; G2 envelope book_gross + 2.0 dip cap; tier-1 MM bound
0.33%. Checked on EVERY 4h close 2021-09-24..2026-09-23 with the actual FAR
legs (both venues):

| legs | worst IM/bal s0 | s1 | s2 | s3 | blocked closes | max MM/bal | max spot cost/Eq |
|---|---|---|---|---|---|---|---|
| BIN FAR f=0.25 | 0.53 | 0.53 | 0.57 | 0.59 | 0 | 0.010 | 1.04 |
| BIN FAR f=0.50 | 0.53 | 0.54 | 0.57 | 0.63 | 0 | 0.010 | 1.09 |
| INV FAR f=0.25 | 0.53 | 0.52 | 0.57 | 0.68 | 0 | 0.011 | 1.08 |
| INV FAR f=0.50 | 0.55 | 0.55 | 0.60 | 0.72 | 0 | 0.012 | 1.12 |

Zero blocked 4h closes at f = 0.25 on both venues' legs (limit 0.95; worst
0.68 on the live legs at G2's Oct-2023 stress hour, carry short there only
0.24 of mix equity). MM never exceeds 1.2% of balance — no liquidation risk
from maintenance. LIMITATION: 4h proxy (no hourly replay, no 1m wicks);
a 4h pass is necessary but not sufficient.
CASH CAVEAT: max spot cost exceeds equity at f = 0.25 (1.04x Binance legs,
1.08x live legs) — during peak overlaps the USDT wallet must borrow to fund
spot legs (bounded, ~4-8% of equity; at f = 0.50 up to 1.12x). Per the
oc_utamargin precedent (base f = 0.50 rejected at 1.80x), FAR at f = 0.25 is
IM-safe with wide margin but needs a borrow facility (or lower f / split
capital) on one UTA — deployment constraint, not a verdict-rule failure.

## Verdict

FAR BETTER — FAR supersedes the base rule; the carry direction stays open
with the FAR tenor (this was the last variant either way). Per-year carry
return on allocated is higher for FAR in 4/5 anchor years on BOTH venues
(Binance proxy AND Bybit inverse; the single loss, 2021, is ~0.001 on each),
AND zero blocked 4h closes at f = 0.25 on both venues' FAR legs. Expected
add at f = 0.25: +0.43 %/mo geometric (Binance proxy) / +0.37 %/mo (live
legs) vs base +0.21/+0.20 — roughly double the idle-equity yield, with worst
incremental account MtM about -1.4%/-1.5% (vs -0.7%/-0.6%) and transient
1.5x allocation on the live venue. Deployment: f = 0.25 per pair max, needs
USDT borrow headroom for roll weeks; requires the same hourly-UTA
confirmation and prospective paper check as everything else (4h proxy only).

## Leader decision (2026-10-06) - verdict NOT adopted
The FAR gain is exposure, not a better rate: entry basis per pair is essentially equal (e.g. 2023 12.9 % vs 13.0 %/yr) but FAR holds each
pair ~6 months while a new pair opens every quarter, so two pairs per coin overlap and allocated capital-time roughly doubles (spot
cost 1.04-1.12x equity -> USDT borrow needed, the same constraint that rejected base f = 0.50 in oc_utamargin). Per unit of capital-time
FAR ~= base. The pre-registered criterion compared per-year sums on allocated capital without normalising for overlap, so it cannot
separate rate from exposure. Decision: keep the base rule (next quarterly, f = 0.25); carry direction closed (2/2 variants used).
