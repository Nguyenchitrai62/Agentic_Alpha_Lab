# oc_clockluck REPORT (2026-10-06)

QUESTION: are the four hourly clocks of the deployment lucky, or are half-hour
clocks structurally worse?

## Setup
- G2 = v421 R2B1D17BFG2. oc_phase8 totals: hourly 0/1/2/3 h 5y 6.92/4.83/5.59/3.10
  %/mo; half-hour 0.5/1.5/2.5/3.5 h 5.37/4.64/3.19/4.01; 4-phase mix 5.41, 8-phase
  mix 4.96. Half-hour clocks ffill the standard book table (<=30 min stale) and
  the s0 agent table (walk-forward). Repro: research/diagnostics/oc_clockluck/
  {clockluck.py, results.json} + attrib caches oc_clockluck_attrib_s<XX>.pkl.
- Part (1): totals from oc_phase8 pickles; splits from causal attrib reruns (same
  worker as oc_phase8 + attrib/path_out like oc_clockanat; attrib = per-bar
  (t, book per-asset PnL, dip PnL) as fractions of bar-start equity, scaled to
  year-start points). Reproduction max |eq/eq_cached-1| = 0.0 on all 8 clocks.
  book_pts + dip_pts = year net, resid 0.000 every clock-year.
- Part (2): exact oc_dipexit D0 replica with START shifted by o minutes
  (bars [START0+o+4h*j,...), START0 = 2020-08-01 00:00 UTC, o = 0,10,...,230 =
  24 offsets), B1 sizes w = 1/(1+n) (oc_b1deeper v399-exact, n = other majors
  with C(T+f-1) <= O(T)*(1-2.5*sg(T))), R2 depths 2.5/3/3.5/4/5, majors, bars
  open in [2021-09-24,2026-09-24), live 16..238 strict low<lv, D0 exits
  (TP 1sg maker; close5 stop 4sg / backstop 8sg taker, stop-first; timeout at
  next-bar open taker + 0.0001 longs on settling bars). S(o,year) = sum(w*y)
  raw size-weighted; NaN exits dropped. Offset 0 reproduces B1 raw sums
  2.388/0.183/3.810/2.579/0.712 (B1 REPORT 2.39/0.18/3.81/2.58/0.71). Fills per
  offset 5382-5675.
- All 5 years to 2026-09-24 are research data; diagnostic only (vs RULES.md 2 /
  VF_COMMON hidden-year). Needs prospective validation before real money.

## (1) Book vs dip per clock-year (year-start points; R %/mo from oc_phase8)
| clock | 2021 book/dip (R) | 2022 book/dip (R) | 2023 book/dip (R) | 2024 book/dip (R) | 2025 book/dip (R) |
|---|---|---|---|---|---|
| 0h | 0.122/0.587 (4.567) | 0.335/0.189 (3.571) | 0.668/1.958 (11.249) | 0.954/1.193 (10.023) | 0.587/0.298 (5.427) |
| 0.5h | 0.165/0.754 (5.584) | 0.221/0.134 (2.569) | 0.092/0.104 (1.499) | 1.224/1.778 (12.250) | 0.680/0.167 (5.248) |
| 1h | 0.027/0.386 (2.919) | 0.328/0.262 (3.942) | 0.438/0.209 (4.226) | 0.863/1.156 (9.645) | 0.472/0.052 (3.577) |
| 1.5h | 0.056/0.356 (2.914) | 0.172/0.271 (3.107) | 0.145/0.041 (0.815) | 0.903/1.876 (11.715) | 0.589/0.199 (4.957) |
| 2h | 0.079/0.213 (2.153) | 0.278/0.186 (3.226) | 0.214/0.901 (6.412) | 0.923/1.910 (11.849) | 0.487/0.227 (4.590) |
| 2.5h | 0.061/0.025 (0.690) | 0.110/0.073 (0.301) | 0.071/0.009 (0.621) | 0.807/1.645 (10.204) | 0.453/0.105 (4.462) |
| 3h | 0.023/0.007 (0.188) | 0.143/0.172 (2.312) | -0.007/-0.244 (-2.431) | 0.744/1.940 (11.040) | 0.486/0.272 (4.905) |
| 3.5h | 0.088/0.192 (1.335) | 0.129/0.315 (3.087) | 0.233/0.208 (3.562) | 0.636/1.392 (9.795) | 0.487/0.087 (2.487) |
Hourly-mean vs half-hour-mean (points; + = half better):
2021 book +0.019 / dip +0.020 (half not worse); 2022 book -0.113 / dip -0.041;
2023 book -0.193 / dip -0.615; 2024 book -0.012 / dip +0.148; 2025 book +0.020 /
dip -0.078. The half-hour deficit concentrates in 2022-2023 on BOTH sleeves,
largest in dip-2023 (0.090 vs 0.706). 2023 dip is the phase-3 crash window
(oc_clockanat: dip -0.43 of -0.56 peak-to-trough); half-hour books (0.5 h stale
ffill) and half-hour dip timing both lose there. VERDICT (1): half-hour clocks
are structurally worse, not just unlucky — they underperform on book AND dip
in the same crash years.

