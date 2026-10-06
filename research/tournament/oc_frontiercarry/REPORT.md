# oc_frontiercarry REPORT -- POST-HOC frozen carry sleeve (f = 0.25) on all 80 frontier rows

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
walk-forward years (anchors 2021-09-24 .. 2025-09-24, +365 d; oc_frontier reset 5y
metric); the carry rule was fixed before any combination (oc_cashcarry PLAN
pre-registered). Combination of already-scored rows only -- no selection claim,
no new predictive features (VF_COMMON feature-study rules: not applicable).

Question: for every frontier row (oc_frontier v399-v423, 80 BOT rows) whose
per-phase runs are stored (all 80: every vNNN_runs.pkl contains its rows), what are
5y mean, worst year, max yearly DD, full-path DD, losing years with and without the
frozen cash-carry sleeve at f = 0.25?

Method (reused UNCHANGED from oc_carryd13/combine_carryd13.py -- imported, not
modified): per anchor year, 4-phase mix reset to 1.0 (reset_metric.year_reset) + carry
sleeve at f of year-start equity (yearly rebalance, labelled), carry marked HOURLY
causal (last closed hourly bar strictly before t; 0 before entry-bar close; locked to
the frozen ret_alloc from settlement-bar close); combined es/ms = base es/ms + carry
curve; 5y mean = geometric mean of yearly monthly factors (same as frontier/v424);
full-path DD = chained-reset path (labelled). Base chained path uses the same chaining
for an apples-to-apples delta; official frontier values (rows R/W/DD + run.log
full-path DD) are kept in results.json for reference. Repro:
research/tournament/oc_frontiercarry/{combine_frontiercarry.py,results.json}; test
tests/test_oc_frontiercarry.py. 4h+1h data only, one process, no 1m, no engine reruns.

Margin (oc_utamargin REPORT): the additive overlay at f = 0.25 is margin-safe on ONE
Bybit UTA (5x, cross, hedge): 0 blocked hours, no MM breach, no liquidation including a
-10% gap at the worst hour; f = 0.50 needs split capital. So f = 0.25 is the largest
single-account f reported here.

## Headline

- 80/80 frontier rows had stored per-phase runs; base recomputation via year_reset is
  BIT-IDENTICAL to the official frontier table (R/W/DD max gaps 0.000).
- Carry f = 0.25 adds +0.11 to +0.14 pp on the 5y mean (mean +0.13) and trims max yearly
  DD by 0.02-0.78 pp (never adds DD on any of the 80 rows). No losing year appears or
  disappears (0 losing years in all 160 base/carry legs).
- BOT base (>= 5 %/mo, max yearly DD < 20 AND chained full-path DD < 20, no losing year):
  45 rows without carry -> 47 rows with carry (+2 flips: v409/R2B1D13 and v420/R2B1F15K20 cross 5.0).
- Stretch (R >= 5, max yearly DD < 15 AND chained full-path DD < 15, no losing year):
  0 rows with carry (no row meets DD < 15 on BOTH metrics even with the sleeve).
  Closest is v409/R2B1D13 at 14.87 yearly but 16.40 chained full-path.
- Win rate note: BOT all-trade win rate UNCHANGED -- the overlay is equity-level and adds
  zero trades (runs.pkl stores only t/eq/eq_min); carry pairs are 33/33 net positive on
  allocated capital per oc_cashcarry, reported separately.

## Full table (sorted by carry max yearly DD ascending; ties: higher carry R first)

Base fullDD and carry fullDD are BOTH the chained-reset convention (labelled); official
run.log full-path DDs are in results.json (convention gap up to 5.30 on high-DD rows,
e.g. v413/R2B1D18BFH 37.57 official vs 32.27 chained; G2 16.82 official vs 16.91 chained
base / 16.78 carry). base_ok = BOT base without carry; carry_ok = BOT base with carry;
stretch = carry meets the stretch bar (all False here).

