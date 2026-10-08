# Báo cáo cuối cùng (VI) — 2026-10-06 (hợp nhất)

## 0. Bổ sung 2026-10-09 (đọc trước; nội dung cũ bên dưới giữ nguyên)

Phạm vi và nguồn số như §1 cũ (walk-forward 5 năm, reset 1/4 vốn mỗi anchor, gate Bybit maker 0.02%/taker 0.055%, long trả 0.01%/8h). Mọi số dưới copy nguyên văn từ docs/CLOSED_DIRECTIONS.md (hàng 2026-10-08) và REPORT.md/COMPARISON.md được dẫn ở đó; không có số mới. Chi tiết ở docs/SUMMARY_FOR_OWNER_20261009_VI.md. Bốn hàng kiểm chứng B7 đã về đủ trong ngày (đợi ~1h, check mỗi 15 phút) nên không còn mục "đang chạy".

- Triển khai không đổi: G2 + carry quý f=0.25 (paper only). Kỳ vọng trung thực Bybit (oc_c2carry): G2+carry 5.111/full-DD 17.93; K2+carry 5.199/17.26; C2+carry 5.342/16.35; năm gần nhất có carry 4.493/4.602/4.607 (cả 3 < 5) — mốc 5%/tháng chỉ còn trên giá Binance (G2+carry 5.634/16.66).
- Họ tilt FM/vol là vol-timing theo regime, gãy ở nhịp crash: C2 đều nhất 7/9 năm presample (chỉ thua 2020p −0.159 và 2021 −0.018), Bybit 5y 5.115 vs 4.883 (full DD 16.50 vs 18.09), audit_c2 PASS-WITH-NOTES; live feed C2 + runner d17bfg2ch từ 2026-10-07 23:11 UTC; beargate/tiltgate/crashgate ĐÓNG; chỉ prospective (scripts/fm_paper_eval.py) mới cho chuyển.
- Cascade boost B7: dev4 6.74/W 2.96/DD 17.92, 5y 6.36, năm labelled 4.88 — nhãn CONTAMINATED; kiểm chứng đủ: exposure giải thích 74%/67% (timing ~0.3) [oc_cboostctrl], unseen 2017–2020 giúp 3/4 (gãy COVID) [oc_cboostpre], ma sát Bybit +1.023 nhưng full DD 20.31 > 20 [oc_cboostbybit], audit PASS exact 53,877/53,877 [audit_cboost], MANUAL CLOSED (KM_B7 5y 3.817, full 22.99) [oc_cboostmanual]; dạng deploy được là B7C2 (Bybit 5.685/17.43); còn thiếu paper prospective.
- Đóng trong ngày: IDEAS5 cả 10 (kể cả D1 pick dev4 5.776/W 2.921 nhưng rho train ~0 đảo dấu → sign luck, không runner), IDEAS6 cả 8, IDEAS7 quanh B7 cả 6 (giữ B7 phẳng), dip1h, shortmember, horizonfix (leak thước IC cũ, book đứng yên), kronosfeat, fmbookic, bybitfill, c2frontier/k2carry/k2parity/c2manual/k2manual.
- Ops: bot_exitstuck FIXED (have() poll trước vòng exits, không hủy market resting; soak 3532→0); oc_paperrecon khớp entry/bảo vệ (1043 episode, 34 fill hai phía, diff 0.0000) nhưng 20 dip exit gửi 420 lần rồi cancel ~25ms (+9.23 USDT may) nên timing exit chưa phải bằng chứng; outage backend 2026-10-07 xem PAPERFIX_20261007 + keepalive KEEPALIVE_20261007 (OWNER đăng ký); DB giữ snapshot=false.
- Chủ tài khoản theo thứ tự: (1) OWNER đăng ký keepalive; (2) review fix exitstuck rồi restart runner; (3) nuôi prospective 26 tuần, chấm bằng scripts/fm_paper_eval.py.

## 0. Bổ sung 2026-10-08 (đọc trước; nội dung cũ bên dưới giữ nguyên)

Phạm vi và nguồn số như §1 cũ (walk-forward 5 năm, reset 1/4 vốn mỗi anchor, gate Bybit maker 0.02%/taker 0.055%, long trả 0.01%/8h). Mọi số dưới copy nguyên văn từ docs/CLOSED_DIRECTIONS.md §11+, docs/FRONTIER_MAP_VI.md và REPORT.md/COMPARISON.md được dẫn ở đó; không có số mới. Chi tiết ngắn ở docs/SUMMARY_FOR_OWNER_20261008_VI.md.

