# Research map (update after every rotation)

Last update: 2026-10-06 (after v424): BOT deployment = R2B1D17BF (v411) + dip gross cap 2.0 (runbook); every risk overlay moves along one return-vs-DD frontier (oc_frontier); stretch DD<15 only at ~4.97 %/mo (v424 D13BF); MANUAL best honest ~3.7 %/mo. Older update: 2026-10-04 (after v389).

2026-10-05: rolling (clock-free) dip anchors closed (lose 2021-22, research/diagnostics/rolling_anchor_dips); MANUAL human schedule (15-min, night skipped) honest 3.0-3.6 %/month, DD 22-24 (research/diagnostics/manual_human).

2026-10-05: v390 ex-ante covariance book sizing (R2-4P) rejected (4.82/4.87 vs 5.24, DD not lower). BOT execution layer bot/ (order mirror; paper on live Bybit klines running).

## 2026-10-06 update (v390-v424 + OpenCode screen wave 2026-10-05)

Last draft: 2026-10-06. Sources: .claude/skills/alpha-lab-leader/research-map.md (to v390), CONTINUOUS_RESEARCH.md 2026-10-04..06 top paragraphs, research/tournament/oc_frontier/REPORT.md (80 rows v399-v423, reset 5y metric). All five walk-forward years are research data; findings need prospective validation.

### Current state
- BOT deployment pick = v411 R2B1D17BF (dips x1.7 corr-size + bear-book): 5y 5.425 %/mo, worst 2.83, max yearly DD 18.33, full-path 16.90, win 65.5%; frictions all DD <= 20 (lat15 5.24, stop-slip 5.11/DD20.0, Bybit 4.97/19.9, lat30 4.68, stress 4.58). Runbook: D17BF + --dip-gross-cap 2.0 (engine hook sleeve_gross_cap; oc_gapstress: -10% all-coin gap 58% -> 33.5% equity; oc_kpi dip notional to ~6.4x without cap). Paper bots: R2-4P, d17bf, d17bfg2, g2k20.
- FRONTIER (oc_frontier, yearly DD): R2B1 4.55/13.88 - D13 4.957/15.00 - X45 5.118/15.92 - G2F20K20 5.346/16.20 - G2 5.41/16.91 - G15K20 5.731/16.96 - G2K20 5.874/17.79 - D20B11 5.894/21.21. Full-path: D15B08 4.626/14.94 - F20K17 5.042/15.47 - X45 5.118/15.81 - G2F20K20 5.346/16.02 - S5 5.416/16.62 - S6 5.565/16.71 - G15K20 5.731/16.76 - G2K20 5.874/17.69 - D20B11 5.894/19.10. Deploy pick on NEITHER (dominated yearly by G2K20, full-path by S6). Stretch DD<15 + >=5%/mo only at edge: v424 D13BF 4.97/yearly 14.98/full 14.86.
- MANUAL best honest ~3.6-3.7 %/mo, DD > 20: manualbf (MANUAL + bear-book, human 15-min/night-skipped schedule) 3.6-3.7/DD21.6 worst-phase 33->25; oc_manual2 top-2 dips 3.06/DD19.5 fails base; human costs ~0.6pp; ~80% capital for DD<20 (~2.8%/mo). MANUAL floor still open.

### v390-v424 tried / result / verdict
- v390 ex-ante covariance book sizing (R2-4P): 4.82/4.87 vs 5.24, DD not lower -> rejected.
- v391 tournament sizes on R2-4P: R2K 5.85/3.03/25.2, R2C 5.58/2.33/23.1, R2T 4.84/1.69/24.3 vs 5.24/1.96/23.1; fold3 lost by 0.0014 -> no transfer, rejected.
- v392 kelly x0.9/x0.8: 5.59/24.3, 5.25/25.5 -> scaling moves size into wrong episodes, rejected.
- v393 MANUAL M5 + size tables: M5K 3.82/27.8, M5C 3.98/27.4 vs M5 4.09/24.4 -> M5 kept.
- v394 sizes + 6-sigma close-stop: R2CS6_4P 5.147/2.13/19.39 (first honest >=5 + DD<=20), R2KS6 5.15/2.94/22.2; folds prefer R2K -> no transfer (robust pick R2CS6).
- v395 GATE scored ONCE recent year: R2CS6_4P 3.48/DD25.15 (R2-4P 3.90/18.8) -> 5y 4.81 FAIL (a)/(b)/DD; dip-size gains do not transfer (as v279/v280/v189-197).
- v396 risk-to-book: folds keep R2 -> rejected.
- v397 book shape (EMA/long-only): 3.62/4.46 vs 4.82 -> rejected (shorts hedge, smoothing delays).
- v398 11-coin dip sleeve: X11 4.39/1.07/31.6, X11N 4.09/losing/40.1 vs R2 4.82/1.96/25.1 -> majors-only confirmed, rejected.
- v399 corr-aware B1 (n=other majors >=2.5sg at f-1): B1 1/(1+n) 4.55/13.88, B2 4.62/17.71 vs R2 4.82/25.05 -> DD breakthrough, return down.
- v400 risk back on B1: R2B1_130 5.171/1.40/17.06 (recent 5.43), _150 5.46/18.92, B2_130 5.52/23.13 -> R2B1_130 first base pass, selected.
- v401 +2.0sg rung: DD up -> rejected. v402 earlier 2.0sg flush detect: worse -> rejected. v403 book loss control (tighten/SL3): worse -> rejected. v404 tighter gov 0.18/0.10 + 0.25/0.15: 4.47-4.78/full 18.7 -> DD down return down, rejected. v405 gov+more risk: worse -> rejected.
- v406 book->dips: D16 5.137/2.01/17.33/16.37, D18B08 5.042/2.49/18.70/17.22 -> first incl full-path DD, base PASS.
- v407 dips x2.0: 5.779/2.52/20.95, D20B11 5.894/2.40/21.21 -> return up DD breach, rejected.
- v408 D18 5.452/2.37/19.14/17.57 -> best BOT row then, candidate.
- v409 alloc frontier to stretch DD: D13 4.957/15.00/16.36, D15B08 4.626/15.99/14.94, D16B06 4.325/16.38/15.21 -> DD down return down, kept as frontier only.
- v410 bear-book (longs x0.5 BTC<1200-bar mean): D16BF 5.236/2.73/17.4/16.2, D18BF 5.564/3.01/19.2/17.6 (audit+robust PASS; Bybit 5.09/DD20.8) -> gain, DD mixed.
- v411 R2B1D17BF (x1.7 + bear-book) 5.425/2.83/18.33/16.90 win65.5, frictions all DD<=20 -> DEPLOYMENT PICK (paper artifacts/bot/paper_d17bf).
- v412 short gate: gain only 2023 -> rejected. v413 hourly+B1 DD30-38 (4th hourly failure) -> rejected. v414 DVOL size tilt: more return more DD -> rejected.
- v415 close-stop 5/6sg: S5 5.416/18.37, S6 5.565/18.37 vs 5.425/18.33 -> no DD gain, folds keep D17BF, rejected (run-before-register deviation disclosed).
- v416 BTC-dominance tilt: 5.194/20.45/18.37 -> rejected.
- v417 cascade (24h cooldown / XRP5.5, post-hoc): C 5.416/3.44/18.45, X 5.574/18.37, CX 5.504/18.55, no fold transfer -> rejected.
- v418 DVOL short gate: 5.547/18.35/recent 4.50 -> rejected.
- v419 breaker/budget (post-hoc labelled): BRK05 5.36/18.32, BRK08 5.401/18.33, BUD13 5.392/18.33 -> neutral, closed.
- v420 flush x mult: F20K17 5.042/2.52/16.00/15.47, F15K20 4.993/16.17, F15K23 5.281/16.97, F20K20 5.30/18.41 -> frontier moves only.
- v421 gross cap G (notional<=Gx): G2 5.410/16.91 (same return DD-1.4), G3 5.291/18.33 -> safety pick (3 rows audit NO; twin in v422 audited).
- v422 cap+size: G2K20 5.874/2.83/17.79/17.69 (best R; fold fails recent), G15K20 5.731/16.96, G2F20K20 5.346/16.20 -> no deploy (post-hoc + fold fail).
- v423 drop deep rungs: X45 5.118/15.92/15.81, X5 5.311/16.87, X45G2 5.015/16.11 -> DD down return down, frontier (audit PASS).
- v424 stretch combo D13BF 4.97/14.98/14.86 -> frontier edge, below base.

