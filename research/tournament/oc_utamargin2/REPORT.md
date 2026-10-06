# oc_utamargin2 REPORT — POST-HOC sensitivity: carry-short leverage 5x/10x/20x

Question: the carry short is fully hedged by its spot leg, so its leverage
setting can be set independently of the G2 perps. Does raising it from 5x
to 10x/20x clear a larger carry fraction f? Rerun of the oc_utamargin
hourly margin path for f in {0.25, 0.375, 0.5} x carry-short leverage in
{5x (reproduce), 10x, 20x}. Repro:
`research/tournament/oc_utamargin2/analyze_utamargin2.py` (one process,
hourly, 43,805 hours 2021-09-24 00:00 .. 2026-09-23 04:00 UTC, no 1m, no
engine reruns) + `tests/test_oc_utamargin2.py`. POST-HOC (labelled):
f = 0.375 and lev 10x/20x were chosen after seeing oc_utamargin.

## Method (single change vs oc_utamargin, everything else verbatim)

- G2 legs rebuilt HOURLY from stored `oc_kpi_g2` events/barsum with the
  exact `oc_margin` q-units math; frozen 33 `oc_cashcarry` pairs, legs =
  f x mix equity at entry, held to delivery; causal hourly_ext + qbasis 1h
  marks; equity ffill. Only change: IM = G2_gross/5 + carry_short/LEV_CARRY
  (parent: /5 on both). MM tiers UNCHANGED (tiered, no netting).
- Blocked iff IM > 95% balance; liquidation iff balance < MM; balance =
  Eq_tot − haircut x spot_val (base haircut 5%).