- Triển khai không đổi: G2 (R2B1D17BF + trần dip 2.0x) + carry quý f=0.25 một UTA. Kỳ vọng trung thực giờ TÍNH CẢ gap giá Bybit: G2 giá Binance 5y 5.410/full-DD 16.82 (dev4 5.601/W 2.588/DD 16.91; năm gần nhất 4.648/12.90) vs giá Bybit S5 5y 4.883/full 18.09 (dev4 4.994/W 2.129/DD 18.11; năm gần nhất 4.443/12.37); gap dev4 0.607 (2023 1.113, các năm khác 0.300–0.547), 5y 0.527, năm gần nhất 0.205; DD rộng +1.27pp [oc_bybitgap §0; oc_amihudrobust §0–§1]. Nghĩa là mốc 5%/tháng chỉ còn đạt trên giá Binance; live Bybit kỳ vọng ~4.88 là RỚT mốc. Carry +0.224 (G2+carry 5.634/16.75/16.66, năm gần nhất 4.698 [oc_carrycompound; FRONTIER_MAP_VI]) cũng đo trên giá Binance. Book khớp gần hệt (fill Bybit +2/+14, giá median <1bp); gap nằm ở thang dip (−25/−57 fill, −34/−59 TP, TP-rate −0.4/−0.6pp) + dư sizing, phân tán mọi coin (basis chỉ BNB lệch −3.6bp; sigma Bybit/Binance ~1.00; P(fill chéo) 95–99%), không pre-register fix venue nào [oc_bybitgap §1–§6].
- Đã xác nhận: book là timing không phải beta (timing +3.25 năm 2021, +1.82 năm 2022, placebo 96.8–100, beta 0.05–0.14; book-only net 2.531, DD 18.96) [oc_bookattrib]; skill ở h=1..18 bar (pooled IC +0.02..+0.04, 4/4 năm dev mọi member, recent +0.036 h=1; h=42 đảo 2022) [oc_bookichorizon] (ĐÃ KIỂM 2026-10-08, oc_horizonfix: thước đo cũ có rò rỉ nến t nhưng với book đã triển khai sai lệch chỉ −0,001..−0,004; kết luận GIỮ NGUYÊN — sau sửa h=1 vẫn +0,017..+0,018 dev, +0,033 năm gần nhất); ablation giữ B1/close5/cap/governor (bỏ B1 maxDD 23.65/full 20.20; cap off gap 32.9→60.9%; governor off 20.04/19.60; VT +0.86/−DD; bear ≈0) [oc_ablation]; không decay (fresh−stale +0.013/+0.002, nhiễu ~0.04; retrain năm đủ) [oc_staleness]; feed dư thừa (bỏ mỗi member dev4 +0.01/+0.02, DD +0.5 lên 17.32/17.41; outage 3 ngày ≈0 ±25bps) [oc_memberdrop]; dip khái quát hóa 2017–2020 (2018 2.50/8.4; 2019 0.48/11.3; Y2017 10.71/5.04; Y2020p 0.27/17.52, s1 COVID 24.5; B1 halved DD; KD13<G2<KD20 đơn điệu; cap inert; TP1.5 lãi hơn/DD hơn; touch chỉ thắng COVID) [oc_presample; oc_presample2].
- Lead mới duy nhất Kronos K2 (tilt dip Kronos-small S=64, risk −low1, ×1.25/×0.75): Binance dev4 5.772/W 2.469/DD 16.20/full 16.09 vs G2 5.601/2.588/16.91/16.82 (+0.171); năm sạch 4.801/12.10 vs 4.648/12.90 (+0.153); 5y 5.577 vs 5.410 (+0.167) [oc_kronoshidden; audit_k2 PASS-WITH-NOTES khớp từng chữ số]; Bybit S1–S5 hơn G2 cả 6 ma sát (dev4 +0.08..+0.27, năm sạch +0.10..+0.20, 5y +0.09..+0.26; S5 5.077 vs 4.994 / 4.972 vs 4.883, full 17.41 vs 18.09) [oc_k2bybit]; placebo timing 97.2/block 98.7 [oc_k2placebo]. Chưa triển khai vì worst dev 2.469<2.588 (robust chọn G2) và năm sạch 4.801<5.0 rớt gate; runner paper_d17bfg2k2 + scripts/kronos_shadow.py hourly đang thu prospective [oc_kronoshidden; oc_k2bybit; BOT_K2FLAG_20261007].
- Bug/ops: exit-cancel cb14cb7 (chưa fix 3 piece BARE; có fix ≤2 cycle, 10 test) [BOT_EXITSOAK_20261007]; dust 0.0999…→S/T 0 (fix qty 0.1, soak 5.5h 0 dust, 4 test) [BOT_DUSTFIX_20261007]; carry-mark 63d65bd (d17bfg2c ~5,039 vs twin ~5,030, lỗi kế toán) [CARRYGAP_20261007]; keepalive AlphaLabRunnersKeepAlive + watchdog backend, ExecutionTimeLimit=0, OWNER đăng ký [KEEPALIVE_20261007]; chân trời bằng chứng 26 tuần (8w zero-edge PASS 38.3%/lỗ-1% 32.0%; 26w 13.7%/8.1%; 52w 2.5%/1.0%) [oc_paperpower].
- Đóng 2 ngày (mỗi họ một dòng): VRP cả họ CLOSED KHÔNG DEPLOY (V2 3.441/−0.165/25.82; k0.97 overlay 6.566/4.365/16.10; R087 overlay 5.740/3.578/17.22; Z2 0.632/14.01; VRP-gate +0.139; strike thật −0.99/3 năm lỗ/35.9; headline +1pp là bias DVOL ~0.87x; chỉ còn ledger paper) [oc_vrpstraddle; oc_vrprobust; oc_vrpconsistent; oc_vrpstrangle; oc_vrpgate; oc_vrpstrike; audit_vrpstraddle]; GEX level+change 2/4 ĐÓNG [oc_gex; oc_gexchange]; IV-term |IC|≤0.11 ĐÓNG [oc_ivterm]; option-flow |IC|≤0.009 ĐÓNG [oc_optflow]; HL-funding +0.40/+0.28 rồi −0.07 ĐÓNG [oc_hlspread]; ETF T1/T2 5.375/5.313<5.410 ĐÓNG [oc_etfflow]; stablecoin G1 5.537<5.601<CTRL 5.699 ĐÓNG [oc_stablegate]; USDT-depeg +0.001 ĐÓNG [oc_usdtdepeg]; literature FHL M1 recent 3.89 vs 4.65 ĐÓNG + calendar V1 4.304 vs 4.648 ĐÓNG [oc_lit_fhlh; oc_lit_calendar]; Amihud A1 5.844/2.798/16.81 nhưng S5 −0.005/DD 21.32 KHÔNG DEPLOY, AB1_S5 +0.045/DD 22.48 ĐÓNG [oc_lit_xs; oc_amihudrobust; oc_amihudbybit]; MVRV M1 6.192/16.26 nhưng book riêng 2.461<2.531 (tương tác governor) KHÔNG ADOPT [oc_lit_position; oc_mvrvmech; oc_mvrvrobust]; governor GV3 6.107/2.830/17.89 (5y 5.849/full 17.50 = G2K20) ĐÓNG [oc_governor]; alt-dip +25% nhưng DD tệ 5/5 ĐÓNG [oc_altdipb1]; native-clock ±0.2pp ĐÓNG [oc_nativeclock]; MANUAL H2 3.508/17.24 vs M5 3.728 (thiếu 1.49pp), Kronos MANUAL 3.44/3.40, book-vol 5.308/18.67 ĐÓNG [oc_manualsplit; oc_kronosmanual; oc_kronosbookvol].
- Chủ tài khoản theo thứ tự: (1) giữ G2+carry f=0.25, kỳ vọng Bybit ~4.88; (2) nuôi mọi paper (gồm paper_d17bfg2k2) đủ 26 tuần; (3) OWNER đăng ký keepalive; (4) chưa đưa VRP/A1/M1/K2/governor/alt-dip vào live khi thiếu prospective.



Phạm vi: BOT = book + thang dip (cần bot); MANUAL = chỉ book + dip đặt tay theo lịch người thật.
Mọi số là walk-forward 5 năm (anchor 2021-09-24..2025-09-24, mỗi năm +365d, reset 1/4 vốn mỗi anchor,
mix trung bình 4 pha giờ, chi phí gate Bybit: maker 0.02% / taker 0.055%, funding bất lợi long trả 0.01%/8h
short không nhận). Cả 5 năm nay đều là research data; paper triển vọng mới là kiểm sạch.
Hiệu chỉnh số trùng: khi hai số lệch nhau do quy ước đo thì giữ số chính thức (official run.log) và ghi cả số
chained-reset trong ngoặc; khi lệch do rebalance (oc_carryfric cộng thêm, lãi carry tái đầu tư vào tài khoản = ước lượng chính; oc_carrycombo roll-only giữ lãi carry như tiền mặt không tái đầu tư = cận dưới) thì ghi cả hai
và dùng oc_carrycompound (+0.224 điểm %/tháng: G2 5.410 -> 5.634, DD năm 16.75, toàn đường 16.66; lãi carry tái đầu tư, BOT đặt lệnh theo tổng equity) làm kỳ vọng; oc_carryfric (+0.12) là bảo thủ, roll-only (oc_carrycombo) là cận dưới; số cũ 5.41 G2 giữ kèm giải thích luck đồng hồ ~0.17pp [oc_clockluck; oc_frontiercarry; oc_carrycombo].

Định nghĩa metric: R = trung bình hình học 5 năm reset mỗi năm; W = năm đơn lẻ tệ nhất 5 năm;
DD năm = max yearly DD; DD toàn đường = full-path trong run.log (liên tục, không reset);
DD gate = max(DD 4h-close toàn đường, DD 1m-marked toàn đường, gồm vị thế mở) [AGENTS.md];
recent R = năm gần nhất (anchor 2025-09-24); win book/rung/all = book là episode vị thế, rung là cặp fill->exit FIFO,
all = book+rung, sau phí [oc_frontier; oc_kpi].