### Closed screen directions (2026-10-05 wave, one line each)
- oc_rips: regime-conditional rip-sell ladder -> every rule 5y negative, LOYO unstable (-3.7 vs dips +11.7) -> asymmetric edge, closed for good.
- oc_regime: slow regimes of dip edge -> signs flip >=2/5y -> no gate, closed.
- oc_newinfo: Wikipedia attention / CME gaps -> two fragile hints for logging only, not tradable -> closed.
- oc_optctx: Deribit skew/put-flow/Coinbase premium context -> NOT PROMISING, closed.
- oc_idea3 pre-bar RV skip / oc_idea10 1h confirmation / oc_volflush capitulation volume -> no transfer, closed.
- oc_idea7 VRP budget dial (2022 inversion) / oc_idea4 funding surprise (tail 3/5) / oc_idea5 premium-flip veto / oc_idea8 dominance-momentum throttle (tail 3/5) -> closed.
- oc_manual2 MANUAL top-2 dips 3.06/19.5 -> fails base, closed.
- oc_idea2wf walk-forward per-coin stops / oc_coinwf coin WF weights / oc_cooldown stop cooldown -> sums up, tails worse, closed.
- oc_velocity velocity guard / oc_b1soft soft B1 / oc_adaptsig adaptive sigma / oc_deeptp deep-rung fast TP -> no gain on frontier, closed.
- oc_bullbook bull-book boost / oc_rlbear RL bear-feature agents (V0 exact) / oc_dailyladder daily ladder / gross-cap-alone selection -> along frontier or neutral, closed.
- oc_idea6 basis momentum / oc_beartp bear-bar fast TP / oc_bookbrake book brake / oc_bookdipnet book-dip overlap / oc_b1btc B1-BTC / oc_b1deeper deeper price (DD down 5/5 sum down 4/5) / oc_weekend weekend / oc_eventblk macro blackout / MANUAL static corr proxy (0/5) -> closed.
- Tournament dip size/TP models (kelly V2/context V2/tp V2 lose newest regime; tp=+TP1.5 which lost v391R2T) -> direction CLOSED; v395 lesson: dev dip-sizing gains need paper-log proof before any dev-selected change.

### Open queue
- Prospective paper evidence first: R2-4P / d17bf / d17bfg2 / g2k20 bots + scripts/bot_health.py, paper_report.py, paper_compare.py; rolling-12m (49: median 4.89, none losing, all DD<20) is in-sample.
- Liquidation/top-book data: backend/liquidations.py (Bybit liqs + Binance forceOrder + top-book) collecting since 2026-10-04 -> features only after 4-12 weeks; oc_liq stream healthy but too short; oc_topbook/oc_venuegap pending.
- Bot-vs-engine parity fixes: bot_beartrim committed; plan-staleness fix (4h plan dropped after 2h -> bids cancelled mid-bar; restarted 14:25 UTC); sleeve_gross_cap + --dip-gross-cap wired; Bybit-price/latency/stop-slip frictions in runbook; oc_dvolshort (short-leg only, 5/5) screen running.

### Lessons
- Frontier: B1 threshold / mult / gross cap / deep-rung drop / bear-book all trade return for DD (oc_frontier); no free DD; overlays (D13BF edge 4.97) cost return.
- Attribution: additive rung/sleeve sums mislead (oc_contrib/oc_plateau); only the 4-phase reset-metric engine_user run decides (metric correction: continuous 1/4 mix let lucky phase-0 43x dominate).
- Ops: background tasks default 30min -> workers get 2h timeout, paper bots under nohup; backend IS the plan source (stall froze plans 12:03 UTC; restarted LOCALLY 127.0.0.1 no tunnel); monitor plans, not just bots.

## 2026-10-06 addendum (screens after the first update; v425/v426 frontier rows)

Phạm vi: mọi REPORT.md dưới research/tournament/ + research/diagnostics/ có mtime 2026-10-06 (61 file,
liệt kê đủ dưới đây kèm verdict lines), cộng audit oc_bookmodel_audit (AUDIT/COMPARISON, không phải REPORT).
Mọi số y nguyên báo cáo. Cả 5 năm walk-forward đều là research data; phát hiện cần paper triển vọng.
FINAL_REPORT_VI.md §5/§6 đã cập nhật các hướng đóng sau 482129e (btclead, rungcap, bookcorr, coinbear,
longcap, cadence, manualtsmom) + chẩn đoán (ddanat_g2, grindsignal); file này là danh mục đầy đủ để leader
merge vào map.

### A. Đề xuất merge vào map (đóng/mở sau 482129e)

- ĐÓNG dip-ladder: oc_btclead NOT PROMISING (sum 0/5: FULL 10.33 vs BASE 15.14; DD 1/5; fills 4998 vs 5498) —
  giữ B1 size-only. oc_rungcap NOT PROMISING (giữ ≥97% tổng 0/5, tốt nhất 91% 2023, raw FULL 7.45 vs 9.67;
  DD 3/5; rung bị cắt win 72-83%) — cụm crash-bar không phải chỗ cắt.
- ĐÓNG book: oc_bookcorr NOT PROMISING (DD 5/5 nhưng retention ≥90% chỉ 1/5: 0.73/0.88/0.92/0.83/0.74) —
  ý tưởng #43. oc_coinbear NOT PROMISING (DD 3/5, P&L≥95% 3/5; grind −0.0504→−0.0506) — ý tưởng #44, không
  đăng ký engine. oc_longcap NOT PROMISING (retention 0/5: 0.848-0.948; DD 1/5 strict; grind −0.0499→−0.0511) —
  ý tưởng #46. oc_cadence NOT PROMISING (8h: P&L 2/5, DD 1/5; 12h: 2/5, 3/5) — ý tưởng #47, đóng hướng cadence.
- ĐÓNG MANUAL: oc_manualtsmom — overlay TSMOM-30d 0.25x lên 3.90/DD 19.33 (excess +5/5, DD tệ hơn 5/5),
  không hàng nào chạm base MANUAL — add-on tương quan.
- MỞ (lead duy nhất): oc_bookcoinbrake PROMISING 4/5 DD + 4/5 P&L (rớt DD 24-25, rớt P&L 25-26: 0.389 vs
  0.95×0.4136=0.3929; cắt ~30% book loss grind −0.0504→−0.0354) — ý tưởng #45, ứng viên đăng ký engine + paper.
- Chẩn đoán: oc_ddanat_g2 — gate 16.91 = grind 2023-04-17→06-15 (~59d/354 bar; long −9..−11 + dip −7..−10/phase,
  BNB-led, short bù +6.8 gộp); <15 cần cắt ~11% thiệt hại cửa sổ; cascade 2024-01-03 (15.81) đã −2.5pp nhờ
  trần G=2.0. oc_grindsignal — giả thuyết breadth=1.0 (E0/E2/E3 max, E1 0.8), gate sau điều kiện trên
  over-extension.
- FIX XONG: bot_capfix — FIXED + ~không tốn (C_on 3.20%/261 vs A 3.58%/271; trần cũ 1.12%/209) — chờ merge
  bot/mirror.py + chạy lại paper có trần. oc_bookmodel_audit — FAIL F1 (rank42 làm feature, common_impl.py:
  251-256; W1 c2:141-147; N1 c1:147-148) → fix dispatched [OPENCODE_W_oc_bookmodel_fix.md] → re-audit → Kaggle.
- XONG: oc_margin — cross/5x tối thiểu (3x kẹt 22 phút-mix), G2 max ~3.4x, phút tệ nhất cần −29% mới cháy,
  gap −10%/−20% 0/65.1k phút cháy → runbook cross + 5x, không Isolated.
- Paper bots trên đĩa: paper, paper_d13bf, paper_d17bf, paper_d17bfg2, paper_g2k20 (5 thư mục; assignment ghi
  6 — leader xác nhận roster bot thứ 6). v425 pre-registered (trần hàng conservative) [d79630d].

### B. Danh mục đủ 61 REPORT 2026-10-06 + verdict (nhóm theo FINAL VI)

