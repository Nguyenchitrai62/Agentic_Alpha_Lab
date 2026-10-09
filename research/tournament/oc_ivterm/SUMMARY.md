# oc_ivterm SUMMARY (<= 15 lines)

- TS = 7d ATM IV / DVOL hourly; contango avg 0.87-0.97; inversion 4-6% (21-22) -> 15-30% (23-24).
- Base replica reproduces placebo 7.7183 exactly; TS join NaN 0%.
- Dips: high-TS worse in 2021/23/24 (-19..-64 bps, stop rate up) but 2022 flips (+78 bps).
- Inversion TS>1: better in 21-22, worse in 23-24. Sign not stable 4/4 -> NO tilt scored.
- Book IC(TS, next-24h vol-norm ret) ~0 everywhere (|IC|<=0.11, mostly <0.03), no stable sign.
- Verdict: REJECT static TS tilt; needs new regime-conditional direction + prospective proof.
