# oc_carrycompound REPORT — account-realistic (compounding) carry overlay on G2

Method: ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t). ASSUMPTION (as ordered):
r_bot is the stored 4-phase G2 hourly return and applies to the WHOLE equity
A(t-1) (UTA: the BOT sizes on total equity, carry included); dU is the frozen
oc_cashcarry pair MtM change on notional N=f x A at each entry, held to
delivery, fees spot 0.001/side + fut 0.00055/0.0002. Marks causal hourly
(last CLOSED hourly bar strictly before t; 0 before entry-close; locked to
frozen ret_alloc from settlement-close; carry leg close-marked, DD lower
bound). Per-year reset to 1.0 (reset_metric arithmetic); spanning carry
rebased to 0 at each anchor; full-path DD continuous from grid start, v421
formula. f=0 short-circuits to base bit-exact. Repro:
`research/tournament/oc_carrycompound/analyze_carrycompound.py` (one process,
~44k hourly rows, 4h+1h only, no 1m, no engine reruns) + test
`tests/test_oc_carrycompound.py`. Frozen rule, no fitting; post-hoc combo.

## G2 + carry, compounding account (per anchor year R %/mo / DD %)

| year | f=0 (= G2) | f=0.25 compound |
|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.778 / 10.86 |
| 2022-09-24 | 3.282 / 16.91 | 3.353 / 16.75 |
| 2023-09-24 | 6.045 / 15.81 | 6.590 / 15.69 |
| 2024-09-24 | 10.677 / 8.27 | 10.956 / 8.20 |
| 2025-09-24 | 4.648 / 12.90 | 4.698 / 12.66 |
| 5y mean / worst / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 5.634 / 2.778 / 16.75 / 0 |
| full-path DD (marked/close/full) | 16.82 / 16.05 / 16.82 | 16.66 / 15.90 / 16.66 |

Validation: f=0 reproduces v421_result G2 (5.41/W 2.588/DD 16.91/full 16.82)
TO THE DIGIT (asserted in-script, also in tests).

## Why carrycombo (5.413) and carryfric (5.533) differ (5 lines)

1. carrycombo sizes each pair at f x TOTAL COMBINED equity at its entry but
adds carry P&L as absolute cash onto a FIXED BOT path (C=Etot+settled+U), so
the BOT never earns return on carry profits and the anchor denominator carries
past carry overhang — on fast BOT years the fixed carry accrual dilutes the
blended rate (2024 falls 10.677->10.559).
2. carryfric/d13 sizes carry at f x YEAR-START equity (fixed all year) and adds
it to a per-year reset base rebased to 0 at each anchor, so every intra-year
accrual lifts the rate (2024 rises to 10.779) but later entries are NOT sized
on intra-year growth and carry profits earn NO BOT return.
3. Neither compounds: combo grows notionals but not returns-on-carry; fric
grows neither intra-year.
4. The compounding account here does both (notionals f x live A + r_bot on all
A), so its lift (+0.224pp to 5.634) exceeds both (+0.003 combo, +0.123 fric).
5. Real-account match: the compounding one — in a UTA the BOT's position
sizer sees total equity (BOT capital + carry pair value), so BOT returns apply
to everything and new pairs are sized on live equity; combo/fric are
book-keeping overlays, useful bounds but not what one account would print.

## Plain verdict

The carry add for G2 at f=0.25 is +0.224 %/mo (5.410 -> 5.634 %/mo
compounded; worst 2.588->2.778; max yearly DD 16.91->16.75; full-path DD
16.82->16.66; no losing year appears or disappears). Honest context: still a
carry overlay on the same five research years (post-hoc combo, needs
prospective paper); carry leg close-marked so DD is a lower bound; spot legs
need funding inside the UTA (no extra-capital denominator here — state it).