- Stresses per (f, lev) at its own worst hour (all cells worst =
  2025-09-25 18:00, G2's worst zone): −10% all-coin gap; haircut 10%/20%
  (balance recomputed, IM/MM unchanged); +30% BTC/ETH squeeze within 24h
  (uniform-mark ASSUMPTION; G2 BTC/ETH net included directionally).

## Bybit venue leverage (public, no keys, fetched live 2026-10-06, frozen in results.json)

| listing | max leverage | source |
|---|---|---|
| linear dated BTC/ETH (LinearFutures, e.g. BTCUSDT-25DEC26, 16 live) | 50x | GET /v5/market/instruments-info?category=linear |
| inverse quarterly BTCUSDH27 / BTCUSDZ26 | 100x | GET /v5/market/instruments-info?category=inverse |
| inverse quarterly ETHUSDH27 / ETHUSDZ26 | 50x | same |
| inverse BTCUSD tier-1 (risk-limit) | 100x, IM 1%, MM 0.5% | GET /v5/market/risk-limit?category=inverse |

10x/20x on the quarterly short is within every applicable limit.
ASSUMPTIONS (marked): Binance UM-quarterly data proxies Bybit linear
dated; UTA cross-pooled margin (the load-bearing one — see squeeze);
10%/20% haircuts stand in for a stressed collateral schedule.

## Per-cell results (base haircut 5%; gap = −10% at worst hour)

| f | lev | min free | max IM/bal | blocked h | MM breach | max MM/bal | gap loss | gap liq |
|---|---|---|---|---|---|---|---|---|
| 0.25 | 5x | 22.49% | 77.51% | 0 | 0 | 1.95% | −28.85% | no |
| 0.25 | 10x | 32.67% | 67.33% | 0 | 0 | 1.95% | −28.85% | no |
| 0.25 | 20x | 37.76% | 62.24% | 0 | 0 | 1.95% | −28.85% | no |
| 0.375 | 5x | 12.18% | 87.82% | 0 | 0 | 2.12% | −28.96% | no |
| 0.375 | 10x | 27.47% | 72.53% | 0 | 0 | 2.12% | −28.96% | no |
| 0.375 | 20x | 35.12% | 64.88% | 0 | 0 | 2.12% | −28.96% | no |
| 0.50 | 5x | 1.85% | 98.15% | 1 | 0 | 2.29% | −29.07% | no |
| 0.50 | 10x | 22.26% | 77.74% | 0 | 0 | 2.29% | −29.07% | no |
| 0.50 | 20x | 32.47% | 67.53% | 0 | 0 | 2.29% | −29.07% | no |

5x column reproduces oc_utamargin bit-for-bit (0.25: 0 blocked; 0.50:
1 blocked hour 2025-09-25 18:00). No MM breach and no gap liquidation in
any of the 9 cells (maintenance stays <= 2.3% of balance).

## Haircut stress (same IM/MM, balance with 10% / 20% haircut)

| f | lev | hc10 min free / blocked | hc20 min free / blocked | gap liq (hc10/hc20 bal) |
|---|---|---|---|---|
| 0.25 | 5x | 18.30% / 0 | 8.40% / 0 | no / no |
| 0.25 | 10x | 29.03% / 0 | 20.42% / 0 | no / no |
| 0.25 | 20x | 34.39% / 0 | 26.44% / 0 | no / no |
| 0.375 | 5x | 4.85% / 1 | −14.22% / 3 | no / no |
| 0.375 | 10x | 21.42% / 0 | 5.67% / 0 | no / no |
| 0.375 | 20x | 29.70% / 0 | 15.61% / 0 | no / no |
| 0.50 | 5x | −9.41% / 3 | −41.98% / 132 | no / no |
| 0.50 | 10x | 13.34% / 0 | −12.45% / 3 | no / no |
| 0.50 | 20x | 24.72% / 0 | 2.31% / 1 | no / no |

f = 0.50 fails the haircut stress at EVERY leverage (even 20x blocks 1
hour at hc20). f = 0.375 fails at 5x (1 blocked at hc10) but clears at
10x AND 20x (0 blocked, gap never liquidates).

## Squeeze stress (+30% BTC/ETH at the worst hour)

- ISOLATED short leg: 30% loss vs IM_short = notional/lev gives
  loss/IM = 1.50 at 5x, 3.00 at 10x, 6.00 at 20x — the short alone is
  liquidated at ALL three settings before the spot gain can help.
- UTA CROSS (pooled): spot gain + short loss + G2 BTC/ETH net offset
  almost exactly (hedged net ~ basis); NO liquidation and NO block in
  ANY of the 9 cells (cross IM/bal after: 0.52–0.87, worst f0.5_lev5).
- ACCOUNT MODE MATTERS: the "hedged so leverage is free" claim holds
  ONLY in cross (UTA default, per Bybit docs leverage is per-pair and
  pooled; hedge-mode same-pair long/short must share leverage, but the
  quarterly short is a different symbol from the perp, so independent
  10x/20x is permitted). Never run this sleeve with the short isolated.

## Verdict

Largest f clearing EVERY stress (0 blocked + 0 MM breach on base path,
0 blocked under 10% AND 20% haircuts, no gap liquidation, squeeze cross
clean): f = 0.375 at 10x carry-short leverage (20x also passes
mechanically: 0 blocked everywhere; 10x preferred — 2x more IM buffer
on the short leg if the cross-pool assumption ever breaks, still 27.5%
min free / 21.4% under hc10 / 5.7% under hc20).
Deployment caveats (unchanged mechanics, honest): at f = 0.375 spot cost
peaks at 139% of equity (headroom −39%) — the USDT wallet MUST borrow
during overlap stretches (interest unmodelled), same structural issue
oc_utamargin found at f = 0.50; f = 0.25 peaks at 95.8% (headroom +4.2%)
and clears everything already at 5x with no borrow. So: one-UTA additive
stays f = 0.25 (5x, no change); f = 0.375 @ 10x is the bounded exception
only if auto-borrow is accepted. f = 0.50 is NOT cleared at any leverage.

KHUYEN NGHI: mot UTA van chay additive f = 0.25 (5x, khong doi); muon
nang len f = 0.375 thi short quarterly de 10x (20x cung qua nhung mong
hon) va chap nhan borrow USDT mua spot; f = 0.50 khong dat o moi don bay
(haircut 20% van chan lenh). Bat buoc cross margin — isolated short chay
ngay khi squeeze +30%.
