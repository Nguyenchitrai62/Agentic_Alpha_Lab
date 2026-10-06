# oc_clockanat: anatomy of the phase-3 2023 drawdown (R2B1D17BFG2)

Source: `v421/v421_runs.pkl` + one vendored v421-harness rerun of phase 3 only
(live 2021-09-24+3h..2024-09-24+3h, single process, events+attrib+path hook;
reproduction max abs diff 0.0 on 2190 bars). Units: year-start points (phase
equity = 1.0 at 2023-09-24). No data >= 2025-09-24 is simulated or scored.
Peak (close) 2024-01-03 11:00 UTC, 1.3076; trough (marked) 2024-09-20 03:00,
0.7424 -> DD 43.23 %; trough close 2024-09-20 11:00, 0.7427; year end 0.7443
(R -2.431 %/month). Peak-to-trough-close drop -0.5649 over 1566 bars (~8.5 mo).
Top-10 losing days (p3 | p0 p1 p2 | mix): 01-03 -0.2453 (-0.018 -0.267 -0.319 |
-0.2123); 06-07 -0.1192 (-0.384 -0.117 +0.011 | -0.1523); 04-13 -0.0965
(+0.020 -0.212 -0.166 | -0.1137); 12-11 -0.0602 (all neg | -0.0418); 11-09
-0.0441 (all pos | +0.0219); 03-05 -0.0396 (all neg | -0.1615); 04-12 -0.0286;
08-05 -0.0246 (others +0.06..+0.17 | +0.0804); 11-21 -0.0239; 09-28 -0.0191.
Top-10 sum p3 -0.7011 vs mix same days -0.6129; mix lost on 7/10 days.
Peak->trough split: book -0.1317 (23 %), dip -0.4332 (77 %), total -0.5649.
Dip exits in window: 85 stop, 326 take-profit, 267 timeout (215 losers).
Top dip losers, all rung_sl: 01-03 BTC fills min 51/55/56 of bar T 11:00, depth
2.5/3.0/3.5/4.0 sigma, stopped 12:09 (-717 bps, -0.029/-0.019/-0.019/-0.015);
06-07 XRP fills min 180 of bar T 15:00, depth 2.5/3.0/3.5 sigma, stopped in 5
min (-979/-914/-849 bps); 04-13 BNB fill min 53 of bar T 19:00, stopped 17 min
later (-1103/-1028 bps); 04-12 XRP fill min 148, stopped next hour (-1304 bps).
Answer: slow bleed punctuated by stop cascades, not one crash: 8.5-month
peak->trough, only the worst day (-0.2453, 96 % of the year net) looks like a
single event, the rest is repeated dip-stop clusters (01-03, 04-12/13, 06-07)
plus 267 timeout exits grinding in the downtrend; the top-10 loss (-0.70)
exceeds the year net (-0.26), so +0.44 was earned back between the episodes.
Phase 3's boundary kept arming rungs minutes before the cascade (fills min
51-61 stopped 10-20 min later; XRP min 180 stopped 5 min later). The 4-phase
mix avoids it mostly by dilution (1/4 weight) plus a fatter cushion (mix year
end 2.02 vs phase 3's 0.74; other clocks earned +4..+11 %/mo that year), not by
hedging: 6-7 of phase 3's 10 worst days are common losses on every clock, only
3-4 days (11-09, 08-05, partly 04-12/11-21) show offsets.
Ket luan: DD 43 % cua dong ho 3 khong phai mot cu dan duy nhat ma la chay mau
cham 8.5 thang xen 3 cum stop cascade (rung khop vao vai phut truoc cascade roi
bi stop ngay, timeout exit mon dan trong downtrend); hon hop 4 dong ho thoat
chu yeu nho pha loang 1/4 va dem loi day hon chu khong phai hedge nghich chieu.