## 1. Mục tiêu và giao thức kiểm định

- Mục tiêu bắt buộc (user 2026-09-27): >= 5%/tháng compounded net, DD <= 20%, chỉ majors BTC/ETH/SOL/BNB/XRP
Binance USD-M perps, limit majors không slippage size [AGENTS.md].
- Walk-forward replay: giả vờ "now" là anchor, đóng băng mọi thứ, chạy liên tục mọi nến năm sau và chấm điểm;
năm gần nhất (2025-09-24..2026-09-23) là "một năm trước -> now"; 5 anchor 2021-2025 lặp lại [AGENTS.md].
- Selection: chỉ so/chọn biến thể trên 4 năm đầu (anchor 2021-2024); năm gần nhất chấm ONCE cho finalist đóng băng,
không bao giờ dùng để chọn [AGENTS.md]. Bản đã nhìn năm cuối cần log paper triển vọng làm bằng chứng sạch [AGENTS.md].
- Gate: (a) mean hình học 5 năm >= 5%/tháng, (b) năm gần nhất alone >= 5%/tháng, (c) không năm lỗ; DD <= 20% full-path
(max 4h-close và 1m-marked) [AGENTS.md]. Robust criterion (từ v204): trong các biến thể DD <= 20 và không năm lỗ ở 4 năm
đầu, ưu mean 4 năm >= 5%/tháng nếu có, trong đó pick worst-year cao nhất, ties -> mean cao hơn [AGENTS.md].
- Mỗi trade như thật: entry limit, SL market taker 0.055% + TP limit maker 0.02% cho mọi vị thế; entry/rebalance limit,
unfilled hết hạn (không fallback market); stop-first nếu SL+TP cùng chạm trong một bar 1m [AGENTS.md].
- ZERO LEAKAGE: feature tại t chỉ dùng dữ liệu có ở close t; label/normalisation/calibration/threshold/model/chọn tham số
chỉ dùng dữ liệu trước anchor trừ embargo >= horizon; không statistic nào từ năm test feed ngược lại lựa chọn [AGENTS.md].
- Gate costs (Bybit VIP0 thật của user): entry/TP limit maker 0.02%, stop/market taker 0.055%, không thêm slippage;
funding adverse long trả 0.01%/8h, short nhận 0 (đứng thay cho trượt nhỏ); carry sleeve không thu funding income;
signed funding thực chỉ là dòng phụ có nhãn [AGENTS.md]. Entry mới không fill trong 5' đầu sau close 4h; từ phút 5 fill
bằng 1m trade-through; không vị thế -> MỘT limit resting cách giá, hiệu lực vài giờ; trong vị thế chỉ move/thắt SL/TP,
break-even, add/exit limit rời rạc; market chỉ cho SL [AGENTS.md].
- Hai sản phẩm chấm riêng (2026-10-02): MANUAL (chỉ book tay): floor bắt buộc mọi metric >= 5%/tháng, DD < 20,
win book >= 55%, rồi stretch 8%/tháng, DD < 15, win >= 60%; BOT (book+dip ladder, cần bot): 8%/tháng, DD < 15,
win all > 65% (dễ trước), DD > 20 không auto-reject [AGENTS.md].

## 2. Hệ thống triển khai: G2 + carry quý f=0.25 trong một UTA