## (2) Dip timing luck over 24 START offsets (S = sum(w*y))
5y sums: min 4.55, max 9.67 (offset 0), mean 7.12, median 7.13, std 1.54.
Deployed hourly offsets: 0 = 9.67 (percentile 100%, the max), 60 = 7.54 (58%),
120 = 8.76 (88%), 180 = 4.90 (8%). Mean of the 4 deployed = 7.72 vs mean of
all 24 = 7.12; luck gap (all - deployed) = -0.59 (-8% of deployed).
Per-year S distributions (mean_all vs mean_deployed; gap = all - deployed):
2021: range -0.89..2.82, mean 0.913 vs 0.911 (gap +0.00; pct 0:96%, 60:54%, 120:46%, 180:13%);
2022: -0.33..1.75, 0.798 vs 0.833 (gap -0.03; 0:13%, 60:88%, 120:79%, 180:25%);
2023: 0.45..3.81, 1.676 vs 2.100 (gap -0.42; 0:100% max, 60:58%, 120:88%, 180:4%);
2024: 2.19..3.74, 3.209 vs 3.197 (gap +0.01; 0:13%, 60:46%, 120:79%, 180:75%);
2025: -0.14..1.19, 0.527 vs 0.677 (gap -0.15; 0:67%, 60:38%, 120:63%, 180:88%).
The deployed set is lucky almost entirely through 2023 (offset 0 is the best
of 24) plus 2025; 2021/2022/2024 are neutral. Offset 180 (3h) is near-worst on
the 5y sum (8th percentile) while offset 0 is the best — the 4-phase hourly
mix diversifies this within itself.

## (3) Random-clock expectation for deployed G2 (approximate)
Method: random-clock ~= book(mix4, unchanged) + dip(mix4) * ratio, ratio =
mean_all_24 / mean_deployed_4 of B1-weighted dip sums, applied per year; year
points -> R = 100*((1+pts)^(1/12)-1); 5y = geometric mean of yearly R.
APPROXIMATE: the equal-bar replica dip (no gross caps, governor, compounding)
stands in for the G2 dip sleeve; the book is assumed clock-neutral at the mix
level. Ratios all/deployed: 2021 1.002, 2022 0.958, 2023 0.798, 2024 1.004,
2025 0.779, 5y 0.923. Mix4 yearly R from points: 2.588/3.282/6.093/10.677/
4.648 (5y 5.42 ~= deployed 5.41). Adjusted yearly R: 2.593/3.233/5.453/10.691/
4.401 -> random-clock expectation 5y = 5.24 %/mo. So ~0.17 pp of the deployed
5.41 looks like dip-clock luck; the expectation stays above 5%/mo on this
approximation, but the margin is thin and the method is only a proxy.

## Verdict
VERDICT: BOTH — the four hourly clocks are lucky on the dip (offset 0 is the
24-offset max, 2023 carries the gap; random-clock ~= 5.24 vs deployed 5.41)
AND half-hour clocks are structurally worse (they lose on book and dip in the
same 2022-2023 crash years, dip-2023 0.09 vs 0.71). Neither fact alone explains
the 0.45 pp mix gap in oc_phase8.

Ket luan: bon dong ho gio hien tai gap may o sleeve dip (offset 0 dung dau
trong 24 offset, chu yeu nho nam 2023; ky vong dong ho ngau nhien khoang 5.24
so voi 5.41 hien tai theo phep gan dung nay), DONG THOI cac dong ho lech nua
gio kem mot cach cau truc (ca book lan dip deu thua trong 2022-2023, dip 2023
chi 0.09 so voi 0.71), chu khong don thuan la den hay do.