Đã vào FINAL VI §1-4/Bổ sung (không nhắc lại số): oc_frontier (REPORTING, 80 hàng v399-v423; D17BF
5.425/18.33/16.90 nằm TRONG cả hai biên; v423 audit PASS), oc_kpi_g2 (G2: 5.41/DD 16.91/16.82, win all 65.3%,
gross tệ nhất 3.0x vs 6.4x), oc_tsmom_official (D13BF 4.97/năm 14.98/toàn đường 14.86; +TSMOM-0.10 lên 5.03
nhưng DD 15.42 — không tổ hợp nào đồng thời ≥5% và DD<15), oc_rolling17 (49 cửa sổ: min 2.73/p10 3.25/
trung vị 4.89/p90 8.88/max 11.71; 49% ≥5%, 100% DD<20), oc_stresshist (tuần tệ nhất 2023-12-27..2024-01-03
−12.3%/DD 13.9%/hồi ~54d), oc_gapstress (−10% phút tệ nhất không trần −58% vốn → trần 2x còn 33.5%),
oc_contrib (shallow dips + TPs + book longs earn the return), oc_venuegap (XRP rungs gánh gap dip-ladder
nhưng chỉ ~4% rung P&L — S5 drag nằm ở BOOK), oc_bookvenue (drag KHÔNG nằm ở book execution),
oc_signedfunding (funding thực +0.12-0.15pp/tháng vs gate — gate bảo thủ hơn), oc_regimeexp (2026-09:
trên MA200, vol thấp, trend 90d +35%; nhóm lịch sử 21 tháng TB +8.1%/trung vị +5.0%), oc_wfselect
(NOT PROMISING — giữ cố định D17BF+G2: 6.03 vs 6.08), oc_manualcap (M5_human 3.73/17.8, G15 3.01/14.9,
G10 2.62/13.5 — Direction CLOSED cap thuần túy), oc_collectors (KHỎE từ restart 2026-10-05 17:40 UTC:
9.06h, 0 gap>60s, 326.813 topbook rows, 802 liqs).
Đã vào FINAL VI §5 từ trước (screens/OpenCode): oc_b1soft NOT PROMISING (SOFT>2/5 chỉ 1/5 — giữ B1 F=2.5),
oc_adaptsig NOT PROMISING (DD 4/5 nhưng efficiency 3/5 — giữ sigma360), oc_bullbook NOT PROMISING (P&L 5/5
nhưng DD episode nằm ngoài stretch boost), oc_deeptp NOT PROMISING (1/5 cả hai chân — giữ TP 1.0),
oc_rungspace NOT PROMISING (sum không thấp hơn chỉ 1/5 dù DD 5/5 — giữ spacing R2), oc_bookexit
NOT PROMISING (+1.0 ATR bank), oc_phaserebal NOT PROMISING (rebalance tháng/tuần đều −0.15/−0.18pp 5y),
oc_bookoffset PROMISING 5/5 nhưng là vol-scaled offset (trade-mode entries đã sigma-scaled — xem commit
bookoffset closed), oc_bookcoinwf PROMISING 5/5 nhưng VACUOUS (gate không loại coin nào — closed),
oc_postflush NOT PROMISING (mean âm 3/5, events 2-10/năm < floor 10), oc_lowvolrung NOT PROMISING
(sum 3/5, DD tệ hơn 5/5), oc_dipbe NOT PROMISING (giữ ≥97% tổng 0/5, DD 3/5 — giữ exit D0),
oc_condhold NOT PROMISING (sum 3/5, DD 1/5 — timeout vẫn exit ở open tiếp theo), oc_holdext NOT PROMISING
(1/5 cả hai — timeout giữ nguyên), oc_bybittp (TP lệch gần như toàn thành timeout 84%),
oc_diptilt NOT PROMISING (return 4/5 nhưng DD chỉ 1/5 — tilt bull 1.2x scale cả climb lẫn dip),
oc_tsmom NOT PROMISING (overlay 0.25x return +5/5 nhưng gate rớt), oc_tsmomcombo (combo D13BF+0.10 chạm
stretch trên lưới daily — check official đã rớt), oc_tsmomvar NOT PROMISING (DIV 0/5 cả hai variant —
đóng, không sleeve), oc_xsrev NOT PROMISING (thua 5/5: net −2.5..−5.4%/tháng, DD tệ hơn 5/5 — đóng),
oc_earlystart PROMISING 4/5 + 4/5 NHƯNG fragile (3/4 năm thắng ~0, 2023 −0.68/DD gấp đôi, full-path về BASE —
cần paper trước mọi engine), oc_manualshallow (NO row passes base MANUAL — best 3.73),
oc_regimetrue (diagnostic: TRUE pairs mọi depth đều thắng), oc_depthregime (deep rungs thua MỌI regime),
oc_deepcheck (xác nhận oc_depthregime), oc_recent (năm gần nhất margin thấp, tập trung hơn),
oc_ladderfill (diagnostic fills, không rule), oc_liqlive PATCHY-nhưng-loadable, oc_topbook
PATCHY-nhưng-loadable.
Ops/thực thi 2026-10-06: bot_parity (bot khớp engine rules — Verdict YES), bot_bookgap (exits-per-piece
~1.0 sau fix; chỉ còn test cũ pin hành vi OLD rớt), bot_parity_adopt (adopt_fresh Verdict NO — +1 fill,
vẫn −64 vs engine, return không đổi; arm C cũ +1.12% vs +3.58% → bot_capfix đã sửa), ops_liveparity
(placement parity PASS so far; win n/a — 0 closed), ops_enginespeed (đo tốc độ engine — xem REPORT),
bot_capfix (FIXED, xem mục A).
Mới trong draft này (FINAL VI §5/§6 đã cập nhật): oc_btclead, oc_ddanat_g2, oc_rungcap, oc_manualtsmom,
oc_bookcorr, oc_coinbear, oc_bookcoinbrake (PROMISING — mở), oc_longcap, oc_grindsignal, oc_margin (XONG),
oc_cadence, oc_bookmodel_impl (implementation-only, smokes C1 25.1s/C2 18.7s, 8 tests pass — chờ fix audit).
Audit kèm theo (không phải REPORT): oc_bookmodel_audit/AUDIT.md (F1 blocker + W1/W2/N1, 9 tests) +
COMPARISON.md (bookmodel: FAIL — chưa upload Kaggle).

- v425 gross cap on D13-D15 rows: D13BFG2 4.92/15.07, D14BFG2 5.05/15.55, D15BFG2 5.17/16.24 -> cap only binds at large kd; rejected.
- v426 per-coin book brake: G2BRK 5.30/16.02 (full 15.61) vs G2 5.41/16.91 -> frontier move; rejected.


## 2026-10-06 addendum 2 (book screens, v427 C2, bot testnet wiring)

- Book screens (vectorised BOT book, v410 bear filter first): oc_expirybook PROMISING (book x0.5 in the 48 h before the monthly
  Deribit expiry: DD not worse 4/5, P&L >= 98 % 4/5; 5y book maxDD 10.05 -> 9.05, P&L +0.016) -> full-engine post-hoc check
  oc_expiry4p running (G2 4-phase); oc_expirycb (expiry + Coinbase premium) running. Closed: oc_cbpremium (P&L up 5/5 but DD
  worse 3/5), oc_skewbook2, oc_basisbook, oc_breadthbook, oc_breadthdip (DD never worse but sum >= 95 % only 1/5).
- v427 = book model C2 (rank-calibrated, pooled 77 coins as signal only) on Kaggle nguynchtrai/oc-c2-rank-calibrated. v1 failed
  at start: script kernels upload ONLY code_file -> bundle helper modules into one self-extracting kaggle_entry.py (base64 zip),
  as v2 does. Same fix is needed for C1 before its push. Evaluation: oc_bookmodel_evalprep (dev years only, 2025 sealed).
- Bot: entries PostOnly (crossing -> postonly_reject, retried, never chased); risk_guard wired (ON in testnet/live, opt-in
  --risk-guard in paper so paper stays engine-faithful). Running: oc_bookholdcap, oc_fomcbook (FOMC window x0.5), oc_blendsens,
  oc_phasedisp, oc_capscale, bot_mockex (fake V5 exchange e2e), ops_paperday2.

## Honest status

