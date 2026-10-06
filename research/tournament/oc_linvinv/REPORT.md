# oc_linvinv REPORT — same-expiry linear-vs-inverse quarterly RV (Bybit)

Question: does the same-expiry linear-vs-inverse dislocation lock a
convergence profit? Method frozen in PLAN.md (written before outcomes):
at each pair-chain roll date (prev delivery - 7d, up to next spot 4h open;
first pair = first availability), for each coin where a linear-USDT and an
inverse quarterly share the SAME `deliveryTime`, ENTER iff
|ann_lin - ann_inv| >= 3 pp/yr, long cheaper / short richer in equal USD
notional f = 0.125/coin/leg, hold both to the shared delivery. Fees: taker
0.055%/leg entry + 0.02%/leg delivery on entry notional (drag 0.15% on
allocated). Settlement = Bybit spot 4h close of the delivery bar; beyond
the last spot bar = incomplete (excluded). Repro:
`research/tournament/oc_linvinv/{PLAN.md,analyze_linvinv.py,results.json}`;
test `tests/test_oc_linvinv.py`. 4h data only, one process.

## Pairs (linear USDT quarterlies exist on Bybit only since 2025)

16 same-`deliveryTime` pairs seen (8/coin: 2025-06-27 .. 2027-03-26).
By entry-opportunity year (anchors 2021..2025-09-24):

| year | pairs (BTC+ETH) | entered | skipped (< 3pp) | incomplete / no-overlap |
|---|---|---|---|---|
| 2021-09-24 | 0 | 0 | 0 | 0 |
| 2022-09-24 | 0 | 0 | 0 | 0 |
| 2023-09-24 | 0 | 0 | 0 | 0 |
| 2024-09-24 | 6 (3+3: Jun25/Sep25/Dec25) | 0 | 6 | 0 |
| 2025-09-24 | 8 (4+4: Mar26/Jun26/Sep26 + Dec26 incomplete x2) | 0 | 6 | 2 incomplete + 2 no-overlap (Mar27) |

Complete-opportunity diffs (pp/yr): max 2.55 (BTC Jun25: lin 7.50 vs inv
4.94), next 1.27 (ETH Jun25); the other ten are all < 0.7 (six < 0.4).
No pair ever reaches the fixed 3 pp/yr filter: 12 skipped, 0 entered.

## P&L and MtM

Entries: 0, so net return on allocated = 0.0000 (account contribution at
f = 0.125: +0.00%) and worst MtM is empty (no open spread ever; the
closest call, BTC Jun25 at 2.55 pp, would have locked about
S_del*(1/F_c-1/F_r) ≈ +0.6% gross on allocated minus 0.15% fees, but the
rule says SKIP — no post-hoc entry).

## Convexity note (assignment rule, as executed)

Inverse P&L is computed in coin and converted at the delivery price:
N*(1/F_entry - 1/S_del) coins x S_del = N*(S_del/F_entry - 1), exactly the
linear price-return formula. The 1/F convexity lives only in the
coin-denominated path (a long gains fewer coins per point up than it loses
per point down); the USDT-converted spread economics are linear, and the
same linear formula is used for MtM (converted at the contemporaneous
mark). Delivery-fee-on-entry-notional is a stated approximation (second
order next to the spread).

## Verdict

NOT USEFUL — the data is too short, CLOSE. Zero entries (rule needs >= 3
entries total and net > 0 on every entry year; there is no entry year).
Linear USDT quarterlies start 2025-02-18, so only 12 complete same-expiry
opportunities exist and none clear 3 pp/yr — the dislocation this sleeve
needs has not printed in the available history. No further work in this
direction without new data (revisit only if a longer linear-quarterly
history or a dislocation regime appears).
