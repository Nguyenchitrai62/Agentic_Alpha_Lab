# oc_vipfees REPORT — Bybit VIP1/VIP2 fee repricing of R2B1D17BFG2 (2026-10-06; PLAN pre-registered before any outcome)

REPORTING task (no selection rule, no verdict). Deployment configuration =
R2B1D17BFG2 (registry v421: R2B1D17BF + dip gross-notional cap G = 2.0);
trade records = research/tournament/oc_kpi_g2/events_s{0..3}.parquet (every
fill/exit with maker/taker type and signed `weight` = notional as a fraction
of phase sub-account equity) + barsum_s{0..3}.parquet (bar equity).
Method = additive per-bar repricing (PLAN.md): per fee leg, saving =
|weight| x (old rate - new rate); per-shift monthly saving summed over bars /
contemporary bar equity; mix = mean over the 4 phase sub-accounts
(1/4 capital each); 1+R_new(M) = 1+R_old(M) + S(M) (gross path unchanged);
exit-vs-fill price drift ignored (rung nets are +/- a few %); funding is
identical across tiers and excluded. Repro:
research/tournament/oc_vipfees/{PLAN.md,compute_vipfees.py,results.json};
test tests/test_tournament_oc_vipfees.py. All five years are research data;
findings need prospective validation.

Fee schedules: gate VIP0 maker 0.0200 % / taker 0.0550 %. No repo doc lists
Bybit VIP tiers, so per the assignment VIP1/VIP2 are ASSUMED values,
cross-checked vs Bybit's current public derivatives schedule (2026-10-06):
VIP1 maker 0.0180 % / taker 0.0400 %, VIP2 maker 0.0160 % / taker 0.0375 %.
Public 30d derivatives-volume thresholds (assumed): VIP1 >= 10M USDT,
VIP2 >= 25M USDT. Maker legs (57,365 fee legs total): book_fill/add/reduce/
partial/tp/close, rung_fill/tp (sum |w| 1,741.9 sub-units). Taker legs:
book_stop, rung_sl/timeout (sum |w| 549.9 sub-units). Book fills are both
sides (buy 641-653 / sell 624-683 per shift). No event at/after 2026-09-24.

## Monthly-return gain per tier (continuous 4-phase mix, 60 full months 2021-10..2026-09)

| year (anchor) | months | R_old %/mo | R_VIP1 %/mo (+pp) | R_VIP2 %/mo (+pp) |
|---|---|---|---|---|
| 2021-09-24 | 2021-10..2022-09 | 2.5604 | 2.6620 (+0.1016) | 2.7032 (+0.1428) |
| 2022-09-24 | 2022-10..2023-09 | 3.1224 | 3.2276 (+0.1052) | 3.2730 (+0.1506) |
| 2023-09-24 | 2023-10..2024-09 | 7.3037 | 7.4279 (+0.1241) | 7.4826 (+0.1789) |
| 2024-09-24 | 2024-10..2025-09 | 10.6427 | 10.7693 (+0.1266) | 10.8240 (+0.1813) |
| 2025-09-24 | 2025-10..2026-09 | 4.6130 | 4.7151 (+0.1022) | 4.7565 (+0.1435) |
| 5y (60 mo geo mean) | 2021-10..2026-09 | 5.6066 | 5.7183 (+0.1117) | 5.7657 (+0.1590) |

5y net (from rounded 2dp monthlies; exact oc_kpi_g2 net is 2538.74, residual
+0.47pp from monthly rounding, identical for all tiers): VIP0 2539.21 %,
VIP1 2712.02 %, VIP2 2788.60 %. Annualised equiv of the gain:
VIP1 (1.001117)^12-1 = +1.35 %/yr, VIP2 = +1.92 %/yr. Mean monthly saving over
full months: VIP1 0.114 %, VIP2 0.163 % (range VIP1 0.014..0.283 %/mo,
VIP2 0.021..0.413 %/mo; full 61-month table in results.json).
Win rates move only upward and negligibly (saving >= 0 on every bar):
rungs flipped losing->winning VIP1 88/21513 (+0.41pp), VIP2 110/21513
(+0.51pp); book VIP1 5/5064 (+0.10pp), VIP2 7/5064 (+0.14pp); all-trade
+0.35pp / +0.44pp. Drawdown unchanged (VIP1/VIP2 equity path pointwise >=
VIP0 path; not recomputed).

## Volume vs tier thresholds (turnover tau = 22.98x contemporary equity / month)

| account equity | monthly volume (tau x E) | share of VIP1 10M | share of VIP2 25M | fee USD saved/mo VIP1 / VIP2 |
|---|---|---|---|---|
| 5,000 USDT | 114,879 USDT | 1.1 % | 0.5 % | 5.70 / 8.13 USDT |
| 10,000 USDT | 229,758 USDT | 2.3 % | 0.9 % | 11.40 / 16.26 USDT |
| 50,000 USDT | 1,148,790 USDT | 11.5 % | 4.6 % | 57.02 / 81.31 USDT |

Equity required to reach tiers on volume alone: VIP1 ~435,241 USDT,
VIP2 ~1,088,101 USDT (threshold/tau). Caveat: Bybit's program also has
asset-balance routes (public: VIP1 ~$100k assets, VIP2 ~$250k), likewise out
of reach at 5-50k equity; volume and balance requirements were not re-verified
against a logged-in fee page.

Summary: VIP1 adds +0.11pp/month (+1.35 %/yr, 5y net 2539 % -> 2712 %) and VIP2
+0.16pp/month (+1.92 %/yr, -> 2789 %) with no DD or win-rate change of note, but
at 5k-50k USDT the strategy trades only ~0.11-1.15M USDT/month, 1-11 % of the
10M/25M 30d-volume thresholds (would need ~$435k/$1.09M equity), so the
deployment keeps VIP0 fees.