| key | base R | base W | base DDmax | base fullDD | carry R | carry W | carry DDmax | carry fullDD | losing | base_ok | carry_ok | stretch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v399/R2B1 | 4.550 | 1.286 | 13.88 | 16.13 | 4.688 | 1.456 | 13.74 | 15.98 | 0 |  |  |  |
| v409/R2B1D13 | 4.957 | 1.728 | 15.00 | 16.54 | 5.091 | 1.890 | 14.87 | 16.40 | 0 |  | Y |  |
| v423/R2B1D17BFX45 | 5.118 | 2.402 | 15.92 | 15.92 | 5.246 | 2.552 | 15.78 | 15.78 | 0 | Y | Y |  |
| v409/R2B1D15B08 | 4.626 | 2.161 | 15.99 | 15.99 | 4.765 | 2.315 | 15.94 | 15.94 | 0 |  |  |  |
| v420/R2B1F20K17 | 5.042 | 2.521 | 16.00 | 16.00 | 5.172 | 2.670 | 15.95 | 15.95 | 0 | Y | Y |  |
| v423/R2B1D17BFX45G2 | 5.015 | 2.350 | 16.11 | 16.11 | 5.144 | 2.501 | 15.97 | 15.97 | 0 | Y | Y |  |
| v420/R2B1F15K20 | 4.993 | 2.129 | 16.17 | 16.17 | 5.120 | 2.284 | 16.05 | 16.05 | 0 |  | Y |  |
| v422/G2F20K20 | 5.346 | 2.648 | 16.20 | 16.20 | 5.471 | 2.795 | 16.09 | 16.09 | 0 | Y | Y |  |
| v404/R2B1G16_130 | 4.472 | 1.161 | 16.70 | 19.34 | 4.614 | 1.333 | 16.16 | 19.12 | 0 |  |  |  |
| v404/R2B1G18_130 | 4.781 | 1.406 | 16.47 | 18.82 | 4.921 | 1.573 | 16.20 | 18.62 | 0 |  |  |  |
| v409/R2B1D16B06 | 4.325 | 2.196 | 16.38 | 16.38 | 4.466 | 2.350 | 16.34 | 16.34 | 0 |  |  |  |
| v400/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v401/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v402/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v403/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v404/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v405/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v406/R2B1_130 | 5.171 | 1.404 | 17.06 | 20.47 | 5.308 | 1.571 | 16.77 | 20.26 | 0 |  |  |  |
| v421/R2B1D17BFG2 | 5.410 | 2.588 | 16.91 | 16.91 | 5.533 | 2.736 | 16.78 | 16.78 | 0 | Y | Y |  |
| v422/R2B1D17BFG2 | 5.410 | 2.588 | 16.91 | 16.91 | 5.533 | 2.736 | 16.78 | 16.78 | 0 | Y | Y |  |
| v422/G15K20 | 5.731 | 2.472 | 16.96 | 16.96 | 5.845 | 2.621 | 16.83 | 16.83 | 0 | Y | Y |  |
| v423/R2B1D17BFX5 | 5.311 | 2.822 | 16.87 | 16.87 | 5.441 | 2.966 | 16.83 | 16.83 | 0 | Y | Y |  |
| v420/R2B1F15K23 | 5.281 | 2.227 | 16.97 | 16.97 | 5.404 | 2.380 | 16.85 | 16.85 | 0 | Y | Y |  |
| v402/R2B1e_130 | 4.961 | 1.184 | 17.03 | 21.27 | 5.096 | 1.355 | 16.89 | 21.05 | 0 |  |  |  |
| v403/R2B1T_130 | 5.015 | 1.228 | 17.53 | 21.37 | 5.155 | 1.398 | 16.99 | 21.18 | 0 |  |  |  |
| v405/R2B1G18_140 | 4.945 | 1.463 | 17.36 | 21.12 | 5.080 | 1.629 | 17.07 | 20.92 | 0 |  |  |  |
| v406/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v407/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v408/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v409/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v410/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v411/R2B1D16 | 5.137 | 2.012 | 17.33 | 17.33 | 5.272 | 2.169 | 17.29 | 17.29 | 0 | Y | Y |  |
| v410/R2B1D16BF | 5.236 | 2.731 | 17.40 | 17.40 | 5.369 | 2.876 | 17.36 | 17.36 | 0 | Y | Y |  |
| v402/R2B1_125 | 5.111 | 1.366 | 17.52 | 20.52 | 5.247 | 1.534 | 17.37 | 20.31 | 0 |  |  |  |
| v399/R2B2 | 4.615 | 1.678 | 17.71 | 17.71 | 4.758 | 1.840 | 17.63 | 17.63 | 0 |  |  |  |
| v422/G2K20 | 5.874 | 2.832 | 17.79 | 17.79 | 5.989 | 2.976 | 17.66 | 17.66 | 0 | Y | Y |  |
| v403/R2B1S_130 | 4.852 | 1.058 | 18.37 | 21.30 | 4.995 | 1.232 | 18.07 | 21.09 | 0 |  |  |  |
| v401/R2B1R_110 | 4.764 | 1.546 | 18.38 | 20.47 | 4.900 | 1.711 | 18.10 | 20.30 | 0 |  |  |  |
| v402/R2B1e_150 | 5.134 | 1.049 | 18.26 | 23.05 | 5.268 | 1.223 | 18.15 | 22.82 | 0 |  |  |  |
| v419/R2B1D17BFBRK05 | 5.360 | 2.816 | 18.32 | 18.32 | 5.492 | 2.960 | 18.28 | 18.28 | 0 | Y | Y |  |
| v411/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v414/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v415/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v416/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v417/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v418/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v419/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v420/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v421/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v422/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v423/R2B1D17BF | 5.425 | 2.831 | 18.33 | 18.33 | 5.555 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v419/R2B1D17BFBRK08 | 5.401 | 2.831 | 18.33 | 18.33 | 5.532 | 2.975 | 18.29 | 18.29 | 0 | Y | Y |  |
| v419/R2B1D17BFBUD13 | 5.392 | 2.757 | 18.33 | 18.33 | 5.522 | 2.902 | 18.29 | 18.29 | 0 | Y | Y |  |
| v421/R2B1D17BFG3 | 5.291 | 2.680 | 18.33 | 18.33 | 5.421 | 2.826 | 18.29 | 18.29 | 0 | Y | Y |  |
| v418/R2B1D17BFDS | 5.547 | 2.752 | 18.35 | 18.35 | 5.673 | 2.897 | 18.32 | 18.32 | 0 | Y | Y |  |
| v417/R2B1D17BFX | 5.574 | 2.831 | 18.37 | 18.37 | 5.699 | 2.975 | 18.34 | 18.34 | 0 | Y | Y |  |
| v415/R2B1D17BFS6 | 5.565 | 2.760 | 18.37 | 18.37 | 5.689 | 2.905 | 18.34 | 18.34 | 0 | Y | Y |  |
| v415/R2B1D17BFS5 | 5.416 | 2.678 | 18.37 | 18.37 | 5.545 | 2.824 | 18.34 | 18.34 | 0 | Y | Y |  |
| v420/R2B1F20K20 | 5.300 | 2.704 | 18.41 | 18.41 | 5.429 | 2.849 | 18.37 | 18.37 | 0 | Y | Y |  |
| v417/R2B1D17BFC | 5.416 | 3.438 | 18.45 | 18.45 | 5.548 | 3.573 | 18.42 | 18.42 | 0 | Y | Y |  |
| v417/R2B1D17BFCX | 5.504 | 3.439 | 18.55 | 18.55 | 5.633 | 3.574 | 18.52 | 18.52 | 0 | Y | Y |  |
| v406/R2B1D18B08 | 5.042 | 2.491 | 18.70 | 18.70 | 5.175 | 2.640 | 18.66 | 18.66 | 0 | Y | Y |  |
| v400/R2B1_150 | 5.460 | 1.335 | 18.92 | 22.32 | 5.590 | 1.503 | 18.81 | 22.10 | 0 |  |  |  |
| v408/R2B1D18 | 5.452 | 2.370 | 19.14 | 19.14 | 5.582 | 2.521 | 19.10 | 19.10 | 0 | Y | Y |  |
| v412/R2B1D18BFS | 5.706 | 2.957 | 19.22 | 19.22 | 5.829 | 3.098 | 19.18 | 19.18 | 0 | Y | Y |  |
| v410/R2B1D18BF | 5.564 | 3.008 | 19.22 | 19.22 | 5.692 | 3.149 | 19.18 | 19.18 | 0 | Y | Y |  |
| v412/R2B1D18BF | 5.564 | 3.008 | 19.22 | 19.22 | 5.692 | 3.149 | 19.18 | 19.18 | 0 | Y | Y |  |
| v413/R2B1D18BF | 5.564 | 3.008 | 19.22 | 19.22 | 5.692 | 3.149 | 19.18 | 19.18 | 0 | Y | Y |  |
| v405/R2B1G18_150 | 4.842 | 1.244 | 20.30 | 23.41 | 4.978 | 1.414 | 19.80 | 22.97 | 0 |  |  |  |
| v416/R2B1D17BFD | 5.194 | 2.831 | 20.45 | 20.45 | 5.330 | 2.975 | 20.40 | 20.40 | 0 |  |  |  |
| v407/R2B1D20 | 5.779 | 2.515 | 20.95 | 20.95 | 5.905 | 2.663 | 20.92 | 20.92 | 0 |  |  |  |
| v407/R2B1D20B11 | 5.894 | 2.401 | 21.21 | 21.21 | 6.020 | 2.552 | 21.18 | 21.18 | 0 |  |  |  |
| v414/R2B1D17BFV1 | 5.731 | 2.409 | 22.93 | 22.93 | 5.852 | 2.559 | 22.91 | 22.91 | 0 |  |  |  |
| v401/R2B1R_130 | 5.198 | 1.980 | 23.51 | 26.91 | 5.328 | 2.138 | 23.00 | 26.48 | 0 |  |  |  |
| v400/R2B2_130 | 5.518 | 1.774 | 23.13 | 23.13 | 5.651 | 1.935 | 23.03 | 23.03 | 0 |  |  |  |
| v414/R2B1D17BFV2 | 5.711 | 2.301 | 24.08 | 24.08 | 5.832 | 2.453 | 24.06 | 24.06 | 0 |  |  |  |
| v399/R2 | 4.820 | 1.956 | 25.05 | 25.05 | 4.960 | 2.114 | 25.00 | 25.00 | 0 |  |  |  |
| v400/R2 | 4.820 | 1.956 | 25.05 | 25.05 | 4.960 | 2.114 | 25.00 | 25.00 | 0 |  |  |  |
| v413/R2B1D12BFH | 4.277 | 1.349 | 30.19 | 31.63 | 4.412 | 1.413 | 29.87 | 31.18 | 0 |  |  |  |
| v413/R2B1D18BFH | 5.040 | 1.384 | 32.27 | 32.27 | 5.159 | 1.552 | 31.49 | 31.49 | 0 |  |  |  |