EXECUTABLE TRADE MODE (user rules 2026-09-28: one resting limit order, no fill in the first 5 minutes after the 4h close, in a
position only SL/TP edits and discrete limit adds/reduces/exits, market only for stops; engine_user `trade=` + `trade["policy"]`):
best = v218 D2 = v216 G2 grid trader (limit size adjustments at most once/day when |target - w| > max(3%, 40% target), limit exit on
signal loss, break-even +2 sigma_d) + dip sleeve budget 0.15 / rung x1.75: dev4 5.26, worst year 2.18%/mo, DD 19.1, win 51%, final
5y 4.97, last year 3.82 (scored once). Deployed: scripts/forward_trade.py (FREEZE 2026-09-28 08:00 UTC) -> web trade plan.
Tried in this family (all audited): v208 execution policy (vol limit / market / band) DD > 20; v209 luck tests (alpha t 3.5, placebo
0/40, beta 0.08) + discrete fixed SL/TP 4.1-4.4; v210 trade mode T1-T3 (T2 4.47/DD 25.5); v211 risk sizing worse; v212 scale in/out
S3 4.83/DD 20.7; v213 limit exit on signal loss E1 4.22/DD 19.3; v214 value RL (fitted Q / MC) 3.3-3.8; v215 one-step improvement
cross-fitted 3.2-3.6 (value estimates favour early exits); v216 grid G1-G3; v217 ES policy search 4.0-4.6 (does not transfer);
v218 DD budget -> sleeve best; v219 sleeve budget 0.18-0.21 DD > 20; v220 learned dip-bid filter hurts; v221 exit hysteresis ~equal;
v222 sub-account bot ensembles ~equal. Diagnostic (dev only, not registered): dip-bid outcome vs open-interest drop at the fill
(5m metrics) - Spearman ~0, sign flips by year -> no liquidation-flush edge.
v229 hourly dip ladder in trade mode (bids x4, 2022 -30%, DD 42-44: rejected). v230 Korean (Upbit) premium member K (USDKRW lagged 2 days; K alone dev4 3.69 -> dilutes like DVOL/macro/COT; best K3 replace A 4.98 DD 20.09: rejected). Dev-only diagnostics (not registered): D2 DD episodes - worst (2023-04..06, 17.2%) is 11pp dip sleeve; the sleeve earns most of the return (2021-24: +27.5/+5.5/+54.7/+44.6% of equity vs books ~+1/+32/+37/+59) and is uncorrelated with the book; sleeve losses are NOT serially dependent (daily autocorr 0.03-0.06, next-week return after a sleeve drawdown equal or better) -> equity-curve throttles would hurt. Untested data left: none of note (on-chain / stablecoins / OI / options / Coinbase / Korea / macro / COT / F&G / DVOL all tried).
QUALITY DATA (user 2026-09-28): data/raw/binance_premium_20260928 = Binance 1m premium-index klines + settled funding, 5 majors, 2020-01.. (scripts/fetch_binance_premium.py); predicted funding reconstructed exactly (MAE 0.05-0.07 bp; BNB interest 0). Funding-hunter study (pre-anchor only, research/diagnostics/funding_premium): positive predicted funding -> premium pushed down in the last minutes, price +14 bps in the 15 min after the settlement (t 7.5); negative -> +15 bps before, -20 after; the move sits in the settlement minute -> not tradable with the minute-5 rule, used as features. v231: TradingView indicators (v231/tv_indicators.py, 17 causal features) in member A = FIRST foundation gain in a long time: dev4 5.46, 5y 5.115 (first >= 5), DD 20.0, last year 3.74; premium+F&G member worse (dilutes, DD 23). Next: TV features in the quarterly half, RL v232 on the V1 foundation.
v232 disciplined RL (cut losers only; dev DD -1pp, last year 3.13) rejected; v233 T3 (TV in all members) 5y 5.156 DD 18.41 last 3.851; v234 daily/weekly TV (dev 5.82, last 2.94) rejected; v235 TV-state dip-bid bandit (sleeve still unpredictable) rejected. BEST: v236 W2 = T3 + WHALE FLOW (Binance aggTrades taker flow by order size, v236/flow_features.py) in the A members: dev4 5.774, worst dev year 2.491, DD 19.51, 5y 5.442, last year 4.123 (scored once), hidden win 54.8% - first time new data lifted dev mean, worst year and the unseen year together. W1 (flow in all members) DD 27. Next: live whale-flow feed (daily archive + websocket), flow x open-interest composites.
v237 spot vs perp whale flow (data/raw/aggflow_spot_20260928): DD 21-22, rejected; v238 market-wide flow (BTC + cross-asset mean): DD 22-24, rejected -> per-asset perp flow (W2) is the useful form; more features on top of W2 raise DD. W2 robustness (research/diagnostics/w2_robustness): no losing year under cost stress / latency / parameter shifts; latency > 15 min hurts (30 min: DD 24); bootstrap median 5.33%/mo, P(loss year) 1.1%, P(DD>20) 7%. Deployed paper pipelines: D2 (v205 books), T3, W2 (live flow via scripts/aggflow_live.py + daily archive in the backend).
v240 O1 (order-level whale flow) = robust best (worst dev year 2.759, DD 19.08, 5y 5.364, last 4.069). Rejected on O1: v241/v242 learned sizing (per bar = churn; entry-locked = no gain), v243 flow-state dip filter, v246 W2+O1 ensembles (last year 4.28 but worse dev worst year). v245 SMALL ACCOUNT: Bybit lot minimums (BTC 0.001, ETH 0.01, SOL 0.1, BNB 0.01, XRP 0.1, 5 USDT) make BTC/ETH impossible at ~100 USDT (44% of O1 orders placeable; 96% at 1000 USDT); SOL/BNB/XRP-only O1 = dev4 4.55, last year 2.56. Dip intrabar diagnostic (dev only): fast pre-fill drops revert better (speed Spearman negative all 4 years) but every quintile is positive -> cancel rules cannot help; the sleeve's limit is the risk budget / DD, not selection (4th confirmation).
v244 Bybit cross-venue order flow: DD 22 (3rd flow extension raising DD; flow direction closed). v247 O1 sleeve budget 0.18 = current best (dev4 5.777, worst dev year 2.854, DD 19.65, 5y 5.436, last 4.082). v248 learned dip-EXIT agent (TP multiple at the fill, exact counterfactuals, engine hook sleeve_tp): dev4 6.05 (largest dev gain) but DD 20.7 and last year 3.85 -> rejected; fixed TP 1.0 sigma is the best fixed rule (0.5: 4.70, 1.5: 5.30, 2.0: 5.01). Data: aggTrades fetcher now keeps a 1m store (8 log-size bins) so future flow features need no re-download.
v249 learned ladder-depth window (six rungs, sleeve_filter): D1 DD 22.6, strict = reference -> rejected. v250 per-rung weights: inverse (heavier near) P3 dev4 5.914 / worst 2.968 / DD 19.0 / 5y 5.525 but last year 3.98 (< 4.082) -> no transfer; pyramid (heavier deep) worse. v251 strategy-level vol targeting (engine hook strat_vt): V1/V2 DD 28-30, de-risk only 4.32 -> rejected; the dev diagnostic (calm -> higher next-month return, all 4 years) was confounded by the 20% governor. Dev-only, not registered: 2023 DD = one bar 2024-08-05 (sleeve -12.3%); 5th-coin (market-wide) fills: most stops but positive mean; slide ladder vs 24h high: incremental fills ~0/negative. Sleeve knobs exhausted: TP (v248), depth (v249), size by depth (v250), budget (v247), selection (v220/v235/v243), concurrency (v177).
v252 intrabar whale flow from the 1m order-level store (in A members): dev below O1 -> rejected. v253 OKX cross-venue flow: registered, DEFERRED (user: OKX incomplete - starts 2021-10, BNB 2022-12 - keep as option; data kept in data/raw/okxflow_20260929). v254 adaptive ladder spacing by current 1m RV: much worse (buys ordinary pullbacks). Premium/predicted funding INSIDE A was already tested in v231 V2/V3 (worse) - do not repeat.
v255 dip ladder from minute 5/10 instead of 16: neutral (last year identical). OpenCode whale-burst reversal study (dev only, research/diagnostics/whale_burst): 0/108 stable rows, all negative, worse than random entries -> closed. O1 B18 ROBUSTNESS (research/diagnostics/o1_robustness, OpenCode): no losing year in any stress row, win 0.50-0.53 everywhere; DD FRAGILE (base 19.65; cost stress 20.75, latency 30 min 21.08, 60 min 23.18, band shifts 20.4-21.0, cool 12 22.7); bootstrap P(loss year) 1.4%, P(DD>20) 6.8%, P(>=5%/mo) 55%; at 2000 USDT 99% of book and 98% of dip orders placeable. A live bot must act within ~15 minutes of the 4h close.
v256 RL entry-execution bandit (limit offset per opening order, exact counterfactuals): neutral (agent deviates on 5-8%). v257 sequential PPO trader (per-coin simulator, walk-forward, engine evaluation): pure PPO trades win rate for return (win 56.5%, dev4 3.9, median hold 20h - cuts trends, as v214); PPO + rule prior = rule. RL CONCLUSION (10 learned layers): the rules are near-optimal given the information; learned managers either copy the rule or cut the fat-tailed trend trades. Next gains must come from new information.
v258 disciplined PPO (G2 pyramiding simulator, fidelity 0.985 vs engine; cut losers only): worse (win 43-49%, DD 20.6-26.7). v259 PPO daily RISK MANAGER (multiplier 0.5-1.25 on the governor, DD-aware reward): seed 259 passed the whole gate (5y 5.114, last 5.309, DD 17.45) BUT the seed diagnostic (4 other seeds, research/diagnostics/v259_seeds) gives last year 2.3-3.6, dev4 4.5-5.0 -> seed luck, rejected. RULE: every stochastic learner (PPO / NN) must report >= 5 seeds before any claim.
v260 PPO risk manager on block-bootstrapped paths, 5 seeds: median dev4 4.47, last year median 3.13 -> the stable learned policy is plain de-risking (no timing skill); not adopted. v258/v259 audits PASS (no leakage; v259 gate pass genuine for seed 259, seed-unstable). Dev-only diagnostic: BTC-hedging alt dip fills keeps only 15-30% of the edge (the sleeve is a market-rebound bet) -> closed.
v261 direct-reinforcement foundation member (differentiable net Sharpe, policy gradient, 5 seeds): member IC ~0-0.07 -> dilutes (dev4 5.50 / 5.58). RL now tried at every level (sleeve bandits, entry/exit bandits, fitted-Q, PPO trade manager, PPO risk manager, direct-RL member): 14 variants, none beats the O1 rules out of sample.
v262 Binance SPOT order-level flow (2017+, kept store): add DD 22.4, perp+spot sum DD 20.8, dev below O1 -> rejected; all venue / market extensions of whale flow (v237, v238, v244, v262; OKX v253 deferred) raise DD. Data catalog: docs/DATA_CATALOG.md.
v263 meta-labeling of entries (win classifier, skip p<0.35/0.40): +0.04pp dev, win rate unchanged (skips re-enter next bar) - neutral.
NEW BEST CANDIDATE (audit + robustness pending): v266 B1 = O1 B18 + dip-rung stops triggered on a 5m-block CLOSE (bot-watched, exit at the next minute open) + an 8-sigma exchange-native touch backstop: dev4 6.13, worst dev year 3.257, DD 19.70, 5y 5.795, most recent year 4.464 (scored once) - better than O1 on every selection metric and on the unseen year. Origin: dev event study of 2024-08-05 (18 rungs stopped at a liquidation-wick low, then recovery). v265 S2 close5 without backstop 6.178 / 19.29; v264 circuit breaker neutral; B2 (budget counts the 8-sigma stop) 5.725 / DD 18.08.
B1 robustness (research/diagnostics/b1_robustness): return higher in every stress row (+0.27-0.39pp dev4; bootstrap P(>=5%/mo) 60% vs 55%, P(loss year) 1.0% vs 1.4%) but DD worse in 12/13 rows (cost stress 22.8 vs 20.75, latency 15 min 21.9 vs 19.8); bot outage (8-sigma backstop only) safe (DD 18.7). -> v267 selects under a stress-robust rule (dev DD <= 20 in base, cost stress, latency 15).
v267 stress-robust selection (dev DD <= 20 in base, cost stress, latency 15): EMPTY pool - no design (not even O1: cost stress 20.75) holds the stress rows; rule keeps O1. DEPLOYED 2026-09-29 as an extra PAPER pipeline: C5 = v266 B1 (forward_trade --candidate v266_B1, backend history_tm 'v266', FE pipe C5) next to O1 (O1 stays the default / recommended view).
v268 book close stops: DD 21.6-21.9 (touch stays right for the book). v269 close-stop distance: 4 sigma DD 18.27 dev4 6.03 last 4.645 (robust criterion keeps B1); v270 stress rule on it: cost-stress DD 20.23 -> pool empty by 0.23 pp, O1 kept. v271 RL optimal-stopping agent for losing dip rungs (exact returns): early cuts free budget for deeper rungs of the same flush -> DD 21.3, rejected.
v272 = v271 + budget lock: identical results (freed-budget hypothesis falsified; wrong cuts miss recoveries). v273 book target 0.27 / 0.29 on M1: dev4 6.12 / 6.21 but weaker weak years (robust criterion keeps M1); T1 last year 4.684 (best unseen-year score so far, still < 5).
v274 dip TP 1.25 / 1.5 sigma under close stops: DD 26.6 / 27.4 -> TP 1 sigma stays optimal (non-TP rungs fall back).
Dev-only diagnostic (research/diagnostics/dip_carry): holding timed-out dip rungs 4h / 8h past the bar end under M1 rules is not consistent (2021 / 2023 negative, late fills worse, q01 -7..-9%) -> no cross-bar dip holding.
v275 hourly dip ladder WITH close stops: 2022 -35%, DD 44.7 -> hourly dips continue; the hourly ladder is closed for good (3rd failure).
v276 rung size 2.0 / 2.25 on M1: DD 20.5 / 22.0, weak year down -> M1 sits at the frontier.
Dev-only diagnostic (research/diagnostics/dip_funding): M1 dip outcomes by predicted-funding / premium-z quintile flip sign between years (2021 high = worst, 2023/2024 high = best) -> no funding-state sizing of the dip rungs.
v277 aligned dip sizing re-tuned under close stops: neutral ((1.5, 0.5) stays). Close-stop family fully explored (v264-v277).
v278 50/50 sub-accounts of stop designs (B1+M1: 6.08 / 3.11 / DD 18.4; O1+B1: 5.96 / 3.13 / 19.67): no diversification gain over B1.
v279 fill-time dip sizing by pre-fill drop speed (walk-forward terciles): best dev rows ever (F2 dev4 6.25, worst 3.44, DD 18.7) but the most recent year FELL to 3.90 (M1 4.65) - a four-year-consistent dev effect that did not transfer; another warning against dev-mean chasing.
M1 ROBUSTNESS (research/diagnostics/m1_robustness): M1 beats O1 in all 13 paired rows on dev4 (+0.17-0.51), holds DD <= 20 in 8 rows vs O1 7 (latency 30: 18.4 vs 21.1), bootstrap P(>=5%/mo) 59% vs 55%, P(loss year) 0.9% vs 1.4%; bot outage (backstop only) DD 18.7. DEPLOYED 2026-09-29: paper pipeline C4 = v269 M1 is now the RECOMMENDED default on the web (O1 and C5 stay as paper comparisons).
v280 monthly-retrained flow member on C4: dev worse (5.69 / 2.71) but most recent year 4.75 (highest) - rejected by the protocol; 'fresher models help new regimes' stays a hypothesis for prospective evidence, never a selection signal.
DATA LEADERBOARD (research/diagnostics/data_leaderboard, dev only; pooled HGB, 7d target, IC gain over base): all groups mean IC 0.051, Bybit flow and spot flow gain in 3/4 years, positioning (OI / long-short) +0.12 in 2023 but negative 2021/2024, premium and OKX nothing; members A / Aq / B / Bq / C4 books IC 0.070 / 0.052 / 0.068 / 0.057 / 0.057, all negative in 2022. v281 microstructure member (all exchange data) blended 20 / 33%: DD 27 / 34 -> rejected.
v282 FULL-ACTION RL trader (user suggestion: direction, size / leverage up to 150%, reversal, stop / target moved every bar; PPO, 10 seeds): every seed far below the G2 rule (dev4 2.8-4.7 vs 6.13, losing years, DD 22-53). RL now tried from single decisions up to full control; the rule on the pipeline signal stays best.
v283 walk-forward NNLS stacking of members (+ exchange member C): corner weights chasing last year's best member, C weight ~0; dev4 5.42 DD 22.1 -> equal weights (C4) stay best.
v284 spot order flow spliced before the perp archive (+2.5y flow history): worse (5.32 / 5.51 vs 6.03) - spot-era flow differs from perp flow.
*** v285 D2 = 0.8 x C4 books + 0.2 x Coinbase-premium member D (annual + quarterly, v154 / v206 caches) on the C4 rules: dev4 5.864, worst dev year 3.005 (beats C4 2.951 -> robust selection), DD 18.39; final 5y 5.725, MOST RECENT YEAR 5.167, no losing year -> FIRST DETERMINISTIC GATE PASS (hidden win 55.8%). Audit PASS (member D replay bit-identical, Coinbase timing / label / fit windows PASS); robustness: at least as robust as C4 (DD <= 20 in 11 vs 10 stress rows, last year higher in all 15 rows). DEPLOYED 2026-09-30 as paper pipeline CB = RECOMMENDED default (scripts/v285_cb_advisor.py logs the live Coinbase member 'v285_CB' in the fast shadow; forward_trade --candidate v285_D2, paper start 2026-09-30 00:00 UTC).
v286 Coinbase member upgraded with TV / order flow: more similar to A/B, worst dev year and DD worse -> rejected (member diversity > member strength). From v286 on the selection DD filter is dev-only (max yearly 1m DD 2021-2024).
*** v287 PATH-LABEL member (first-touch / triple-barrier target on the O1 features, same window/embargo): P1 = 0.8 CB + 0.2 PA: worst dev year 3.054, dev DD 18.05, dev4 5.683; final 5y 5.586, most recent year 5.200, DD 18.05, hidden win 56.2% -> candidate (audit + robustness pending). Replacing A with the path member (P2) worse (2.70 / 19.5). Next ideas: path labels in the B / D members as extra diverse members; barrier width.
v288 path label in the options+TV member too (Q1 = 0.8 CB + 0.2 four path members): worst dev year 2.57, DD 19.4 -> the path-label gain does NOT generalise; P1's +0.05 worst-year edge is weak evidence. Path-label direction closed.
12h DIP ENGINE (research/diagnostics/daily_dip, dev only): no-stop event study positive every dev year at 3.5-4 sigma (t 3-5, win 75-87%), daily corr with CB ~0; v289 sub-account with 3-sigma TOUCH stops loses 2022/2023 (touch stops turn the edge negative, as for the 4h sleeve); close5 4-sigma + 8-sigma backstop or backstop-only restore positive years but the stream is ~+8%/yr at DD ~8% per 1% risk - mixing it dilutes CB's return unless CB is re-levered -> direction closed. CB drawdown anatomy (research/diagnostics/cb_dd): no single cause (2022 book whipsaws, 2023-04..06 sleeve -11.7%, 2024-07 short book into a +16% BTC squeeze) -> no structural DD filter to buy leverage with.
v290 INFORMATION-SATELLITE SCREEN on CB (20% each, annual + quarterly members; new data: Coinbase SOL/XRP 1h -> per-coin premium Dc): K 2.13/DD 20.4, E DVOL 1.54/21.7, F macro 1.91/18.4, G F&G 2.53/22.3, H COT 3.17/22.0 (DD breach), Dc 2.75/18.2 vs CB 3.005/18.39 -> none accepted; D (Coinbase BTC/ETH premium) stays the only helpful satellite. v291 consensus sizing (CB x agreement of the six model sets): agreement already 0.945 -> neutral/worse. Binance archive: no liquidation history; bookDepth only from 2023-01 (too short for the 2021+ walk-forward).
v292 stress-robust risk level: CB already holds dev DD <= 20 under cost stress / 15- and 30-min latency (its full-path breaches come from the most recent year); lower sleeve budgets raise dev4 but lower the worst year -> CB kept.
RL WITH POOLED EXPERIENCE (the breakthrough, v293-v295): a standalone dip-rung replica (fidelity 98% within 1e-4 vs the engine) gives EXACT counterfactual outcomes for every dip rung of any coin; a causal alt universe U2020 (top-30 non-major USD-M perps by Dec-2020 volume, delisted included, data/raw/alts2020_intraday_20260930) supplies ~38k training rungs (survivorship-free; U2020 alts earn less per dip than survivor alts). Take-profit agent: worst dev year 2.50 (5 majors) -> 2.85 (11 coins) -> 2.93 (35 coins), below CB 3.005 (v293/v294 rejected). *** v295 SIZE agent (x1.5 if both cross-fitted halves predict > 2 mu, x0.5 if both < 0, at the fill; engine hook sleeve_fill_size): S1 dev4 6.275, worst 3.384, DD 17.50, 5y 6.084, most recent year 5.326 -> FIRST learned trader decision that beats the rules; audit PASS; robustness (research/diagnostics/s1_robustness): dev4 higher in all 15 stress rows, DD<=20 in 14/15 vs CB 11/15, bootstrap P(>=5%/mo) 0.62 vs 0.56; executability (research/diagnostics/s1_exec): 5 / 15-min decision lag and sizing once at placement keep the edge; deployed form = sized at the bar open (state at minute 0): 5y 5.987, last 5.266, worst dev 3.425, DD 17.20. DEPLOYED 2026-09-30 as paper pipeline CS = RECOMMENDED (scripts/v295_size_agent.py frozen cutoff 2026-09-11; forward_trade --candidate v295_CS from 12:00 UTC; backend history via artifacts/research/engine_real/v295_size_mult_m0.parquet). Lesson: learned trader decisions need cross-asset experience; next: pooled agents for other decisions (book entry size, dip ladder depth), more coins / venues as experience.
NEW USER GOAL (2026-09-30): DD ~15%, 6-7%/month, win ~60%; step by step, easiest first, DD > 15 not an automatic reject. From v301 on the STEPWISE RETURN-FIRST rule: highest dev4 with dev DD <= ref + 0.5, worst dev year >= 3.0, no losing year, >= +0.05.
v296 J1 = size agent + take-profit agent (pooled 35 coins): worst dev 3.577, 5y 6.105, last 5.451, DD 17.89 (audit PASS); J2 5-action size (skip / x2) best dev4 6.40. v297 risk reallocation (book target down / sleeve budget up): DD 15 only at ~4.7-5.2%/month (frontier). v298 book partial take-profit: grid re-adds -> win rate DOWN; book trades are structurally ~50% winners; all-trade win (book + dip rungs) ~0.66. v299 77-coin pool (whole Dec-2020 perp market, data/raw/alts2020_intraday_20260930, 8.8 GB): mean up (dev4 6.46) but weak / unseen year not; larger HGB overfits. Book-experience diagnostic (v300/book_experience.py): generic trend-trade outcomes unpredictable from context (|rho| <= 0.025) -> not registered. *** v301 G2 = J1 agents + dip budget 0.26: dev4 6.527, worst 3.618, dev DD 17.33, 5y 6.318, most recent year 5.486, DD 17.52; bar-open form (deployable): 5y 6.272, last 5.349, worst dev 3.736, DD 17.09 > deployed CS on every metric. engine_user book_size hook (default-neutral) added.
v302 / v303 FLUSH-BREADTH features for the dip agents (mean / min 30-min move of the five majors, number of majors at their 2.5-sigma bid): five seeds - dev DD 17.33 -> 16.49 (seed-independent: 2021-22 fit on < 10k rows, no early-stopping split), worst dev year 3.618 -> 3.346, dev4 6.601 -> 6.582: a real DD-for-weak-year trade, outside the registered tolerance -> G2 stays (candidate if DD is prioritised: H1, not scored on the unseen year). HGB seed spread of the dev4 is ~0.15 (only 2023-24 move). OpenCode studies (dev only): G2 DD anatomy (research/diagnostics/g2_dd) - half of the DD is the book's one-way concentration (all-long into -11% BTC, net-short into +16% BTC), half is dip flushes (10 flush bars = 51% of stop losses, but the sleeve earns +217 on other bars); mechanical levers (vol x0.5, flush-skip, budget cut in DD) buy no material DD (budget cut in DD even +1.6). Second stream (research/diagnostics/second_sleeve): a learned 12h / 1d dip sleeve is positive but weak (12h dev4 1.55, DD 33; 1d has a losing year); blends with G2 lose return at similar DD -> closed. v304 LADDER DEPTH: adding a 2.0-sigma rung (agents retrained on that rung set) lifts dev4 6.527 -> 7.807 (rungs 4073 -> 7022) with dev DD 17.33 -> 20.25; a 5-sigma rung adds little and raises DD; both -> DD 28.9. v305: on the 2.0 ladder, sleeve budget 0.22 / 0.18 and book target 0.22 all leave the 2021 DD at ~20.2 (dev4 7.03-7.25): the shallow-rung DD is not a risk-scale problem (one episode, 2021) -> OPEN LEAD: find that 2021 episode (OpenCode DD anatomy of R1) and a rule for it; R1 is the best return source not yet deployed.
TWO PRODUCTS (user 2026-10-02): MANUAL = book only (floor 5%/mo, DD<20, book win>=55%; then 8/15/60) and BOT = book + dip (8/15/65). MANUAL G2 books: dev4 2.50, 2021 losing, win 50%; the old flat book frontier was the vol-scale cap 2 (cap 4 t0.37: 4.29 / DD 21.1, no losing year). Book anatomy (dev): all profit from longs held > 4 days (TP exits), shorts ~0 but hedge 2021, close exits win 48%. EVOLUTION (v306 BOT, v307-v309 MANUAL): walk-forward GA, fitness only on years before the test year, judged vs the best seed on the unseen year; one training year overfits (v306 fold 1); 2+ years transfer (v307 fold 2: unseen 2023 5.3-5.8 vs seed 3.24). Infra: v306_gene_tables (bar-open dip-agent predictions for rung sets G2/R1/U), kpack (Kaggle CPU bundle of engine_user + prepared arrays + member caches), engine_user gov hook.
*** MANUAL BRACKET DIPS (v338-v342, audits PASS): a human can place plain limit buys with TP limit + exchange-native touch stop attached; one at 3.0 sigma per coin (v338 MD30) lifts MANUAL dev4 3.01 -> 3.91 and transfers; book x0.75 + dip x2.5 (v340 RA2) transfers (DD 16); v339 depth/size and v341 vol target 0.28/0.31 fail transfer (leverage again); v342 L2 = bracket limits at 3.0 + 4.0 sigma transfers: 5y 5.53, last 4.54, DD 19.71 (M2 books). Deployed on CB books as paper pipeline M3 (replay dev4 6.233, 5y 5.925, last 4.704, DD 17.73; research/diagnostics/l2_robustness: cost stress DD 20.3, latency 60 breaks). From v343 the MANUAL reference = L2 on CB books.
v343-v370 (2026-10-03, kpack 4 s/sim): M3 local optimum on depth pairs, book share, stop distance, member-weight GA, 1296-rule dip grid, hour multiplier, M3-rule / richer-state agents, quarterly-basis data (OpenCode fetcher, DD 22.9), governor, vol target, cap, shorts, entry depth, 3rd rung; BOT: hedged dips (sleeve_hedge hook), sub-account blends (R2 alone wins), tighten rule, book SL/TP all keep R2. MANUAL gains: book SL 5 / TP 10 (M4, plateau along TP 10) and loss_act tighten (M5, book win 0.66, plateau over tighten 1.0-2.0). Dev studies closed: rip-fade sells, dip refills after TP, hedged dips (half the edge is idiosyncratic).
REGISTRY NOTE (2026-10-03): v309-v313 ran OUTSIDE the registry (slot backlog while v305 / v307 awaited audits; versions must be monotonic). Each has its docstring hashed before the run (vNNN/prereg_sha256.txt) and Kaggle runs record cloud_submission.json. Registered in order: v306, v307 (audit PASS), v308, v314 (audit PASS), v315 (audit PASS); next registry version = v316 - register BEFORE running from now on.
v314 risk dial (target x cap walk-forward): dev folds transfer, dev4 choice t0.44 cap5 -> most recent year 0.50 %/mo DD 30.6 (leverage not general). v315 pullback entry 0.75 sigma_4h / 3 bars: transfers, 5y 3.02, last 3.29, DD 18.5, no losing year = best general MANUAL (M1 reference). v307 final M: dev4 5.49 / DD 19.7 / win 57 but last year 0.10 / DD 28 (TRANSFER failed). v312 GP alpha member G: corr 0.94 with A, small add-on gain.
BOT R2 (v321): walk-forward best-seed choice -> R2 = G2 + 5-sigma rung, agents fit on all depths (v306 fit U): 5y 6.79, last 5.66, DD 18.39, win 0.66 -> paper pipeline v321 (forward_trade --candidate v321_R2; backend catalog v321, history table v321_r2_table_m0). POOLED EXPERIENCE for books (v316/v317): +IC in 3/4 dev years; pooled path-label (PP) / flow (PF) members have good IC but WORSEN the book (v319). Member-weight GA v320 running. MANUAL floor still open: best general M2 3.16 / 3.76 / DD 20.6.
v322-v326 (2026-10-03): theta x target on M2 (higher theta hurts; target 0.37 -> full DD 24), R2 + book pullback / loss_act (folds keep R2), pooled efficiency-ratio overlay (IC > 0 every year but tilting the book hurts), R2 with 77-coin dip agents (no gain, as v299), pooled 77-coin GRU on Kaggle GPU (IC well below the tree PT; 5th DL failure) -> M2 (MANUAL) and R2 (BOT) unchanged.
R2 ROBUSTNESS (research/diagnostics/r2_robustness, OpenCode): R2 beats G2 on return in all 17 stress rows, no losing year anywhere, bootstrap P(>=5%/mo) 0.71 vs 0.65, P(DD>20) 0.066 vs 0.074; but DD <= 20 in 14/17 vs 16/17: bot outage (native 8-sigma stop only) 22.2, latency 60 21.2, offset 0.40 20.7 -> R2 needs a reliable bot; G2 is the safer fallback. v327 BOT sub-account ensemble -> R2 alone (no gain); v328 fill-time agents (+ breadth) no gain; v329 alt spot-history prefix for the pooled member: IC worse (spot era differs, as v284).
M2 MANUAL ROBUSTNESS (research/diagnostics/m2_robustness, OpenCode): human latency matters - 15 min 2.97, 30 min 2.83, 60 min 2.39 (DD 23), 120 min 1.70 (DD 26) 5y %/mo; missing one decision a day 2.71 / DD 22.3; bootstrap P(>=5%/mo) 0.19, P(loss year) 0.075; placeable at 1000 USDT 95%. v334 tighter governor on R2 raises DD (20.4) -> rejected.
PLATEAU: every management layer lands at dev4 ~5.1-5.3 and last year ~3.8-4.0 at DD ~19 -> the foundation signal is the limit.
v223-v228 (all rejected, D2 stays): foundation component mixes slower/faster (0.25/0.25/0.5 local optimum), no long-only + trim
(best worst year 2.47 but dev4 4.97), member D / monthly schedule, causal coin bandit for the sleeve (DD > 20), deeper limit
offsets (non-monotone noise). Dev-only diagnostics: time-of-day / weekend dip effects unstable; per-coin sleeve XRP/SOL best, BNB
weakest. D2 robustness (research/diagnostics/d2_robustness): no losing year under cost stress, 15-60 min latency or any single
parameter shift; latency costs ~0.6pp/month at 30 min -> pipeline cycle now runs 1 minute after the close.