Lệnh paper khuyến nghị: `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, equity paper 5000
(khuyến nghị thật >= 5000, tốt nhất ~10000), Bybit cross margin, Hedge Mode, 5x cả 5 coin, plan `trade_plan_v376.json`
[DEPLOYMENT_PLAN_VI; BOT_RUNBOOK_VI; QUICKSTART_VI]. Chân short quarterly của carry để 10x (hedge bằng spot),
f=0.25 chung một UTA; vượt f=0.25 phải tách vốn [oc_utamargin2; QUICKSTART_VI]. Lệnh vào PostOnly maker-only,
TP/reduce GTC reduce-only, stop/market không đổi; `postonly_reject` thử lại cycle sau không đuổi giá;
`risk_guard` ON mặc định ở testnet/live (per-coin 2.5x / dip 2.0x / total 4x / single 1x, log `risk_reject`),
OFF ở paper để giữ engine-faithful [BOT_EXECUTION.md bot_testnetfix; QUICKSTART_VI].

Số base (giữ cả hai quy ước, nguồn trong ngoặc):
- G2 (R2B1D17BF + trần dip 2x; v421 audited NO, twin v422 audited yes, số giống hệt): 5.41 %/tháng, worst 2.588, maxDD năm 16.91,
full-path official 16.82 (chained 16.91) [oc_frontier; oc_kpi_g2; oc_frontiercarry]. Deploy cũ D17BF (v411):
5.425 (làm tròn 5.43, recent 5.06) / DD năm 18.33 / full official 16.90 (chained 18.33) [oc_frontier; oc_kpi; oc_signedfunding].
- Chi tiết G2+D17BF theo năm (reset metric) [oc_kpi]: 2021: 2.83/DD 12.42; 2022: 3.51/16.23; 2023: 4.67/18.33
(D17BF) và mix G2 năm 2023 là 6.045/DD 15.81 (mix worst 2.588 là năm 2021, không phải mix-2023) [oc_phasedisp]; 2024: 11.27/8.26; 2025: 5.06/12.81. Đường liên tục D17BF:
4h-close DD 15.34, 1m-marked 16.90, gate 16.90, lãi ròng 5 năm +2534% (26.3x) [oc_kpi].
G2 KPI [oc_kpi_g2]: gấp 26.4x sau 5 năm, win all 65.3-65.5% (book 51.5%, rung dip 68.6-68.7%, n G2=5064/21513/26577; BF=4955/21389/26344),
không năm lỗ; 41% tháng >= +5%, ~70.5-72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng D17BF (G2 4 tháng 2024-04..07).
Gross đỉnh đo được: BF không trần peak 6.40x vốn (oc_kpi results.json combined 6.4007); G2 có trần 2x mix max 3.41x (oc_margin results.json G_max 3.4113, các phase <=3.78); "~7.1x không trần" chỉ là ước tính trong văn bản oc_margin/REPORT.md:95, không phải giá trị results.json [oc_kpi; oc_margin].
- G2+carry f=0.25 một UTA: ước lượng chính là oc_carrycompound (+0.224: G2 đơn 5.410/2.588/16.91/16.82
(close 16.05) -> +carry 5.634/2.778/16.75/full 16.66; lãi carry tái đầu tư, BOT đặt lệnh theo tổng equity)
[oc_carrycompound]; oc_carryfric (+0.123: 5.533/2.736/16.78, year-start sizing, chained-reset) là bảo thủ;
roll-only oc_carrycombo (5.413/2.647/16.78/full-marked 16.34 (close 15.60); f=0.50: 5.418/2.705/16.65/15.86)
là CẬN DƯỚI (lãi carry không tái đầu tư vào BOT) [oc_carryfric; oc_carrycombo]. Từng năm G2+carry f=0.25
compound (R/DD): 2021 2.778/10.86; 2022 3.353/16.75; 2023 6.590/15.69; 2024 10.956/8.20; 2025 4.698/12.66
[oc_carrycompound]; roll-only từng năm (R/DD): 2021 2.647/10.79; 2022 3.283/16.78; 2023 6.168/15.72;
2024 10.559/8.08; 2025 4.593/12.57 [oc_carrycombo]. Overlay cần tới 2f cash EXTRA khi cả hai coin cùng mở
(f=0.25 -> tới 1.5x funded); R tính trên base equity [oc_carrycombo].
- Carry sleeve độc lập (oc_cashcarry, BTC/ETH quarterlies, ENTER iff basis năm hóa >= 4%/yr, giữ tới delivery,
drag phí 0.275% allocated, delivery futures không funding): 50 contracts thấy -> 33 vào, 13 skip, 2 incomplete loại,
33/33 net dương (min +0.18% allocated) [oc_cashcarry]. Sum năm allocated: 2021 0.0470; 2022 0.0528; 2023 0.2960;
2024 0.1219; 2025 0.0058 (BTC/ETH: 2021 0.0261+0.0209 / 2022 0.0424+0.0105 / 2023 0.1579+0.1381 / 2024 0.0638+0.0581 /
2025 0.0058+0; mean basis 8.9/8.0, 5.6/5.7, 13.3/12.7, 7.4/7.4, 4.2/—%) [oc_cashcarry].
Gộp 5 năm +13.09% (f=0.25) = +0.218%/th số học (+0.213% hình học); f=0.50 +26.17% (+0.436/+0.416);
năm gần nhất ~+0.01%/th (1/6 cơ hội vượt filter) [oc_cashcarry]. Worst MtM allocated -1.01/-0.71/-2.65/-0.39/-2.17%
-> account f=0.25 tệ nhất -0.66% (2023); sleeve không cộng quá ~0.7% account DD [oc_cashcarry].
Margin một UTA (43.805 giờ, IM=(G2 gross+carry short)/5) [oc_utamargin]: f=0.25 free min 22.49%, IM max 77.51%,
0 blocked, 0 MM breach, spot cost max 95.8%, gap -10% giờ tệ nhất -28.85% không liq — CLEAR; f=0.50 free min 1.85%,
1 giờ blocked 2025-09-25 18:00, spot 179.9% thiếu USDT — KHÔNG clear [oc_utamargin; oc_utamargin2].
Short quarterly 10x: free 22.49%->32.67%, bắt buộc Cross (isolated cháy khi squeeze +30% mọi 5x/10x/20x) [oc_utamargin2].
Khả dụng Bybit [oc_carrycombo; research/data_fetch/bybitq/REPORT.md]: linear BTCUSDT-25DEC26/26MAR27/25JUN27 (cả ETH) + inverse BTCUSDZ26/H27,
deliveryFeeRate 0, fundingInterval 0, phí đúng gate, spot collateral 95%; yield inverse ≈ Binance (+0.4973/23 trades
vs +0.5234/25, f=0.25 +0.207%/+0.202% vs +0.218/+0.213) [research/data_fetch/bybitq/REPORT.md].

Ma sát D17BF/G2 (giữ DD<=20 mọi hàng, nguồn trong ngoặc):
base gate 5.43/DD 18.33/16.9 [oc_signedfunding]; trễ 15' D17BF 5.24 (docs/DEPLOYMENT_PLAN_VI.md:11; docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:6), G2 5.21/16.91 (docs/DEPLOYMENT_PLAN_VI.md:75);
trượt stop 50% (S4) D17BF 5.11/DD 20.0 (G2 4.90/17.31 vs D17BF 19.97) [docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:6; docs/DEPLOYMENT_PLAN_VI.md:75-76; oc_stopslip];
giá Bybit thật D17BF 4.97/19.9 (G2 4.88/18.11) [docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:6; docs/DEPLOYMENT_PLAN_VI.md:75-76]; trễ 30' D17BF 4.68 (G2 4.58/17.32) [docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:6; docs/DEPLOYMENT_PLAN_VI.md:75-76];
cost stress (maker 0.0004/taker 0.0007+5bps) 4.58/<=20 (G2 4.57/17.45) [DEPLOYMENT_PLAN_VI].
G2+carry f=0.25 dưới ma sát (year-start) [oc_carryfric]: base 5.533; S1 4.696; S2 5.339; S3 4.717; S4 5.033; S5 5.016
(f=0.50: 5.654/4.820/5.463/4.853/5.166/5.147) — giữ >=5.0 ở base/S2/S4/S5, RỚT S1 và S3 kể cả f=0.50;
sleeve chỉ +0.12-0.15pp (f=0.25), bớt DD 0.1-0.3pp, không năm lỗ cả 36 combo [oc_carryfric].
Giá Bybit thấp hơn Binance ~0.5pp/tháng, nằm ở thang dip (ít TP hơn), không ở book [DEPLOYMENT_PLAN_VI].
Funding thực có dấu chỉ là dòng phụ: +0.12-0.15pp/tháng (D17BF signed 5.55/18.32 vs gate 5.43/18.33) [oc_signedfunding].
Vốn (số cũ oc_lots qua docs/DEPLOYMENT_PLAN_VI.md:29: 10k đặt 100% book/98% dip; 5k 96%/94%; 2k 80%/81%, mất ~5-20% chủ yếu BTC; đã SUPERSEDED bởi G2 oc_capscale bên dưới): G2 minima mới (research/diagnostics/oc_capscale/REPORT.md:34-35): >=5000 đặt gần như mọi lệnh (book 0.9990/0.9995; dip 0.9780/0.9985/0.9967), 2000 chỉ ~93-96% count [oc_capscale; DEPLOYMENT_PLAN_VI].
VIP1/VIP2 chỉ +0.11/+0.16pp/tháng nhưng volume unreachable (5k chỉ 114.879/tháng, cần ~435k/1088k cho VIP1/2) — giữ VIP0 [oc_vipfees].

Hiệu chỉnh luck đồng hồ [oc_clockluck; oc_phasedisp; oc_seedengine]: 4 offset dip deployed mean 7.72 vs mean 24 offset
7.12 (gap -0.59; offsets 0=9.67 pct100% max /60=7.54/120=8.76/180=4.90; gap năm 2023 -0.42 + 2025 -0.15) -> kỳ vọng
đồng hồ ngẫu nhiên ~5.24 thay vì 5.41 (adjusted yearly 2.593/3.233/5.453/10.691/4.401; ratios 1.002/0.958/0.798/1.004/0.779)
— giữ số cũ 5.41 kèm giải thích ~0.17pp luck, method proxy [oc_clockluck]. Đơn lẻ phân tán 5 năm 3.102-6.923, DD tới
43.55 (phase3 năm 2023 -2.431/DD 43.23 trong khi mix năm 2023 +6.045; 2.588 là worst-year của mix, năm 2021), không clock nào thắng mọi năm — không bao giờ chạy pha đơn
[oc_phasedisp; oc_clockanat]. May mắn seed triệt tiêu ở cấp danh mục: 5 seed G2 5.343-5.430 (TB 5.387, deployed 5.410 hạng 2/5),
DD 16.54-17.03, không năm lỗ — trừ ~0.02pp luck [oc_seedengine].

Thực tế crash/outage/spread: gap -10% cả 5 coin phút tệ nhất không trần lỗ 58% vốn, trần 2x còn 33.5% (3x: 39%),
trung vị/p99 không đổi; trần hạ DD dưới mọi ma sát [DEPLOYMENT_PLAN_VI; oc_gapstress]. Vì sao cần trần: slip thực 1699 stops
trung vị -4.6 Binance/-1.6 Bybit (S4 ~18-19bps bảo thủ ở trung vị, công bằng kiểu 2021, quá nhỏ cho đuôi crash p90 +146/+197,
p99 +495/+738, max +813/+1347 bps; flash ~75%; top-10 toàn stop long dip trong FTX 2022-11-09 và flush 2024-01-03) [oc_stopslip].
COVID 03/2020 mix 4 pha ~-16.1%, pha đơn tệ nhất -21.8% (vượt 20% nên cấm pha đơn); trần 2x không kích hoạt trong crash
(peak gross <=1.03x) nhưng giữ vì chặn gap lúc yên [oc_crash2020]. Outage routine rẻ (weekly-2h 2.4%/monthly-6h 1.7%/
quarterly-24h 0.9% lãi dip) nhưng mất đúng flush tốn ~9% (giờ xấu nhất 2021-12-04 +0.684, DD +0.26); quy tắc: hủy bid chờ
trước bảo trì có hẹn, sau sự cố xác nhận stop native rồi mới comeback [oc_outage]. (oc_outage chỉ đo weekly-2h/monthly-6h/quarterly-24h/adversarial-10h; không có kết quả "cắt 4h 1-3h" nào.)

## 3. Menu return/DD (có/không carry f=0.25)

Biên yearly-DD (R/DD năm) [oc_frontier]: R2B1 4.55/13.88 – D13 4.957/15.00 – X45 5.118/15.92 – G2F20K20 5.346/16.20 –
G2 5.41/16.91 – G15K20 5.731/16.96 – G2K20 5.874/17.79 – D20B11 5.894/21.21.
Biên full-path [oc_frontier]: D15B08 4.626/14.94 – F20K17 5.042/15.47 – X45 5.118/15.81 – G2F20K20 5.346/16.02 –
S5 5.416/16.62 – S6 5.565/16.71 – G15K20 5.731/16.76 – G2K20 5.874/17.69 – D20B11 5.894/19.10.
Mọi overlay rủi ro đi dọc một frontier duy nhất, không có DD miễn phí [oc_frontier].
Có carry f=0.25 cộng +0.11..+0.14pp (TB +0.13), bớt DD 0.02-0.78pp, không hàng nào tăng DD; 45 -> 47 hàng qua mốc 5.0;
stretch 0 hàng; win all không đổi (overlay equity, thêm 0 trade) [oc_frontiercarry]:
D13 (v409) 4.957/15.00/16.54 chained-reset -> 5.091/14.87/16.40 chained-reset (official run.log full-path v409 = 16.36; qua 5.0 nhưng fullDD >15, không stretch);
G2 (v422) 5.410/16.91/16.91 chained-reset -> 5.533/16.78/16.78 chained-reset (official full-path G2 16.82);
D17BF (v411) 5.425/18.33/18.33 -> 5.555/18.29/18.29; G2K20 cao nhất đạt base 5.874/17.79 -> 5.989/17.66;
tuyệt đối cao nhất v407 D20B11 carry 6.020/21.18 rớt DD [oc_frontiercarry].
Kỳ vọng thực tế (49 cửa sổ 12m của v411 R2B1D17BF D17BF, không phải G2) [docs/DEPLOYMENT_PLAN_VI.md:57-60; oc_rolling17]: 49 cửa sổ 12m min 2.73/p10 3.25/trung vị 4.89/p90 8.88/
max 11.71; DD min 8.3/trung vị 13.5/p90 18.3/max 18.7; 49% cửa sổ >=5%, 61% DD<15, 100% DD<20, không cửa sổ lỗ.
Bootstrap 10.000 năm: trung vị 5.12 (p5 1.47/p95 10.32), chỉ ~52% năm >=5%; P(năm lỗ) ~0.7%; DD marked trung vị 14.5%,
p95 22.6%, P(DD>20%) ~11%, P(>25%) ~2.1% — vốn phải chịu DD 25% [oc_mcdd].
KPI 61 tháng: 41% tháng >=+5%, ~70.5-72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng ở BF [oc_kpi] (G2 4 tháng 2024-04..07 [oc_kpi_g2]).
Tuần xấu G2+trần 2x [oc_stresshist]: tệ nhất 2023-12-27..2024-01-03 -12.3% (DD 13.9%, hồi ~54 ngày; không trần -14.7%/16.3%);
khác 2025-10-10 -9.7% (hồi ~134 ngày), 2024-07 -9.6%, 2023-06 -8.6%, 2024-06 -8.9%; FTX -2.2% (DD 9.2%), LUNA -3.0% (DD 9.7%).
Bối cảnh 2026-09 (không phải dự báo): trên MA200, vol thấp, trend 90d +35%; nhóm lịch sử 21 tháng TB +8.1%,
trung vị +5.0%, 29% tháng âm, tệ nhất -7.5% [DEPLOYMENT_PLAN_VI]. Underwater G2: 47 lần sụt >5%, dưới đỉnh trung vị
~9 ngày, p90 ~63 ngày, dài nhất ~149 ngày (2022-07..12); ~29% thời gian dưới đỉnh >5% [oc_underwater].
Grind DD gate G2 16.91 là grind chậm đồng bộ 2023-04-17->06-15 (~59 ngày, book long -9..-11/phase + dip NET -7..-10/phase sau khi trừ TP +10..+13, BNB dẫn đầu, book-shorts các phase bù +6.8 gộp = +0.45+1.73+1.92+2.69) — muốn <15 phải cắt ~11% thiệt hại cửa sổ; breadth=1.0 là cực trị lặp lại duy nhất
(đỉnh mở rộng toàn diện), gate tương lai phải điều kiện trên over-extension chứ không phải stress [oc_ddanat_g2; oc_grindsignal].

## 4. Đạt được gì so với mục tiêu

BOT base ĐẠT: G2 5.41 (luck-adjusted ~5.24, vẫn trên 5), DD 16.91/16.82 <=20, win all 65.3-65.5% >55-60, không năm lỗ
(W=2.588 G2; 2.831 là worst D17BF) [oc_frontier; oc_kpi_g2; oc_clockluck]. Hàng giá Bybit G2 4.88 / D17BF 4.97 vẫn DD<20 [DEPLOYMENT_PLAN_VI].
Stretch win >60 ĐẠT (all-trade 65.5%) [oc_kpi]. DD <15 và 8%/tháng CHƯA: biên max chỉ ~5.9 ở DD>17.5 (G2K20 5.874/17.79,
D20B11 5.894/21.21 FAIL); stretch DD duy nhất D13BF 4.97/năm 14.98/toàn đường 14.86 thiếu 0.03pp return và dưới mọi
ma sát DD vượt 15 (phí x2 15.51; trễ 15' 15.08; trễ 30' 15.62) — kỳ vọng thận trọng ~4.2-4.8%/th DD ~15-16 [oc_frontier; oc_d13robust].
Vì sao 8% không tới: bão hòa cơ học — edge/đơn vị notional bất biến theo kd (0.0029->0.0028), B1 cắt ~35% notional,
trần 2x tỉa đuôi gần miễn phí (-1.42 DD đổi -0.015 R), governor tự bóp khi DD cao; size thêm chỉ đổi thành DD
(V2 +0.29 R đổi +5.75 DD) [oc_saturation]. Edge không decay (slope +0.067 CI [-0.158;+0.160]; sau 6.61 > đầu 5.59;
6m gần nhất 7.38) nên trần là cấu trúc, không phải edge yếu [oc_edgedecay].
MANUAL floor CHƯA ĐẠT: tốt nhất trung thực M5_human (15', bỏ nến đêm, agents ON) 3.73 (dev4 3.66, recent 3.99),
DD 17.9/17.8, book 64.8% (n=3744), W=0.85, thiếu ~1.3pp return (DD và win đạt) [oc_manualcap; oc_manualnight].
MANUAL+carry tốt nhất cũng chỉ 3.993 (equity-level 3.765), thiếu ~1.0-1.2pp [oc_manualcarry].
MANUAL+book gấu 3.6-3.7/DD 21.6; top-2 dip 3.06/19.5; trần đặt lệnh G15/G10 3.01/14.9 và 2.62/13.5 (win 64.9% cả hai,
DD tốt nhưng return càng xa base) — hướng cap thuần ĐÓNG, cần edge entry trước [oc_manualcap; docs/opencode/RESEARCH_MAP_DRAFT_20261006.md].
Tay người tốn ~0.5pp (M5_base 4.066 - M5_human 3.586 = 0.48pp; M4 chênh 0.47pp), chạy 80% vốn để DD<20 chỉ còn ~2.8%/tháng [DEPLOYMENT_PLAN_VI; oc_manualbf].
Carry cộng ~+0.13pp và bớt DD một chút nhưng ma sát bào ~0.2-0.8pp (đo ở oc_carryfric/oc_d13robust, không phải oc_frontiercarry) nên không phải cứu cánh — giữ G2 chờ paper [oc_carryfric; oc_d13robust].

## 5. Bài học phương pháp

1. Book ideas đi THẲNG tới engine 4-phase: 3/3 vectorised screens FAIL full engine (EXP +0.088 nhưng 2021 -0.341;
CME +0.014 nhưng full DD +0.21pp và 2023 -0.416; USDT -0.242, 2024 -0.701) [oc_expiry4p; oc_cmegap4p; oc_usdt4p].
2. Dip screens cần gate placebo: full PROMISING legs + dSum5y >= +0.273 (pooled p95, ~3.5% base 7.718; FPR 6.7%->0.7%)
[oc_placebo_dip]. Book joint tails FPR 0.2%/0.0% (không real nào pass) [oc_placebo].
3. Control exposure-matched cho tilt: constant-mult control + 500 block-shuffles; USDT ALPHA (gain +0.049, pct 99.4)
vẫn engine NO [oc_premexpo; oc_placebo].
4. Chỉ dùng mean 4-phase: clock đơn phân tán 3.10-6.92, DD tới 43.55; mix khóa luck [v376; oc_frontier; oc_phasedisp].
5. Kiểm cân bằng dấu member: blend 0.8/0.2 interior nhưng bước cục bộ đổi dấu theo năm (mean step 0.0134, không plateau
sạch) — giữ nguyên, không chọn lại [oc_blendsens].
6. Gắn nhãn post-hoc: frontier moves post-hoc không deploy; folds phải transfer (WF select 31 biến thể 6.03 vs giữ cố
định 6.08 — giữ cố định D17BF+G2, không đổi theo kết quả gần đây) [oc_wfselect; v419-v426; oc_expirycb].
Thước đo cũ mix liên tục phóng đại các năm sau (lucky phase-0 43x theo docs/opencode/RESEARCH_MAP_DRAFT_20261006.md:62); mọi số trên đã dùng thước đo cân lại 1/4 mỗi đầu năm
[docs/opencode/RESEARCH_MAP_DRAFT_20261006.md]. Chọn walk-forward mỗi năm chỉ bằng các năm trước + embargo >= horizon; fail dev DD/worst thì đóng
không chạm năm cuối [research/parallel/rounds/parallel-20260906-r2/v427/v427_c2_rank_calibrated.py:42 (ghi chú PROCESS NOTE trong code, không phải báo cáo audit)].

## 6. Hướng đã đóng (tóm tắt; danh sách đầy đủ ở docs/CLOSED_DIRECTIONS.md)

Dip sizing/exit: B1 corr-size + D17BF dip x1.7 + bear-book + trần G2 GIỮ (bước v400/v406/v410/v411/v421);
TP decay, TP1.5 theo n, dip tilt, bear-bar fast TP, deep-rung fast TP, break-even, hold-extend, fill-TTL,
rung-space/cap, B1-wide/soft/BTC-lead/deeper/BTC-inclusive, trend-ladder, lowvol-rung, breadth-dip, cooldown,
re-arm, velocity, adaptive/EWMA/seasonal sigma, +2.0sg rung, x2.0 dip ĐÓNG [docs/opencode/RESEARCH_MAP_DRAFT_20261006.md; CLOSED_DIRECTIONS.md].
Book tilt: bear-book GIỮ; corr-scale, per-coin bear, long-cap, cadence, brake, bull-boost, bear-short, hold-cap,
weekend/macro/FOMC halve, funding-tilt, premium/skew/basis/breadth tilts, expiry-book (vectorised PROMISING nhưng
engine NO), expiry+premium combo, CME-gap ĐÓNG; per-coin brake PROMISING (#45, v426 G2BRK 5.30 vs 5.41 on-frontier,
không adopt) và DVOL-short/dvolbook/idea2 còn screen [CLOSED_DIRECTIONS.md].
Model: C1 (v428 dev 1.927/1.768/3.191/7.590 mean 3.593 DD 19.17 vs deployed 5.601/16.91 — thua cả 4 năm) và C2
(rank-calibrated, bug calibration lần đầu dev 0.88% KHÔNG phải model result, audit mù PASS, fixed-run pending rồi
reject) ĐÓNG 2/2 [v428; research/parallel/rounds/parallel-20260906-r2/v427/]. Sleeve: cash-carry f=0.25 GIỮ add-on; TSMOM overlay, reversal, daily ladder, rip-sell,
FAR tenor (Binance +0.425 / Bybit-inverse +0.372 hình học — là exposure phải vay, không phải rate tốt hơn — KHÔNG adopt), carry top-up/calendar ĐÓNG [oc_carryfar; CLOSED_DIRECTIONS.md].
Execution: PostOnly entries + risk guard GIỮ; engine-faithful cap fix GIỮ (dip 209->261, +1.12%->+3.20% vs 3.58%
không trần, tốn ~0.38pp) [bot_capfix]; stop-mark, 2h TTL, depth-tilt, same-minute TP (dSum đúng 0 trên 22312 rungs),
USDT/CME/expiry dip, expiry/CME/USDT book 4-phase, placebo gates ĐÓNG [CLOSED_DIRECTIONS.md].
Frontier/clock: frontier map GIỮ; D13/D15/F20K17/X45/G2K20/D20B11 chỉ để vẽ biên; cap conservative v425 và brake v426
frontier-only; WF-select/re-balance/corr-budget/governor ĐÓNG; 4-phase GIỮ, 8-phase (4.960/17.98/17.32 vs 4-phase
5.410/16.91/16.82, -0.45pp +0.5pp DD, 47-60% BTC dưới minimum) NO [CLOSED_DIRECTIONS.md].
MANUAL: M5_human GIỮ best honest; bear-book/top-2/corr-proxy/cap/shallow/TSMOM/daily/2-coin ĐÓNG [CLOSED_DIRECTIONS.md].
Data: whale flow/TV/A-B GIỮ; liq/order-book/DVOL/macro/COT/F&G/Korea/options/Coinbase-SOL-XRP dilute/hurt ĐÓNG;
liq/topbook collector từ 2026-10-04 chờ 2027-01-04 [CLOSED_DIRECTIONS.md].
Không deploy tilt/halving nào (kể cả USDT ALPHA, expiry PROMISING vectorised) khi chưa PASS engine 4-phase + paper
[oc_placebo; oc_placebo_dip].

## 7. Bằng chứng triển vọng và đường tới live

Paper từ 2026-10-05 (chưa đủ 8 tuần, sớm nhất ~2026-12-01): tại snapshot PAPER_DAY1 (~03:28 UTC) có 5 thư mục `paper` (R2-4P), `paper_d17bf`, `paper_d17bfg2`,
`paper_g2k20`, `paper_d13bf` (đúng thời điểm đó không có bot thứ 6; d17bfg2/g2k20 đã restart `--adopt-fresh` + fix double-spend);
tới lúc báo cáo có 7 thư mục (thêm `paper_d17bfg2c` G2+carry 0.25 started 2026-10-06 07:19 UTC, BTC-25DEC26 basis ~5.31%, equity 5000, và sổ
`paper_carry`) [docs/opencode/PAPER_DAY1_20261006.md; DEPLOYMENT_PLAN_VI]. Ngày đầu 2026-10-06 ~03:28 UTC: backend sống (plan 03:01:12Z,
tuổi 0.5h), mỗi bot equity ~4998.7-4999.6/return -0.03..-0.01%/maxDD 0.01-0.09%/fills 0 dip + 3-6 book, toàn book fill
đúng giá, 0 exit, mọi piece có stop+TP, unprotected/qty_mismatch none; stale-plan đúng giữa outage 12:39-17:40
(plan kẹt 12:03:26Z, stale paper/d17bf/d17bfg2/g2k20/d13bf = 355/281/52/83/0, sau ~18:13 bám lại); `skipped_below_minimum` 596-701 dòng ở 3/5 bot (paper 658, d17bfg2 701, g2k20 596; paper_d17bf và d13bf 0, ồn erwart);
không double-spend; divergence toàn "too early" (<14d) [docs/opencode/PAPER_DAY1_20261006.md].
Carry paper 2026-10-06 06:05Z f=0.5: BTC entered basis +5.42%, ETH skip (<4%), MtM -0.15% quá sớm [PROSPECTIVE_20261006].
Parity carry 143/144 đồng ý với rule đóng băng trên mids của ledger (vi phạm genuine duy nhất ETH retry vào ở 3.80% <4% đã fix re-check trong bot/carry.py); khớp chính xác basis trong 0.2pp/yr chỉ 56/144 (88 breaches là mid-vs-last do quarterly kém thanh khoản, không phải bug rule)
[oc_carryparity].
OOS sạch trên dữ liệu mới (research kết thúc 2026-09-23, không gate claim vì mẫu nhỏ): full G2 book+dip 2026-09-30..10-06 (6 ngày, rule-based, 4 pha, gate costs) +1.995% (equity 1.004602->1.019945), DD gate 0.766% (close 0.128/marked 0.766), 10 rung exits 9 thắng (90.0%), 0 book episode hoàn tất, phân vị 72.7 trong biên 6 ngày (p5 -3.309/p50 +0.466/p95 +7.477) [oc_bookoos]; dip sleeve riêng 2026-09-24..10-06 (12 ngày) +0.187%, DD 0.149%, 14 exits 12 thắng (85.7%), phân vị 37.8 trong biên 12 ngày (p5 -4.173/p50 +1.028/p95 +13.634) [oc_oos12d]. Cả hai trong biên lịch sử, không kết luận gate. Chạy lại hằng tuần: `.venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py --fetch --run` [oc_bookoos].
Caveat: trần dip bot cũ CHẶT HƠN engine (09/2026 có trần chỉ +1.1% vs +3.6% không trần); fix engine-faithful đã xong
trên paper (C_on 3.20%/261 fills vs A 3.58%/271, trần cũ 1.12%/209) nhưng tới khi merge xong thì chạy KHÔNG trần hoặc
chấp nhận thấp hơn [bot_capfix]. Carry orders trong paper bị generic diff hủy ngày 2026-10-06, fix đang làm [docs/opencode/OPENCODE_W_bot_carryfix.md:3-4; bot/run.py].
Go-live chỉ sau >=8 tuần paper + testnet bắt buộc, khi ĐỦ cả 4: (a) paper >= phân vị 20 bootstrap
(`prospective_scorecard.py`); (b) DD paper <=15%; (c) lệch bot vs plan <=1.5pp/tháng (đủ 14 ngày mới kết luận);
(d) không cycle_error >1h, không vị thế thiếu stop [DEPLOYMENT_PLAN_VI].
Dừng: DD >20% dừng mở mới; lỗ tháng >10% halve vốn tháng sau; phân vị <5 sau >=8 tuần thì dừng [DEPLOYMENT_PLAN_VI].
Kiểm hằng ngày: `daily_status.py` (+ mục 6 edge monitor) + `bot_health.py` + `paper_report.py` + `prospective_scorecard.py`;
runbook đã xác minh độc lập 2026-10-06 (core đúng, 11 issue văn bản, chưa đủ điều kiện live vì paper <1 ngày)
[RUNBOOK_VALIDATION_20261006]. Testnet 7 ngày G2+carry theo `docs/TESTNET_PLAN_VI.md` (9 tiêu chí PASS, P&L không kết luận): code-review F1-F7 + N1-N4 ĐÃ SỬA (commit 359004f, bot_reviewfix) nên testnet có carry GO sau preflight PASS; live chỉ sau testnet sạch 7 ngày [docs/opencode/CODEREVIEW_BOT_20261006.md; docs/BOT_EXECUTION.md].
Carry làm tay theo rule đóng băng (oc_cashcarry: 33 entered / 25 in-window trong 5 năm, ≈5 quyết định vào/năm); vào khi front còn <=7d và basis >=4%/yr; mỗi chân f x vốn; giữ tới delivery;
bán spot đúng 08:00 UTC delivery [oc_carrycombo; research/tournament/carry_audit/COMPARISON.md (audit độc lập verdict FAIL về dung sai số — 20/25 basis >0.1pp, 25/25 returns >0.02pp, 4/5 năm, thêm 1 BTC 2026-12-25, 1 sign-flip BTC 2026-03-27 — nhưng PASS leakage/fee/overlay/IM-MM; leader 2026-10-06 chấp nhận kèm modelling note settlement đúng kinh tế, thêm rule bán spot đúng giờ delivery); QUICKSTART_VI].

## 8. Việc còn mở

- Paper triển vọng là bằng chứng sạch duy nhất: nuôi đủ >=8 tuần + đủ 4 gate; divergence >=14 ngày mới kết luận;
hiện mọi bot/paper mới ~0.2-1.1 ngày ("quá sớm", trong biên) [PROSPECTIVE_20261006; DEPLOYMENT_PLAN_VI].
- Testnet bắt buộc trước live (GO sau preflight PASS; code-review F1-F7 + N1-N4 đã sửa ở commit 359004f nên testnet có carry được phép; live chỉ sau testnet sạch 7 ngày), rồi live vốn nhỏ, tăng vốn sau
3 tháng nếu gate vẫn đúng [DEPLOYMENT_PLAN_VI; docs/TESTNET_PLAN_VI.md; docs/BOT_EXECUTION.md; docs/opencode/CODEREVIEW_BOT_20261006.md].
- Một UTA G2+carry f=0.25 cố định (không đổi theo kết quả gần đây; WF-select 31 biến thể thua giữ cố định)
[oc_wfselect]. Không vượt f=0.25 chung UTA; FAR/top-up/calendar/weekly carry đã đóng [oc_carryfar; oc_carrytopup; oc_calendar].
- Dữ liệu liquidation/top-of-book: collectors KHỎE từ restart 2026-10-05 17:40 UTC (9.06h sạch, 0 gap>60s, 326.813
topbook rows, 802 liq) nhưng còn non (3.230 rows tới 2026-10-06, 2 gap đã rào) — tích 4-12 tuần, walk-forward sớm nhất
2027-01-04, tới lúc đó chỉ monitoring [oc_collectors; oc_liqcheck].
- Edge monitor đã vào `daily_status.py` mục 6: TB 6 tháng <1.61%/tháng hoặc TP rate dip nửa năm <0.434 thì ĐIỀU TRA,
không tự đổi cấu hình [oc_edgedecay]. Vốn phải chịu DD 25% [oc_mcdd].
- Tháng yên tĩnh khởi đầu (6 flush/30d = nhóm thấp): lịch sử 12 tháng thấp sau đó trung bình +4.87%/tháng nhưng trung vị chỉ +0.67% (p10 -4.46/p90 +22.44; 3/12 đạt >=5%, 4/12 lỗ), so với nhóm bình thường (n=34) 7.55/4.82 và nhóm cao (n=14) 3.64/4.17; chênh lệch trong một SE mẫu nhỏ (n=12), hai tháng lãi lớn nhất (+23%) cũng từ khởi đầu yên tĩnh — khởi đầu yên tĩnh KHÔNG phải tín hiệu xấu đáng tin, chỉ nghĩa là ít cơ hội dip hơn, giữ kỳ vọng chung và ngưỡng edgedecay [oc_quietmonth].
- Giả thuyết mở duy nhất (chưa rule): breadth=1.0 làm gate over-extension tương lai [oc_grindsignal].
Lead book-coin brake PROMISING (cắt ~30% book loss cửa grind -0.0504->-0.0354) chờ đăng ký engine version + paper
[oc_bookcoinbrake]; v425 (trần trên hàng conservative) đã pre-register [docs/opencode/RESEARCH_MAP_DRAFT_20261006b.md:33].

## 9. Bổ sung docs_update11 (2026-10-06)

- Jitter đồng thời ±10% kd/G/k, 12 bộ Kaggle [oc_jitter]: BASE tái lập v421 (5,41/2,588/16,91/16,82) PASS; cả 12 bộ 5,09–5,95
(trung vị 5,54), DD năm 16,3–18,2, full 16,28–18,07, không năm lỗ — ROBUST; G2 nằm trên vùng ổn định, không đổi triển khai.
- Latency bot thật [docs/opencode/LATENCY_20261006.md]: steady-state book ~5,3 phút, dip ~16,1–16,3 phút, bảo vệ ~0,3 giây = base 5/16,
không phải S2 (book 15 phút) hay S3 (book 30/dip 31 phút); S2 chỉ trễ book, S3 trễ cả book+dip; đuôi p90/max là backlog khởi động runner.
Bộ ma sát thực tế cho BOT từ nay là S1 (phí) / S4 (trượt stop 50%) / S5 (giá Bybit); S2/S3 không áp dụng.
- Hồ sơ thay thế G2K20 + carry f=0,25 [oc_g2k20robust]: G2K20 base 5,874/maxDD 17,79/full 17,69; +carry base 5,989/17,66,
S1 5,022/17,88, S2 5,807/17,67, S3 5,056/17,77, S4 5,448/17,82, S5 5,465/18,63 (full chained 19,72) — giữ >= 5 và DD < 20 dưới
mọi ma sát (đệm return so với G2+carry rớt S1/S3), nhưng DD cao hơn G2 ~1 điểm (base ~17,8 so với ~16,8; S5 tới ~19,6).
Đã rớt fold năm gần nhất (v422 fold 4 test 2025-09-24: 4,716 so với 5,06 của R2B1D17BF, transfer=False) nên G2 vẫn là triển khai chính;
runner paper `paper_g2k20c` (G2K20+carry 0,25) từ 2026-10-06 ~14:15 UTC thu bằng chứng triển vọng.
- Bookscale NO [oc_bookscale]: G2B11 x1,1 S1 4,769 (+carry 4,892), S3 4,647 (+carry 4,788); G2B12 x1,2 S1 4,673 (+carry 4,799),
S3 4,715 (+carry 4,854) — rớt mốc 5,0 cả 4 ô có/không carry — không adopt.

<!-- factfix 2026-10-06: fixed L52 (v421 NO / v422 yes); L58 (G2 n=5064/21513/26577, BF=4955/21389/26344); L60 (G2 max 3.41 results.json, BF peak 6.4007, 7.1x REPORT-text only); L80-82 ([bybitq]->research/data_fetch/bybitq/REPORT.md); L85-87 (lat15/S4/Bybit/lat30 as D17BF research-map values + G2 legs DEPLOYMENT_PLAN_VI:75-76; G2 lat15 5.21/16.91); L94 (old oc_lots SUPERSEDED, lead with oc_capscale); L101-102 (mix-2023 6.045/15.81; 2.588 = mix worst 2021); L113-114 (removed no-source 1-3h line, kept oc_outage scenarios); L125 (chained-reset vs official run.log labels); L129-130 (49 windows = v411 D17BF); L133 (2mo BF [oc_kpi], G2 4mo [oc_kpi_g2]); L139-141 (dip NET after TP offset; +6.8 = book-shorts sum); L145 (W=2.588 G2, 2.831 D17BF); L159 (~0.5pp not ~0.6pp); L160 (friction 0.2-0.8pp cited oc_carryfric/oc_d13robust); L175 (43x -> research-map:62); L177 (PROCESS NOTE -> v427 code docstring); L184/188/196/246 ([research-map]->actual draft paths; v425 in ...b.md:33); L192 (FAR Binance +0.425 / Bybit-inverse +0.372 geometric, not adopted exposure-not-rate); L207 (5 dirs at PAPER_DAY1 snapshot, 7 at report time); L212-213 (stale 355/281/52/83/0); L213 (skipped 596-701 only 3/5 bots, d17bf/d13bf 0); L216 (parity 143/144 + 56/144 within 0.2pp, 88 mid-vs-last); L220 ([paper_d17bfg2c]->OPENCODE_W_bot_carryfix + bot/run.py); L229 (carry_audit FAIL disclosed, accepted with note; 33 entered/25 in-window ~5/yr, removed ~4/yr ~15 tickets); L227/232 (testnet F1 PostOnly-not-sent + V1 Cross/5x-manual). Conclusions unchanged. -->
