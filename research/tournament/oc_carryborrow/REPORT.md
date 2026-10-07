# oc_carryborrow REPORT — f=0.5 with USDT borrow cost on the extra spot

Method: ONE compounding account A(t)=A(t-1)*(1+r_bot(t))+dU(t)-borrow(t),
reused UNCHANGED from `oc_carrycompound/analyze_carrycompound.py` (same grid
2021-09-24 04:00 .. 2026-09-23 12:00 hourly, same causal last-CLOSED-hourly
marks, same fees spot 0.001/side + fut 0.00055/0.0002, same per-year reset to
1.0 with spanning carry rebased to 0, same continuous full-path DD with the
v421 formula). ASSUMPTION: r_bot from the stored 4-phase G2 mix applies to the
WHOLE equity (UTA: BOT sizes on total equity); carry notional N=f x A at each
entry held to delivery; f=0.25 no borrow; f=0.5 borrows the extra spot
B=0.25 x A at each entry (spanning: 0.25 x 1.0) at constant APR (main 10 %/yr,
stress 15 %/yr), hourly rate APR/8760 charged each held hour (grid time
strictly after entry-close, strictly before settlement). Carry leg
close-marked so DD is a lower bound. G2 base from v421/v422/audit-base runs
(twins asserted equal in-script); S1 = v421_audit G2 S1 BOT + S1 carry fees
stressed exactly as oc_carryfric2 (drag 0.0044). Repro:
`research/tournament/oc_carryborrow/analyze_carryborrow.py` (one process,
4h+1h only, no 1m, no engine reruns) + test `tests/test_oc_carryborrow.py`.
Frozen rule, no fitting; post-hoc combo.

## G2 base + borrow (per year R %/mo / DD %)

| scen | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing | gain vs f=0.25 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base f=0.25 (no borrow) | 2.778 / 10.86 | 3.353 / 16.75 | 6.590 / 15.69 | 10.956 / 8.20 | 4.698 / 12.66 | 5.634 | 2.778 | 16.75 | 16.66 | 0 | — |
| base f=0.5 @10% | 2.658 / 10.86 | 3.272 / 16.93 | 6.735 / 15.60 | 10.797 / 8.15 | 4.586 / 12.53 | 5.569 | 2.658 | 16.93 | 16.84 | 0 | -0.065 |
| base f=0.5 @15% | 2.503 / 10.86 | 3.195 / 17.10 | 6.538 / 15.60 | 10.577 / 8.16 | 4.504 / 12.59 | 5.424 | 2.503 | 17.10 | 17.01 | 0 | -0.210 |

## G2 S1 cost-friction row + borrow

| scen | 2021 | 2022 | 2023 | 2024 | 2025 | 5y | worst | maxDD | fullDD | losing | gain vs f=0.25 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 f=0.25 (no borrow) | 2.147 / 11.18 | 2.653 / 17.29 | 5.375 / 15.89 | 9.965 / 8.23 | 3.943 / 13.38 | 4.780 | 2.147 | 17.29 | 17.22 | 0 | — |
| S1 f=0.5 @10% | 2.009 / 11.18 | 2.560 / 17.47 | 5.495 / 15.78 | 9.778 / 8.19 | 3.822 / 13.25 | 4.696 | 2.009 | 17.47 | 17.39 | 0 | -0.084 |
| S1 f=0.5 @15% | 1.853 / 11.18 | 2.482 / 17.64 | 5.297 / 15.78 | 9.557 / 8.19 | 3.740 / 13.79 | 4.550 | 1.853 | 17.64 | 17.56 | 0 | -0.230 |

Validation: f=0.25 base reproduces oc_carrycompound G2_f0.25 TO THE DIGIT
(5.634/2.778/16.75/full 16.66; asserted in-script); S1 f=0.25 reproduces
oc_carryfric2 G2/S1/0.25 (4.780/2.147/17.29/full 17.22); v421/v422/audit-base
hourly twins asserted equal. Borrow paid (account units, per-year from 1.0):
base @10% [0.04200, 0.02646, 0.08370, 0.11149, 0.02071]; @15% correspondingly
~1.5x; no losing year appears or disappears anywhere.

## Plain verdict (Vietnamese, 3 lines)

f=0,5 KHÔNG đáng sau khi trừ lãi vay: base 5,569 (@10%) và 5,424 (@15%) đều thua f=0,25 (5,634), tức -0,065 và -0,210pp/tháng, DD còn nhích lên (16,93/17,10 so với 16,75).
Hàng S1 cũng vậy: 4,696 (@10%) và 4,550 (@15%) đều thua f=0,25 (4,780), tức -0,084 và -0,230pp/tháng, DD nhích lên (17,47/17,64 so với 17,29).
Giữ trần f=0,25 chung UTA như runbook (f=0,50 đã bị chặn margin, chưa kể lãi vay này).