USER-RULE ENGINE (engine_user, 2026-09-27; limit entry + SL market + TP limit per position, maker 0.02% / taker 0.055%, adverse funding, no carry; selection on first four years): v188 v154+sleeve SL m=4: 5y 3.53, last year 3.55, DD 19.0; v189 comparison selects v151+sleeve (dev4 3.90) -> 5y 3.58, last year 2.34, DD 19.4. Gate needs 5y >= 5, last year >= 5, no losing year, DD <= 20. Then: v190 bracket (triple-barrier) targets rejected (2022 IC ~0); v191 sleeve rung stop 5 sigma best (dev4 4.05); v192 book limits resting the whole bar (4.07); v193 STOP-RISK sleeve budget X=0.08: dev4 5.046 (first >= 5), DD 19.3, 5y 4.60, last year 2.85 (+40%) -> fails on last year; v194 sleeve TP 1 sigma stays best; v195/v196 books-vs-sleeve allocation: keep books at 0.25 (sleeve is capacity-limited by rung size); v197 rung size x1.5 with budget 0.12: dev4 5.562, DD 19.32, 5y 4.996, last year 2.761 (+38.7%) -> BEST under user rules; fails only on the most recent year. v198 TSMOM blend hurts every year. v188 audit -> engine fix: 1m DD peaks include intrabar highs, stop wins same-minute ties; v197 re-scored DD 19.72 (v199). v199 ladder to 6 sigma: dev4 5.71 but DD 20.27 (excluded). v200 closer book SL/TP (user range) hurts (DD > 20); v201 hourly ladder fails (DD 39.7); v202 quarterly retrain helps weak years but DD 22.5; v203 annual+quarterly ensemble dev4 5.52 (better worst year, not selected under the mean criterion). ROBUST CRITERION from v204 (worst dev year). v204 sleeve aligned with book direction (x1.5 long-book / x0.5 otherwise): dev4 5.87, 5y 5.33, last year 3.21, DD 19.46 (gain carries to the unused last year). v205 annual+quarterly book ensemble + aligned sleeve: dev4 5.82, worst dev year 3.41, 5y 5.49, LAST YEAR 4.15 (+63%), DD 19.76 = NEW BEST (fails only on the last year; audited). v206 +member D and v207 +monthly schedule both worse (DD > 20). OVERFIT WARNING: dev4 rose 3.90 -> 5.56 across v189-v197 while the untouched last year only moved 2.34 -> 2.76.