## Menu (Vietnamese) -- 4 cau hinh dang xem xet, so co/khong carry, kem luu y that

Thap DD nhat dat BOT base (co carry): v409/R2B1D13 -- khong carry 4.957 %/thang, DD nam
15.00, fullDD chuoi 16.54 (rot moc 5.0); co carry f = 0.25: 5.091 %/thang, DD nam 14.87,
fullDD chuoi 16.40 -- carry keo qua moc 5.0 va giam DD ~0.13, nhung fullDD van > 15 nen
KHONG dat stretch. G2 dang deploy (v422/R2B1D17BFG2, audited yes; ban doi v421 cho so
giong het): khong carry 5.410 %/thang, DD 16.91/16.91; co carry: 5.533 %/thang, DD
16.78/16.78 -- dat BOT base ca hai, khong dat stretch. Deploy cu v411/R2B1D17BF:
5.425/18.33/18.33 -> carry 5.555/18.29/18.29, dat base, DD cao hon G2 ~1.5. Loi nhuan cao
nhat dat base: v422/G2K20 -- 5.874/17.79/17.79 -> carry 5.989/17.66/17.66 (dat base, DD
< 20); cao nhat tuyet doi v407/R2B1D20B11 (6.020/21.18 co carry) thi rot DD < 20 ca hai.
Luu y that (oc_carryfric): ma sat thi truong ha moi hang ~0.2-0.8 %/thang va pha vo DD
ngay ca khi f = 0.50, nen muc +0.13 cua sleeve la do dem nho, gan nhu mien phi ve DD/margin
(f = 0.25 an toan tren mot UTA theo oc_utamargin), chu khong phai thuoc chua ma sat -- can
paper-check trien vong nhu moi thu khac.

