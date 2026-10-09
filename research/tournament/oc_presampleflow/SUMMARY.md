# oc_presampleflow SUMMARY (2026-10-07)

Q: do deployed book families (whale flow A/Aq, Coinbase premium D/Dq) have
7d pooled-HGB skill before 2021? A: NO -- and neither after 2021 on the same
spot-built yardstick: pooled IC ~0 in 20/21 variant-years (all CIs but one
cross zero; the one, prem-2021 negative, does not persist).
Train IC 0.26-0.56 every anchor x variant (fit loop works): overfit, no
generalisation -- same verdict as the TV-only member (oc_presamplebook).
FLOW 7y pooled IC: 0.054/-0.024/-0.015/0.024/0.010/0.008/0.004.
PREM 7y pooled IC: -0.027/0.062/0.064/-0.164/-0.023/0.057/-0.065.
BLEND (deployed 0.8/0.2): 0.040/-0.009/-0.007/-0.014/0.017/0.026/-0.014.
Diag P&L is drift x exposure + noise (DD 12-71%): untradeable as-is, not engine.
Venue: SPOT flow both sides (research used PERP flow -- disclosed); labels and
fills on one stitched SPOT series; fits obey label-end < anchor - 7d.
G2 book timing is not standalone 7d skill of any family; look at shorter
horizons / LS structure / sizing / engine instead. Direction closed, no deploy
change, no prospective log needed. Tests: 6 passed.