| candidate | normal / fee / execution %/month | full-path DD | hidden year (strict 1m exec) |
|---|---|---|---|
| **v183 = ladder + TP maker exit at L(1+sigma) + budget on OPEN sleeve notional (audited)** | 4.28 (stress 3.88) | 18.8% 4h / 19.0% 1m (stress 19.1) | +67% |
| v179 = v178 + stress budget on sleeve notional (<= 1/6 equity, ex post) | 4.14 (stress 3.73) | 18.2% 4h / 19.8% 1m | +68% |
| v178 = selection-free ladder of limit bids (2.5/3/3.5/4 sigma) inside the vol target | 5.51 (stress 4.79) | 18.6% 4h / 27.8% 1m-marked (2025-10-10) | +106% |
| **v176 = v154 books + v170 exec + v175 limit dip sleeve inside the portfolio vol target (audit pending)** | 0.25: 5.24 | 20.7% (2021) | +123% |
| v175 = same, sleeve outside the vol target (audit pending) | 0.25: 5.63 | 22.8% | +119% |
| v172 = taker-entry dip sleeve, crash-aware slippage (audited) | 0.25: 4.60 | 22.4% | +92% |
| **v154 + v170 execution (60-min rest) on engine_real, audited** | 0.25: 3.80 | 18.9% close | +64.7% |
| **v154 on engine_real (actual signed funding, real carry fees, capital budget, min notional; audited PASS)** | 0.25: 3.71 | 18.9% close / 19.0% true 1m-marked (v169) | +63.0% |
| **v154 = (v144 + options + Coinbase-premium books)/3, realistic engine, 20% governor** | 0.25: 3.52; 0.28: 3.67 (v155, ex post) | 19.2% / 20.0% | +56.3% (0.25) |
| v151 = 0.5 v144 + 0.5 v150 (options-flow) books, realistic engine, governor, target 0.25 (ex post)** | 3.53 (realistic 1m path) | 19.4% | +36.5% |
| v152 frontier with a 30% governor (user decision) | 0.30: 3.76; 0.35: 3.93; 0.40: 4.09 | 25.0-25.3% | cap 2x binds |
| v144 deploy v3 = v142 xs books + 10 bps limits (1m) + v110 governor, target 0.25 (ex post)** | 3.37 (realistic 1m path) | 19.6% | +41.3% |
| v142 xs features (v133 pipeline, flat fees) | 2.55 / 2.33 / 2.06 | 16.3 / 17.2 / 18.3% | +31.2% |
| v133 deploy v2 = tranched + vol-forecast sizing (best honest)** | 2.44 / 2.22 / 1.95 | 15.2 / 16.6 / 18.4% | +29.0%, DD 10.1% |
| v133 + v135 limits 10 bps, realistic 1m execution 5y | 2.24 (single realistic path) | 16.3% | +30.5%, DD 9.7% |
| v137 realistic frontier (ex post) | target 0.17: 2.49; 0.19: 2.73; 0.21: 2.93 | 17.9 / 19.3 / 20.3% | |
| v127 = v115 tranched (deployable, luck-free) | 2.38 / 2.16 / 1.88 | 16.8 / 18.2 / 20.2% | +30.2%, DD 10.0% |
| v115 phase mean (v126) | 2.31 / 2.09 / 1.82 | up to 20.9 / 22.4 / 24.3% | phase 0: +36.0%, DD 10.3% |
| v129 vol-forecast sizing (phase mean) | 2.37 / 2.15 / 1.88 | 19.8 / 21.2 / 22.8% | - (small real gain, adopt next) |
| v120 frontier (v118 band 0.05) | target 0.15 -> 2.68 normal; 0.18 -> 3.06 at DD 20.4-21.4% | | ex-post risk dial |