## Caveats / post-hoc log

1. No post-hoc change to definitions: base R/W/DD recomputed via the shared year_reset
   match the official frontier table exactly (max gaps 0.000/0.000/0.000). Full-path DD in
   the table is the chained-reset convention (labelled); official run.log full-path DDs
   differ by construction (up to 5.30 on the riskiest rows) -- convention gap, not a finding.
2. Carry leg is close-marked (hourly closes; no intra-hour low), so combined DD is a
   close-marked lower bound on the carry leg (same limitation as oc_carryd13/oc_carryfric).
3. v421/R2B1D17BFG2 rows are audit.passed false (awaiting blind audit); the identical twin
   v422/R2B1D17BFG2 is audited yes and gives identical numbers here (5.533/16.78).
4. v399/v400 official full-path DDs are null (predate full-path logging); chained values are
   reported for them like every other row (labelled).

## Verdict

REPORTING ONLY: carry f = 0.25 lifts every frontier row by ~+0.13 pp with a small DD trim,
flips 2 rows over the 5.0 line (45 -> 47 meet BOT base), but earns ZERO stretch passes
(closest v409/R2B1D13 fails the full-path leg 16.40 > 15). Sensible shortlist: lowest-DD
base pass v409/R2B1D13 (carry), deployed G2 v422/R2B1D17BFG2, highest base-pass return
v422/G2K20 -- all need the same prospective paper check as everything else.