FRONTIER (v186_frontier.py, ex post diagnostic, engine_real + sleeve, gate DD = max(4h, 1m)): target 0.25/0.28/0.31/0.34 -> majors sleeve 4.28/4.51/4.62/4.73 %/month at DD 19.0/20.0/21.7/22.5; 11-asset sleeve (research only) 4.29/4.44/4.57/4.64 at 17.7/18.7/19.8/21.1; stress ~0.4-0.5pp lower. CORRECTION (v187): at target 0.25 the 2x cap rarely binds (mean scale ~1.5); a confidence-gated 2/3/4x cap with Binance margin + 1m liquidation checks gives 4.33 (no liquidations) - the governor/DD, i.e. the return/DD ratio, is the real limit; more risk adds ~0.1pp per step. Ceiling ~4.5%/month at DD 20% (normal), ~4.0% (stress). Newer: v184 hourly ladder 3.89 (crowds budget), v185 sleeve outside governor 4.31 (neutral), v186 11-asset sleeve 4.29 at DD 17.7.

Gate (5%/month at DD <= 20% in all scenarios) not met. v148 bootstrap of v144 (target 0.25): median 1y +45%, P(DD>20%) 19%, P(loss) 8.5%, P(>=5%/month) 24.5%; at 0.15 ungoverned P(DD>20%) 5.4%, median +30%. Frontier: 5%/month would need DD ~35-40% with the
current signal (IC ~0.1 at 7d, ~0.05 at 1d; Sharpe ~1.5-1.9).

## Building blocks (audited, reuse via importlib from `research/parallel/rounds/parallel-20260906-r2/`)

- `v92/v92_pooled_hgb_vt.py`: pooled 5-majors 4h panel (`build`, `features`, `load_asset` with 2017 spot prefix),
  7d vol-normalised target, `train_predict`, `weights_from` (long-only, daily ribbon gate), `vol_target_scale`
  (20%, cap 2), `simulate`, `stats`, `SCEN`, `ANCHORS`, `EMBARGO_BARS`.
- `v94/v94_long_short_ensemble.py`: horizons 18/42/84 ensemble, `add_targets`, `weights_ls` (long/short).
- `v103/v103_flow_short_horizon.py`: 1d/3d targets + order-flow features (`build`, `flow_features`, `train_predict`,
  `evaluate`, `FLOW`, `HS`, `EMBARGO`).
- `v113/v113_longer_history.py` + `v114/v114_bitstamp_history.py`: extended panel (Bitstamp BTC 2013 + Coinbase BTC
  2015/ETH 2016 + Binance). Pattern: `ext = v115.v114.v113; v115.v114.v113.cb_bars = v115.v114.cb_bars_ext;
  ext.v92.load_asset = ext.load_asset_ext; p92 = ext.v92.build()`.
- `v115/v115_candidate.py`: `books_v115()` (0.25 v92 LO + 0.25 v94 LS on the extended panel + 0.5 v103 LS).
- `v110/v110_dd_governor.py`: sequential portfolio engine `run(panel, books, target, governed, fee, slip)` +
  `summarize` (80% books + 20% carry x3, portfolio vol target, cap 2; full-path DD).
- `v104/v104_candidate.py`: `fill_strict` (strict 1m execution), `HIDDEN`.
- `v125/v125_tranching.py`: `raw_lo`, `raw_ls`, `phased(W, phases)`; `v129.phase_mean(ext, p92, p103, lo, ls, fl)`.
- `v118/v118_no_trade_band.py`: `run_band` (per-asset no-trade band).
- Data: `data/raw/ma_ribbon_20260924` (BTC perp), `xs_universe_20260924` (other perps), `spot_majors_20260925`
  (spot 4h/1d + 2017 prefixes + 1h prefix), `majors_intraday_20260924` / `btc_intraday_20260924` (1m/15m/1h),
  `coinbase_20260925`, `bitstamp_20260925`, `bybit_20260925` (funding), `artifacts/research/carry/carry_oos_fee0.0004.parquet`.

## Evaluation standard (2026-09-26, user: match reality)

GATE DD = max(4h-close full-path DD, 1m-marked full-path DD incl. open sleeve positions). Stress row = maker 0.0004 / taker 0.0007 + 5 bps on taker fills.

`engine_real/engine_real.py` (`evaluate(books, opens)`, cached v154 books in artifacts/research/engine_real/): v144 loop +
actual signed Binance funding at the t+2 settlement, carry with spot 0.1% + perp taker 0.05% and t+2 funding, capital
budget (spot cash + perp gross/5 <= 95%), min notional at 10k USDT, intrabar DD bound. Ablation on v154: funding +0.20pp,
carry +0.02, budget -0.04, min notional 0. engine_real audit PASSED (bit-exact, funding timing verified). Report both engines for new versions.

## Tried and rejected (do not repeat without a new hypothesis)

Patterns (candles/chart), indicators, MA S/R bounces (15m-1d), 4h/weekly MA-ribbon features (v123), seasonality,
macro, DVOL, on-chain, positioning, breadth, ORB, pairs, lead-lag, capitulation; deep sequence models (v90 Kaggle
TCN+Transformer IC ~0); rich cross-asset features (v95); ExtraTrees/HGB ensembles (v97), bagging (v121); recency
weights (v98); 4x phase-shifted rows (v100); training on 13 alts (v101); market-neutral XS books (v102);
intrabar 1h features (v107); rebalance every 4h/12h (v108) or slower (v117); trailing-IC gate (v109);
Coinbase premium (v111, unstable); sign classifiers (v112); nested-CV hyperparameters (v119); 28-day book (v122);
no-trade band (v118 gain vanishes under strict execution, v124); tranching as a return booster (v125 = luck-free
level); halving-cycle features (v128, memorises 2-3 cycles); spot-vs-perp flow/basis (v130); signal-strength
leverage (v131, just more exposure); nested permutation feature selection (v136: 1.97%/month, worse); HGB+ridge blend (v138: 2.08, ridge IC unstable); Binance positioning metrics OI/long-short (v139: IC up 2022-24 but hidden year down, 2.42 vs 2.44); forward-Sharpe targets (v140: 1.37); cross-asset attention NN (v143: IC negative 2021-22, blend 2.36); xs features for ALL features (v145: 2.20, dilutes); relative positioning (v146: 2.52, DD 25%); 12h horizon in v103 (v147: neutral 3.33); xs vol forecast (v149: neutral); ensemble members that DILUTE: positioning (v153), DVOL (v156: 2.98), macro (v157: 2.94), ETH options added to the options member (v158: 3.44), Fear & Greed (v159: 3.34), CFTC COT (v160: 2.68); options flow alone (v150: 3.47/19.2 but hidden year +27% vs +41%); bear-only shorts (v134: lower DD 12.8% but 2.30%/month, hidden year +21% - diagnostic-motivated, keep only as a prospective hypothesis); trading DOGE/TRX/ADA as extra assets (v132: 2.13%/month, DD 24%, new assets IC ~0-0.04); cross-venue funding arbitrage (Binance vs Bybit, 0.1-0.3 bps/8h now); deep tabular MLP-PLR + FT-Transformer member on Kaggle (v165: IC ~0.03, val loss best at epoch 0, (A+B+D+E)/4 3.41 vs 3.52); agreement confidence (v166: neutral 3.55); quantile-HGB uncertainty sizing of v103 (v168: 2.67, median model loses signal; audit: median-only 2.66); 1m intrabar portfolio stop at k*sigma (v169 on engine_real: k=3 2.71, k=4 3.05, k=2 2.02 vs 3.71, DD not lower - intrabar dips mean-revert); GRU over 42 4h bars on Kaggle (v167: IC ~0/negative 2021-24, blend 3.15; 4th DL failure); funding-settlement microstructure (research/diagnostics/funding_settlement, PRE-ANCHOR data only: post-settlement +17 bps sits in the settlement minute itself, from S+1 only +4 bps gross = -10 net; pre-settlement effect only with the unknown final rate = look-ahead, -3 bps with the known previous rate) - rejected without touching test years; v177 sleeve concurrency cap (4.71/21.1); v180/v182 rebound gates (selection is not the binding constraint; budget is).

## What worked (keep)

Pooled majors HGB (v92), 2017 spot prefix, causal vol targets, long/short horizon ensemble (v94), blending books
(v96), funding carry sleeve (v99), 1d/3d order-flow model (v103, +0.5pp at short horizons), longer history
(v113/v114), vol-forecast sizing (v129, small), 10 bps limit execution (v135), selected cross-sectional features (v142, +0.11pp), realistic governor at higher risk (v141/v144), actual funding in the engine (engine_real, +0.19pp), 60-minute limit rest window (v170 audited: 3.80 vs 3.71, maker share 0.64 -> 0.81, all years better).

## Idea queue (next)

- NEW LEAD (v171, audit pending): intrabar dip-reversal sleeve on 1m data (buy after close <= -k sigma of the 4h open in minutes 16..238, exit next 4h open, taker both sides, k walk-forward): sleeve alone +8..+65%/yr, DD 7-9%, corr 0.04 with v154; v154+sleeve 5.96%/month but DD 21.85%. Robust to 10 bps slippage and 1-5 min delay (ex post diagnostic); top events are real crashes. v172 = crash-aware slippage + v170 execution. v173 learned rebound model: IC 0.08-0.17 but pred>0 too lax (3.98/25.1, rejected). v174 spike fade: spikes do NOT revert (rejected). v175 limit bids (maker on trade-through) let k 2.5-4 pay: 5.63/22.8. v176 sleeve inside the vol target: 5.24/20.72. Prospective log: scripts/dip_sleeve_forward.py (limit k=3.5 and taker k=4, FREEZE 2026-09-26 16:00 UTC, matches research events exactly).

- Information-diverse ensembles work only with members that are good alone (options, Coinbase premium). Next: ETH options (download running to data/raw/deribit_opt_20260926/ETH_options_4h.parquet) as part of the options member (v158).
- v151 frozen: scripts/v151_advisor.py (+ scripts/deribit_options_update.py appends live 4h options aggregates each run; backup BTC_options_4h.backup_20260926.parquet), logged as v151_deploy_v4.
- Data added: data/raw/deribit_opt_20260926 (BTC options trades aggregated per 4h, 2019-2026; research/mj/fetch_deribit_options_4h.py).

0. Frozen advisors: v154 (scripts/v154_advisor.py, best: base + options + Coinbase model sets; updates Coinbase/spot via scripts/coinbase_spot_update.py and Deribit via scripts/deribit_options_update.py each run), v151, v144 (scripts/v144_advisor.py, ungoverned weights at target 0.25; apply the governor on paper equity). Data added: data/raw/um_metrics_20260926 (Binance metrics 5m, BTC 2020-09+, others 2021-12+).

1. Execution adopted (v135): rest limits 10 bps better than the 4h bar open, market fallback at minute 15 (+~2pp/yr). 1 bp of cost per unit turnover ~ 0.055 pp/month.
2. Deployment v2 (v133) is frozen: scripts/v133_advisor.py (vol models artifacts/research/advisor_shadow/v133_vol_models.pkl, cutoff 2026-09-08), logged as v133_deploy_v2.
3. Kaggle (with authorization) only for a materially new model on the extended panel; DL has failed so far.
4. More history for XRP/SOL/BNB (other venues) if a source with clean hourly data exists.

### Screen criteria (2026-10-06, from placebo studies)
- Dip replica screens: PROMISING legs (4-phase sum >= base 4/5 AND DD within 1 pp 4/5) let 6.7 % of placebo rules pass
  (oc_placebo_dip); additionally require 5y 4-phase-mean sum delta >= +0.273 (placebo p95, ~3.5 % of base) -> FPR 0.7 %.
- Book vectorised tilts: two PROMISING tilts (expiry, CME gap) failed the full engine; oc_placebo: require legs + placebo P&L pct >= 95 AND DD pct <= 5 (joint FPR 0.2 %);
  exposure tilts must also beat an exposure-matched control + timing placebo (oc_premexpo: USDT premium passed, CB premium did not).
- Carry: cash-and-carry with quarterlies (oc_cashcarry) = useful add-on +0.21/+0.42 %/mo at f 0.25/0.5, near zero DD; combo pending.
