# Báo cáo cuối cùng (VI) — 2026-10-06

Phạm vi: BOT = book + thang dip (cần bot); MANUAL = chỉ book + dip đặt tay theo lịch người thật.
Mọi số đều là walk-forward 5 năm (anchor 2021-09-24..2025-09-24, mỗi năm +365d, reset 1/4 vốn mỗi anchor,
mix trung bình 4 pha giờ, chi phí gate Bybit: maker 0.02% / taker 0.055%, funding bất lợi long trả 0.01%/8h
short không nhận). Cả 5 năm nay đều là research data; paper triển vọng mới là kiểm sạch.

## Định nghĩa metric (dùng thống nhất toàn báo cáo)

| Ký hiệu | Nghĩa | Nguồn định nghĩa |
|---|---|---|
| R (%/tháng) | trung bình hình học 5 năm, reset mỗi năm | oc_frontier REPORT |
| W (%/tháng) | năm đơn lẻ tệ nhất trong 5 năm | oc_frontier REPORT |
| DD năm | max yearly DD (rows[row].DD) | oc_frontier REPORT |
| DD toàn đường | full-path DD trong run.log (liên tục, không reset) | oc_frontier REPORT |
| DD gate | max(DD 4h-close toàn đường, DD 1m-marked toàn đường, gồm vị thế mở) | AGENTS.md |
| recent R | năm gần nhất (anchor 2025-09-24) | oc_frontier REPORT |
| win book / rung / all | book = episode vị thế (v213), rung = cặp fill->exit FIFO, all = book+rung, sau phí | oc_kpi REPORT |

## 1. Trạng thái so với mục tiêu

Mục tiêu base: BOT >= 5%/tháng, DD <= 20, win > 55%; MANUAL >= 5%/tháng, DD < 20, win book >= 55%.
Stretch: 8%/tháng, DD < 15, win >= 60% (MANUAL) / > 65% (BOT).

| Sản phẩm | R | DD năm xấu nhất / toàn đường | Win | Không năm lỗ? | Kết luận |
|---|---|---|---|---|---|
| BOT R2B1D17BF v411 (deployment pick) | 5.43 (recent 5.06) [oc_frontier; oc_signedfunding] | 18.33 / 16.90 [oc_frontier; oc_kpi] | book 51.5%, rung 68.7%, all 65.5% (n=4955/21389/26344) [oc_kpi] | có (W=2.83) [oc_frontier] | **đạt base** (ma sát gate; hàng giá Bybit 4.97 vẫn DD<20, xem mục 2) |
| BOT + trần dip 2x (G2, v421, bản chạy thật) | 5.41 (recent 4.65) [oc_frontier; oc_signedfunding] | 16.91 / 16.82 [oc_frontier] | như trên (cùng engine) | có (W=2.59) [oc_frontier] | base đạt, DD thấp hơn ~1.4pp với cùng lợi nhuận |
| MANUAL tốt nhất trung thực M5_human (15', bỏ nến đêm, agents ON) | 3.73 (dev4 3.66, recent 3.99) [oc_manualcap; oc_manualnight results.json] | 17.9 / 17.8 [oc_manualcap] | book 64.8% (n=3744), all 68.2% [oc_manualnight] | có (W=0.85) [oc_manualcap] | **chưa đạt base về return** (thiếu ~1.3pp); DD và win đạt |
| MANUAL + bear-book lịch người (manualbf) | 3.6–3.7 [research-map 2026-10-06] | 21.6 (pha xấu 33→25) [research-map] | — | — | vẫn dưới base |
| MANUAL top-2 dip (oc_manual2) | 3.06 [research-map] | 19.5 [research-map] | — | — | rớt base |
| MANUAL trần đặt lệnh G15/G10 | 3.01 / 2.62 [oc_manualcap] | 14.9 / 13.5 [oc_manualcap] | book 64.9% cả hai [oc_manualcap] | có [oc_manualcap] | DD tốt nhưng return càng xa base → đóng hướng |

Chi tiết BOT theo năm (reset metric, R2B1D17BF) [oc_kpi; oc_mcdd khớp từng chữ số]:
2021: 2.83 / DD 12.42; 2022: 3.51 / 16.23; 2023: 4.67 / 18.33; 2024: 11.27 / 8.26; 2025: 5.06 / 12.81.
Đường liên tục: 4h-close DD 15.34, 1m-marked 16.90, gate 16.90, lãi ròng 5 năm +2534% (26.3x) [oc_kpi].

## 2. Cấu hình triển khai và vì sao

Lệnh paper khuyến nghị (runbook): `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`, equity paper 5000
(khuyến nghị thật >= 5000, tốt nhất ~10000), Bybit cross margin, Hedge Mode, plan `trade_plan_v376.json`
[DEPLOYMENT_PLAN_VI; BOT_RUNBOOK_VI].

| Ma sát (D17BF) | R | DD | Nguồn |
|---|---|---|---|
| base gate | 5.43 | 18.33 / 16.9 | oc_signedfunding (gate row) |
| trễ 15' | 5.24 | ~16.9 | DEPLOYMENT_PLAN_VI (v411 frictions) |
| trượt stop 50% | 5.11 | 20.0 | DEPLOYMENT_PLAN_VI |
| giá Bybit thật | 4.97 | 19.9 | DEPLOYMENT_PLAN_VI |
| trễ 30' | 4.68 | — | DEPLOYMENT_PLAN_VI |
| cost stress (maker 0.0004/taker 0.0007+5bps) | 4.58 | <= 20 | DEPLOYMENT_PLAN_VI |
| G2 (D17BF+trần 2x) giá Bybit | 4.88 | 18.11 | DEPLOYMENT_PLAN_VI (v421 audit) |

Vì sao trần 2x: gap-stress sập tức thì -10% cả 5 coin nhảy qua mọi stop — phút tệ nhất không trần lỗ 58% vốn,
trần 2x còn 33.5% (3x: 39%), trung vị/p99 không đổi; lợi nhuận giữ nguyên (5.41 so với 5.43, DD 16.9 so với 18.3)
[DEPLOYMENT_PLAN_VI]. Trần cũng hạ DD dưới mọi ma sát (cost x2: 4.57/DD 17.45; trượt stop: 4.90/17.31 so với
D17BF 19.97) [DEPLOYMENT_PLAN_VI]. Giá Bybit thấp hơn Binance ~0.5pp/tháng, nằm ở thang dip (ít TP hơn),
không ở book [DEPLOYMENT_PLAN_VI]. Funding thực có dấu chỉ là dòng phụ: +0.12–0.15pp/tháng so với gate
(D17BF signed 5.55/DD 18.32 so với gate 5.43/18.33) — số chính thức vẫn là gate [oc_signedfunding].
Notional dip không trần có lúc ~6.4x vốn (stop gần, thị trường yên; có trần 2x còn ~2x) — phải đặt đòn bẩy
tài khoản đủ cao, không dùng Isolated [oc_kpi; BOT_RUNBOOK_VI]. Vốn nhỏ: 10k USDT đặt được 100% book/98% dip;
5k: 96%/94%; 2k: 80%/81% (mất ~5–20%, chủ yếu BTC) [DEPLOYMENT_PLAN_VI].
CẢNH BÁO 2026-10-06: bot cài trần hiện CHẶT HƠN engine (tính cả lệnh chờ) — 09/2026 bot có trần chỉ +1.1% so
với +3.6% không trần; tới khi bot_capfix xong thì chạy KHÔNG trần hoặc chấp nhận lợi nhuận thấp hơn
[BOT_RUNBOOK_VI; RUNBOOK_VALIDATION_20261006 ISSUE-01].

Go-live tiền thật nhỏ (sau >= 8 tuần paper, đủ cả 4): (a) paper >= phân vị 20 bootstrap
(`prospective_scorecard.py`); (b) DD paper <= 15%; (c) lệch bot vs plan <= 1.5pp/tháng; (d) không
`cycle_error` > 1h, không vị thế thiếu stop [DEPLOYMENT_PLAN_VI; BOT_RUNBOOK_VI].
Dừng: DD > 20% dừng mở mới; lỗ tháng > 10% halve vốn tháng sau; phân vị < 5 sau >= 8 tuần thì dừng
[DEPLOYMENT_PLAN_VI]. Kiểm hằng ngày: `bot_health.py` + `paper_report.py` + `prospective_scorecard.py`;
runbook đã được xác minh độc lập 2026-10-06 (core đúng, 11 issue văn bản, chưa đủ điều kiện live vì mới
paper < 1 ngày) [RUNBOOK_VALIDATION_20261006].

## 3. Kỳ vọng thực tế

Cửa sổ 12 tháng trượt, 49 cửa sổ (D17BF) [oc_rolling17]: min 2.73 / p10 3.25 / trung vị 4.89 / p90 8.88 /
max 11.71; DD min 8.3 / trung vị 13.5 / p90 18.3 / max 18.7; 49% cửa sổ >= 5%/tháng, 61% DD < 15,
100% DD < 20, không cửa sổ nào lỗ. Kỳ vọng trung vị ~5%/tháng, năm xấu ~3%/tháng [DEPLOYMENT_PLAN_VI].
Bootstrap khối dừng 10.000 năm (khối TB 20 ngày) [oc_mcdd; DEPLOYMENT_PLAN_VI]: trung vị 5.12 (p5 1.47 /
p95 10.32), chỉ ~52% năm >= 5%/tháng; P(năm lỗ) ~0.7%; DD marked trung vị 14.5%, p95 22.6%,
P(DD>20%) ~11%, P(>25%) ~2.1%. Vốn phải chịu được DD 25%.
KPI tháng (61 tháng) [oc_kpi]: 41% tháng >= +5%, 72% tháng không lỗ, chuỗi lỗ dài nhất 2 tháng (không bao
giờ 3 tháng lỗ liên tiếp).
Tuần xấu (G2+trần 2x) [oc_stresshist]: tệ nhất 2023-12-27..2024-01-03: -12.3% (DD 13.9%, hồi ~54 ngày;
không trần BF: -14.7%/DD 16.3%); các tuần xấu khác 2025-10-10 -9.7% (hồi ~134 ngày), 2024-07 -9.6%,
2023-06 -8.6%, 2024-06 -8.9%; FTX 2022-11 -2.2% (DD 9.2%), LUNA 2022-05 -3.0% (DD 9.7%). Tâm lý chuẩn:
vài lần mỗi năm mất 8–12% trong một tuần, mất 1–4 tháng về đỉnh cũ [DEPLOYMENT_PLAN_VI].
Bối cảnh 2026-09 (không phải dự báo) [DEPLOYMENT_PLAN_VI]: trên MA200, vol thấp, trend 90d +35%; nhóm lịch
sử này 21 tháng, TB +8.1%, trung vị +5.0%, 29% tháng âm, tệ nhất -7.5%.

## 4. Frontier return-vs-DD và trạng thái stretch

Mọi overlay rủi ro đi dọc một frontier duy nhất, không có DD miễn phí [research-map 2026-10-06; oc_frontier].

Biên yearly-DD (R / DD năm) [oc_frontier]: R2B1 4.55/13.88 – D13 4.957/15.00 – X45 5.118/15.92 –
G2F20K20 5.346/16.20 – G2 5.41/16.91 – G15K20 5.731/16.96 – G2K20 5.874/17.79 – D20B11 5.894/21.21.
Biên full-path [oc_frontier]: D15B08 4.626/14.94 – F20K17 5.042/15.47 – X45 5.118/15.81 –
G2F20K20 5.346/16.02 – S5 5.416/16.62 – S6 5.565/16.71 – G15K20 5.731/16.76 – G2K20 5.874/17.69 –
D20B11 5.894/19.10. Pick triển khai D17BF (5.425/18.33/16.90) nằm TRONG cả hai biên (thua yearly trước
G2K20, thua full-path trước S6), đã audit PASS [oc_frontier].
Stretch DD < 15: trong v399–v423 không hàng nào đạt DD < 15 ở CẢ hai metric cùng lúc [oc_frontier];
điểm biên mở rộng v424 D13BF đạt 4.97 / năm 14.98 / toàn đường 14.86 — tức stretch DD chỉ gặp được ở
~4.97%/tháng, dưới base 5% [research-map 2026-10-06]. Win > 60% đã đạt (all-trade 65.5%) [oc_kpi];
8%/tháng còn xa (max biên ~5.9 ở DD > 17.5) [oc_frontier].

## 5. Đã thử và đóng (một dòng mỗi họ)

v390 covariance book sizing: không hạ DD → loại [research-map]. v391 tournament sizes (R2K/R2C/R2T): fold3
thua 0.0014 fitness → không chuyển [research-map]. v392 kelly scale: size vào episode sai → loại.
v393 MANUAL size tables (M5K/M5C < M5) → giữ M5. v394 sizes+stop6: R2CS6 dev đạt base/DD đầu tiên nhưng fold
chọn R2K → không chuyển. v395 GATE năm giấu scored ONCE: R2CS6 3.48/DD 25.15 (R2-4P 3.90/18.8) → FAIL toàn
gate; bài học: dip-sizing dev cần bằng chứng paper trước mọi đổi chọn-dev [CONTINUOUS_RESEARCH 2026-10-05].
v396 risk-to-book: fold giữ R2 → loại. v397 EMA/long-only book: shorts hedge, smoothing trễ → loại.
v398 dip 11 coin: alt yếu, crash-correlated → giữ majors-only. v399 corr-size B1: đột phá DD (13.88) nhưng
rớt return. v400 bơm rủi ro lại (R2B1_130): base pass đầu tiên → chọn. v401 rung 2.0sg / v402 flush sớm /
v403 book loss control / v404–v405 governor: DD xuống thì return xuống → loại. v406 book→dip (D16/D18B08):
pass cả full-path DD → base PASS. v407 dip x2.0: vượt DD → loại. v408 D18: hàng BOT tốt nhất lúc đó.
v409 frontier phân bổ về DD: chỉ để vẽ biên. v410 bear-book (long x0.5 khi BTC<mean1200): có lợi, DD lẫn →
D16BF/D18BF. v411 D17BF: deployment pick (ma sát mọi hàng DD<=20, win 65.5%). v412 short gate (lợi mỗi
2023) / v413 ladder giờ+ (DD 30–38, thất bại giờ thứ 4) / v414 DVOL size tilt (return+DD cùng lên) → loại.
v415 close-stop 5/6sg: không hạ DD, fold giữ D17BF (lệch chạy-trước-đăng ký đã công bố) → loại. v416
dominance tilt (DD 20.45) → loại. v417 cascade cooldown/XRP-stop (post-hoc, fold không chuyển) → loại.
v418 DVOL gate short (recent 4.50) → loại. v419 breaker/budget (post-hoc, trung tính) → đóng. v420 flush
multiplier: chỉ dịch biên. v421 gross cap G2 (cùng return, DD -1.4): pick an toàn. v422 cap+size (G2K20 tốt
nhất R nhưng fold rớt recent + post-hoc) → không deploy. v423 bỏ rung sâu: DD xuống return xuống, chỉ để
vẽ biên (audit PASS). v424 stretch D13BF: biên DD<15 ở 4.97 → dưới base.
Screens OpenCode đóng: rip-sell (mọi rule 5y âm, bất đối xứng flush-hồi/spike-không) [research-map];
slow regime (dấu flip ≥2/5 năm); Wikipedia/CME gap (mỏng, chỉ log); Deribit skew/put-flow/Coinbase premium
context, pre-bar RV skip, 1h confirm, VRP dial (nghịch 2022), funding surprise (đuôi 3/5), premium-flip veto,
dominance-momentum throttle (đuôi 3/5), capitulation volume; MANUAL top-2 dip; WF per-coin stop / coin WF
weight / stop cooldown (cộng dồn, đuôi tệ hơn); velocity guard / soft B1 / adaptive sigma / deep-rung fast TP /
bull-book boost / RL bear-feature (V0 khớp exact) / daily ladder / cap đơn lẻ; basis momentum / bear-bar fast
TP / book brake / book-dip overlap / B1-BTC / deeper B1 (DD xuống 5/5 nhưng tổng xuống 4/5) / weekend /
macro blackout / MANUAL static corr proxy (0/5); tournament size/TP models (kelly/context/TP thua regime mới;
TP=+TP1.5 đã thua ở v391R2T) — hướng size/TP dip ĐÓNG [research-map 2026-10-06].
MANUAL caps: trần đặt lệnh G15/G10 hạ DD (17.8→14.9→13.5) nhưng tốn ~0.7/1.1pp/tháng, rung nhỏ thu hẹp cả
hồi phục trả tiền cho crash-fill, budget lại nhận THÊM rung nhỏ (6417→6806 fills) — hướng cap thuần túy
ĐÓNG, cần edge entry trước [oc_manualcap]. Đặt trước nến đêm (stale mức bar trước): R 2.92/DD 25.25,
tệ hơn M5_human → không đặt đêm [oc_manualnight results.json].

Bổ sung đóng đợt 2026-10-06 sau cập nhật trước (mỗi hướng một dòng, số y nguyên báo cáo):
- Quy tắc thang dip: oc_btclead — BTC-lead làm sâu giá bid alt theo beta BTC: tổng năm thua cả 5/5 (FULL 10.33 so với
BASE 15.14; mean 17.5 so với 27.4 bps, win .678 so với .705), DD chỉ tốt hơn 1/5 — fills mất 9% (4998 so với 5498)
toàn trúng winner mà không có đuôi bù → đóng, giữ B1 size-only [oc_btclead]. oc_rungcap — trần 3 fills/coin/bar
(cắt rung sâu 4-5 cùng nến crash): giữ ≥97% tổng 0/5 năm (tốt nhất 91% năm 2023; raw FULL 7.45 so với 9.67),
DD tốt hơn chỉ 3/5 — rung bị cắt win 72-83%, mean +15..+83 bps toàn winner đáy crash → đóng [oc_rungcap].
- Quy tắc book: oc_bookcorr — co giãn book theo tương quan (s=clip(1.5−rho,0.5,1.0), ý tưởng #43): DD tốt 5/5
nhưng giữ ≥90% P&L chỉ 1/5 (retention 0.73/0.88/0.92/0.83/0.74, bám sát mức co 0.70-0.85x vì rho 0.65-0.80 quanh
năm) — deleverage gần như thường trực, không phải edge DD → đóng [oc_bookcorr]. oc_coinbear — bear-book mở rộng
theo từng coin (long x0.5 khi BTC bear HOẶC chính coin dưới mean-1200, ý tưởng #44): DD không tệ hơn 3/5,
P&L ≥95% 3/5, cửa grind 2023-04-17..06-15 gần như không đổi (−0.0504→−0.0506) — không chạm đúng episode cần cắt
→ không đăng ký engine [oc_coinbear]. oc_longcap — trần tổng long book 0.6 (ý tưởng #46): giữ ≥95% P&L 0/5 năm
(0.848-0.948), DD không tệ hơn 1/5 strict, cửa grind còn tệ hơn (−0.0499→−0.0511) — bleed nằm ở bar không binding
(chỉ bind 9.1% bar), trần chỉ cắt winner nơi khác → đóng [oc_longcap]. oc_cadence — book cadence chậm 8h
(ý tưởng #47): P&L hơn base 2/5, DD không tệ hơn 1/5 (12h: 2/5 và 3/5) — tiết kiệm phí (~0.011/5 năm) nhỏ hơn
một bậc so với độ trễ stale-gross → đóng [oc_cadence].
- MANUAL: oc_manualtsmom — M5_human + sleeve TSMOM-30d: overlay 0.25x lên 3.90%/tháng (+0.17pp, excess +5/5)
nhưng DD cũng tệ hơn 5/5 (19.33), đòn cao hơn vỡ DD<20 mà vẫn xa 5%, split thì return rơi (2.53 ở 0.50) —
add-on tương quan, không phải edge còn thiếu → đóng [oc_manualtsmom].
- Chẩn đoán (ghi nhận, không phải hướng đóng): oc_ddanat_g2 — DD gate G2 16.91 là grind chậm đồng bộ
2023-04-17→06-15 (~59 ngày, book long −9..−11 + dip stop/timeout −7..−10 mỗi phase, BNB dẫn đầu, short bù +6.8
gộp) — muốn <15 phải cắt ~11% thiệt hại cửa sổ; cascade một-bar 2024-01-03 (15.81) đã nhỏ hơn BF ~2.5pp nhờ
trần G=2.0 [oc_ddanat_g2]. oc_grindsignal — không có tín hiệu fear/crowding/washout báo trước; cực trị lặp lại
duy nhất là breadth=1.0 (E0/E2/E3 max, E1 0.8) — DD bắt đầu từ đỉnh mở rộng toàn diện, gate tương lai phải điều
kiện trên over-extension chứ không phải stress [oc_grindsignal].

## 6. Việc còn mở (tươi 2026-10-06)

Trần dip của bot (bot_capfix): FIXED và tốn ~không — bản engine-faithful (room = G×vốn − notional OPEN đã fill,
bound cứng 2×G): C_on 3.20%/261 fills so với A không trần 3.58%/271 (trần cũ 1.12%/209, lệch −5.98pp → −3.90pp);
code bot/mirror.py đã sửa cục bộ (chưa commit), tests đã cập nhật — còn lại: merge, chạy lại paper có trần, rồi
mới quay lại lệnh 4-flag [bot_capfix; BOT_RUNBOOK_VI; RUNBOOK_VALIDATION_20261006 ISSUE-01].
Mô hình book C1/C2: audit mù FAIL ở F1 (C2 dùng chính label rank42 làm feature — common_impl.py:251-256; kèm W1
split calibration random, W2 allowlist mong manh, N1 vòng lặp chết) → fix đã dispatch
[docs/opencode/OPENCODE_W_oc_bookmodel_fix.md], code đang sửa (chưa commit) → re-audit → Kaggle C1 ~3-6h CPU /
C2 ~0.5-1h → chọn trên 2021-2024 [oc_bookmodel_audit COMPARISON/AUDIT; oc_bookmodel_impl].
Bằng chứng paper: 5 thư mục bot đang chạy trên đĩa (paper/R2-4P, paper_d17bf, paper_d17bfg2, paper_g2k20 từ
2026-10-05, paper_d13bf từ 2026-10-06); assignment ghi 6 bot — leader xác nhận roster bot thứ 6; divergence
paper-vs-plan (ngưỡng go-live 1.5pp/tháng, ≥14 ngày mới kết luận) theo ops_divergence
[docs/opencode/OPENCODE_W_ops_divergence.md]; go-live vẫn cần ≥8 tuần + đủ 4 điều kiện [DEPLOYMENT_PLAN_VI].
Dữ liệu liquidation/top-of-book: collectors KHỎE từ restart 2026-10-05 17:40 UTC (9.06h sạch, 0 gap>60s,
326.813 topbook rows, 802 liq, ~27MB/ngày) — tích 4-12 tuần mới có feature; oc_liq còn ngắn,
oc_topbook/oc_venuegap chờ [oc_collectors; research-map].
Margin study: XONG [oc_margin] — Bybit cross margin Hedge Mode, leverage tối thiểu không bao giờ kẹt lệnh là 5x
(3x kẹt 22 phút-mix; 10x/20x không an toàn hơn trong cross), G2 max ~3.4x vốn (không trần ~7.1x), phút tệ nhất cần
−29% mới cháy, gap −10%/−20% không phút nào cháy trong 5 năm → runbook: cross + 5x cả 5 coin, không Isolated.
Lead mở duy nhất sau đợt này: brake DD theo từng coin PROMISING (DD 4/5, P&L 4/5, cắt ~30% book loss cửa grind
−0.0504→−0.0354) [oc_bookcoinbrake] → đăng ký engine version + paper; giả thuyết breadth-1.0 [oc_grindsignal]
cho rule sau; v425 (trần trên hàng conservative) đã pre-register; giữ D17BF+G2 cố định, không đổi theo kết quả
gần đây (walk-forward 31 biến thể thua giữ cố định: 6.03 so với 6.08) [oc_wfselect; DEPLOYMENT_PLAN_VI].

## 7. Caveat trung thực

Cả 5 năm walk-forward nay đều là research data (đã nhìn) — mọi con số trên là trần của thông tin hiện có,
không phải bảo đảm tương lai; kiểm sạch duy nhất là log paper triển vọng trên dữ liệu chưa tồn tại lúc
đóng quy tắc [AGENTS.md selection rule; DEPLOYMENT_PLAN_VI; CONTINUOUS_RESEARCH 2026-10-05 v395].
Thước đo cũ (mix 4 pha liên tục) từng phóng đại các năm sau (pha-0 may mắn 43x chi phối); mọi số trên đã
dùng thước đo cân lại 1/4 mỗi đầu năm [DEPLOYMENT_PLAN_VI; research-map Lessons].
Mục tiêu 5%/tháng DD<=20% với MANUAL CHƯA đạt trung thực (~3.7 ở DD~18, tay người tốn ~0.6pp, chạy 80% vốn
để DD<20 chỉ còn ~2.8%/tháng) [DEPLOYMENT_PLAN_VI; research-map].
Kỳ vọng BOT hợp lý là 4–6%/tháng với DD 12–18%, nhưng ~1/9 năm có thể chạm DD>20%; vốn phải chịu được DD
25% [DEPLOYMENT_PLAN_VI; oc_mcdd].

## Bổ sung: KPI cấu hình triển khai G2 (OpenCode oc_kpi_g2)

R2B1D17BFG2 (D17BF + trần notional dip 2x): 5,41 %/tháng, DD năm tối đa 16,91, toàn đường (gate) 16,82, gấp 26,4 lần sau 5 năm,
win tất cả lệnh 65,3 % (book 51,5 %, rung dip 68,6 %), không năm lỗ; 41 % số tháng >= +5 %, 70,5 % số tháng không lỗ, chuỗi tháng lỗ
dài nhất 4 tháng (2024-04..07; D17BF: 2 tháng). Gross tổng tệ nhất 3,0x vốn (D17BF 6,4x). => BOT đạt base cả 3 chỉ số.
Lưu ý: cách bot hiện cài `--dip-gross-cap` chặt hơn engine (đang sửa: bot_capfix); số trên là engine.

## Bổ sung: stretch DD < 15 (OpenCode oc_tsmom_official, thước đo chính thức)

Hồ sơ thận trọng R2B1D13BF (dip x1,3 + bear-book): 4,97 %/tháng, DD năm 14,98, toàn đường 14,86 (đạt DD < 15, thiếu 0,03 %/tháng).
Thêm sleeve TSMOM 0,10: 5,03 %/tháng nhưng DD năm 15,42 (vượt 0,42 pp). Không tổ hợp nào đạt đồng thời >= 5 %/tháng và DD < 15 trên
thước đo chính thức. Bot paper D13BF (`--dip-mult 1.3 --bear-book`, tag d13bf) chạy từ 2026-10-06 để thu bằng chứng tiến cứu.

## Bổ sung: rủi ro may mắn của seed agent (OpenCode oc_agentens)

Bảng agent R2 đang triển khai là seed TỐT NHẤT trong 5 seed ở 2022 và năm gần nhất (2025), hạng 2 năm 2023, hạng chót năm 2024; độ phân
tán giữa các seed đáng kể. Bỏ phiếu 5 seed không tốt hơn (năm tệ nhất kém hơn). Hàm ý: các con số backtest của R2 có thể hơi lạc quan vì
may mắn của seed ở cấp rung. NHƯNG chạy engine đầy đủ G2 với 5 seed (OpenCode oc_seedengine): 5y 5,34-5,43 %/tháng (trung bình 5,39, seed triển khai 5,41, hạng 2/5), DD toàn đường 16,5-17,0, không năm lỗ ở seed nào -> may mắn seed gần như triệt tiêu ở cấp danh mục (~0,02 %/tháng). Kỳ vọng G2 ~5,4 %/tháng trên giá Binance, ~4,9 trên giá Bybit.

## Bổ sung: hồ sơ thận trọng D13BF dưới ma sát (OpenCode oc_d13robust, oc_kpi_d13)

D13BF (dip x1,3 + bear-book): gốc 4,97 %/tháng, DD năm 14,98 / toàn đường 14,86. Dưới mọi ma sát DD vượt 15 (chi phí x2: 4,27 / 15,51;
trễ 15': 4,79 / 15,08; trễ 30': 4,16 / 15,62; trượt stop: 4,56 / 15,90). => DD < 15 chỉ đạt trên giấy, không bền dưới ma sát thực tế;
hồ sơ thận trọng nên kỳ vọng ~4,2-4,8 %/tháng với DD ~15-16. Cấu hình triển khai chính vẫn là G2 (DD 16,9; ma sát giữ DD <= 18,1).

## Bổ sung: trần dip của bot đã sửa khớp engine (OpenCode bot_capfix, cửa sổ 09/2026)

Cửa sổ dùng: 2026-09-01..2026-09-23 holding bars (tận dụng plans bot_parity/snaps_cache.json; baseline engine từ bot_parity/results.json,
không chạy lại; cửa sổ assignment 2026-08-01..09-23). Baseline engine trên cửa sổ: 0,0710 (+7,10%), dip fills 219, book fills 83.
Bản sửa (bot/mirror.py, cap on): mỗi bid dip chờ = min(size thường, room), room = G x vốn sub − notional dip OPEN đã fill (KHÔNG trừ
các bid chờ khác), tính lại mỗi cycle; bound cứng an toàn open + resting <= 2 x G x vốn sub. Mặc định cap off giữ bit-for-bit.
Có trần C_on (cap 2.0, adopt on = cấu hình triển khai): ret 0,0320 (eq 10320,27), gap −0,0390, dip 261, book 19. Không trần A_off:
ret 0,0358 (eq 10357,95), gap −0,0352, dip 271, book 18. Trần cũ (bot_parity_adopt C_adopt_cap2): ret +1,12%, dip 209, book 19,
gap −5,98pp. => FIXED: dip 209 → 261 (so với 271 không trần), phí 62,3 → 76,9 (so với 80,7), return +1,12% → +3,20%.
Kết luận: có trần chỉ thua không trần 0,38pp (3,20% so với 3,58%), so với trần cũ tốn 2,46pp (1,12% so với 3,58%) — tốn ~không
như trần G2 của engine; adopt cộng cùng +1 book fill dù có/không trần [bot_capfix].

## Bổ sung: trượt stop thực tế (OpenCode oc_stopslip) — vì sao cần trần gross

Universe: mọi exit `book_stop` (773) + `rung_sl` (926) của R2B1D17BFG2 gộp 4 phase = 1699 stops, phút exit 2021-10-27..2026-09-22.
Slip thực = bps bất lợi của open phút kế so với stop; S4 = 0,5 x xuyên trong biên của cùng phút exit; phủ 100% cả hai venue,
không hàng nào >= 2026-09-24. Trung vị gộp: −4,6 Binance / −1,6 Bybit (open kế thường hồi vài bps so với stop; chỉ 45% Binance /
48% Bybit có slip dương), nhưng đuôi phải dữ dội: p90 +146/+197, p99 +495/+738, max +813/+1347 bps. S4 tính ~18–19 bps trung vị
(18,2/19,0), phân số trung vị −0,49 Binance / +0,09 Bybit: ở trung vị fill market open-kế TỐT HƠN stop, tức S4 bảo thủ; nhưng phụ
thuộc regime — 2021 (frac ~0,5..1,5 cả hai venue) và vài ô BNB/ETH 2022–2024 (frac ~0,6..1,5) NGANG/TRÊN vạch S4, còn năm crash
SOL/XRP âm sâu (snapback sau stop). Bybit nóng hơn Binance ở 8/10 ô trung vị dương; 7,2% stops thanh Bybit không hề chạm stop
suy từ Binance (S4 = 0 ở Bybit so với 0,5% ở Binance) — râu venue khác nhau. Flash: 75,5% Binance / 74,7% Bybit (biên phút exit
trung vị ~146 bps so với mean trailing ~16 bps — stop vốn cụm trong burst). Top-10 tệ nhất toàn stop long rung dip trong hai burst
crash: FTX 2022-11-09 (SOL, Bybit 1347 bps do venue gap — Bybit ~9,05–9,35 trong khi Binance ~10,29–10,46) và flush 2024-01-03
(XRP, −10%/phút). Verdict một dòng: S4 bảo thủ ở trung vị, xấp xỉ công bằng trong biến động kiểu 2021, và quá nhỏ cho đuôi crash
— đó là lý do trần gross 2x tồn tại (phút tệ nhất gap −10% không trần lỗ 58% vốn, trần 2x còn 33,5%) [oc_stopslip].

## Bổ sung: phí VIP (OpenCode oc_vipfees)

Cấu hình R2B1D17BFG2, repricing cộng từng bar (gross giữ nguyên): 57.365 fee legs; maker |w| 1741,9, taker |w| 549,9 sub-units.
Gate VIP0 maker 0,0200% / taker 0,0550%; VIP1/VIP2 là giá trị GIẢ ĐỊNH đối chiếu lịch derivatives công khai Bybit 2026-10-06:
VIP1 maker 0,0180% / taker 0,0400%, VIP2 maker 0,0160% / taker 0,0375%; ngưỡng volume công khai giả định VIP1 >= 10M USDT,
VIP2 >= 25M USDT. Gain 5 năm (mix liên tục 60 tháng 2021-10..2026-09): 5,6066 → VIP1 5,7183 (+0,1117) → VIP2 5,7657 (+0,1590)
%/tháng; net 5y VIP0 2539,21% → VIP1 2712,02% → VIP2 2788,60% (tương đương +1,35%/năm và +1,92%/năm; saving TB tháng 0,114% /
0,163%). Win nhích không đáng kể (rung +0,41pp/+0,51pp, book +0,10pp/+0,14pp, all +0,35pp/+0,44pp); DD không đổi (đường VIP pointwise
>= VIP0). Vòng quay tau = 22,98x vốn/tháng: 5.000 USDT → 114.879/tháng (1,1%/0,5% ngưỡng, tiết kiệm 5,70/8,13 USDT); 10.000 →
229.758 (2,3%/0,9%, 11,40/16,26); 50.000 → 1.148.790 (11,5%/4,6%, 57,02/81,31). Cần ~435.241 USDT để chạm VIP1 và ~1.088.101 USDT
cho VIP2 chỉ bằng volume (đường asset công khai ~$100k/$250k cũng ngoài tầm 5–50k) — triển khai giữ phí VIP0 [oc_vipfees].

## Bổ sung: paper ngày đầu (OpenCode PAPER_DAY1_20261006, 2026-10-06 ~03:28 UTC)

Phạm vi: 5 thư mục có mặt `paper`, `paper_d17bf`, `paper_d17bfg2`, `paper_g2k20`, `paper_d13bf` (không có bot thứ 6);
`d17bfg2`/`g2k20` đã restart với `--adopt-fresh` + fix double-spend ngày 2026-10-05. daily_status.py exit 1 = WARNING duy nhất
do `paper` dính rate-limit; backend sống (plan gen `2026-10-06T03:01:12Z`, tuổi 0,5h); equity/return/maxDD/fills(dip/book): `paper`
4998,74/−0,03%/0,09%/0/6; `d17bf`, `d17bfg2`, `g2k20` mỗi bot 4999,46/−0,01%/0,01%/0/4; `d13bf` 4999,64/−0,01%/0,01%/0/3. Collector
4 feed sống nhưng mỗi feed 1 gap >5p/24h, liq gap max 16933s (~4,7h) — cửa sổ backend outage. paper_divergence.py toàn "too early"
(<14d, chưa PASS/FAIL; số pp/tháng trên <1d là nhiễu). bot_health.py: cả 5 cycle sống 3–25s, plan 0,5h, unprotected=none,
qty_mismatch=none; còn lại OK. Fill toàn book (limit đúng giá), 0 dip fill ngày đầu; exit 0 mọi nơi (chưa TP/stop/time exit nào);
mọi piece mở đều có cả stop+TP. Xử lý stale-plan đúng: 14:03–18:13 không fill nào (stale 355/281/52/83), plan kẹt 12:03:26Z do backend
outage 12:39–17:40, sau ~18:13 bám plan tươi lại; `plan_error` 0 khắp nơi. Bất thường/không: (a) `paper` 15x cycle_error 10006
06:00–12:01 10-05 là runner-cụ thể (chia quota kline public), không phải bug plan; (b) `skipped_below_minimum` 596–701 dòng/bot
(vài rung BTC sâu dưới minimum Bybit ở equity 5000, 1 log/cycle — ồn nhưng erwart); (c) không lệnh lặp/double-spend (market_exit 0,
fix giữ). Vấn đề trước testnet: CRITICAL chưa có; WARNING tách quota kline + báo động stale-plan sớm hơn (>4h30m hiện tại là muộn)
và runbook ca trực khi backend chết; LOW gộp log skipped + dán nhãn "closest plan v376 R2-4P" cho divergence bot cấu hình khác
[PAPER_DAY1_20261006].

## Bổ sung: screens mới đóng đợt 2026-10-06 (mỗi hướng một dòng, số y nguyên báo cáo)

- oc_agentskip (idea #57, SKIP khi cả hai nửa HGB y1.0 < −0,002): sum>=base 2/5 (2021, 2022), DD không tệ hơn 4/5 (trừ 2023) —
NOT PROMISING; gate chỉ đúng 2021 (rung bị loại mean −0,004828), 2023–2025 loại toàn winner (+0,003463/+0,001478/+0,000848) [oc_agentskip].
- oc_b1wide (B1-wide size x 1/(1+n_wide), n_wide = n + 0,5*n_alt alt BCH/DOT/ETC/XLM/ATOM): sum>=97% 3/5 (2021, 2023, 2024),
DD 0/5 (tệ hơn cả 5 năm; full sum 96,2%, DD 1,79→2,01, worst day tệ hơn 5/5; 2022 0,27→0,01, 2025 −28%) — NOT PROMISING, giữ B1 [oc_b1wide].
- oc_bookfunding (idea #56, tilt x0,75 long khi funding 7d > p80 walk-forward): P&L>=97% 3/5, DD không tệ hơn 3/5 (2023 fail cả hai;
5y −8,8%; 2023 tilt-on 63% long, total −15,5%) — NOT PROMISING, funding nóng đánh dấu long khỏe chứ không phải squeeze để fade [oc_bookfunding].
- oc_tpdecay (TP decay 1,0sg→0,5sg): sum 3/5 (2021 +0,09, 2022 +0,18, 2024 +0,20; 2023 −0,28, 2025 −0,04), DD 1/5 (chỉ 2023 đỡ;
timeout 41%→31%, win +1..+4pp mọi năm nhưng full sum chỉ +1%, worst tệ hơn 4/5) — NOT PROMISING, giữ TP +1,0sg cố định [oc_tpdecay].
- oc_trendladder (depth theo trend BTC r30: mult 0,85 up / 1,15 down): sum 3/5 (2021–2023 đỗ, 2024 −0,39, 2025 −0,46), DD 2/5
(2023 0,41→0,77, 2024 0,33→0,52, 2025 1,13→1,74 với worst −1,66 so với −0,90; full 15,14→16,97 chỉ nhờ 3 năm tốt) — NOT PROMISING,
giữ depth R2 cố định [oc_trendladder].

## Bổ sung: vì sao bot chạy bốn đồng hồ (OpenCode oc_phasedisp)

R2B1D17BFG2 theo từng đồng hồ đơn (reset mỗi anchor, R %/tháng, DD % trong năm) so với mix 4 pha (mỗi pha 1/4 vốn mỗi anchor) [oc_phasedisp]:

| năm (anchor→+365d) | phase0 (0h) | phase1 (1h) | phase2 (2h) | phase3 (3h) | mix 4 pha |
|---|---|---|---|---|---|
| 2021-09-24 | 4,567 / 13,41 | 2,919 / 22,46 | 2,153 / 13,70 | 0,188 / 15,94 | 2,588 / 10,86 |
| 2022-09-24 | 3,571 / 16,91 | 3,942 / 15,67 | 3,226 / 17,39 | 2,312 / 17,99 | 3,282 / 16,91 |
| 2023-09-24 | 11,249 / 14,56 | 4,226 / 18,91 | 6,412 / 20,07 | −2,431 / 43,23 | 6,045 / 15,81 |
| 2024-09-24 | 10,023 / 10,75 | 9,645 / 15,22 | 11,849 / 10,14 | 11,040 / 10,90 | 10,677 / 8,27 |
| 2025-09-24 | 5,427 / 11,88 | 3,577 / 21,21 | 4,590 / 13,69 | 4,905 / 14,21 | 4,648 / 12,90 |
| TB 5 năm | 6,923 | 4,834 | 5,592 | 3,102 | 5,410 |
| năm tệ nhất | 3,571 | 2,919 | 2,153 | −2,431 (lỗ) | 2,588 |
| DD năm tối đa | 16,91 | 22,46 | 20,07 | 43,23 | 16,91 |
| DD toàn đường | 16,91 | 22,46 | 20,07 | 43,55 | 16,82 |

Đọc: chỉ lệch 1–3 giờ cắt 4h mà đơn lẻ phân tán 5 năm 3,102–6,923 %/tháng, DD toàn đường 16,91–43,55 %, năm tệ nhất đơn lẻ xuống −2,431 %/tháng
(phase3, 2023) trong khi mix vẫn +2,588 %/tháng và không năm nào lỗ; không đồng hồ đơn nào thắng mọi năm (nhất năm xoay 2021→p0, 2022→p1,
2023→p0, 2024→p2, 2025→p0), mix không thắng năm đơn nào nhưng cũng không thua năm nào [oc_phasedisp].
Quy tắc vận hành theo đó: không bao giờ chạy một pha đơn lẻ; pha bị restart/thiếu phải khôi phục xong mới được tin các số mix (mix là cách khóa
chênh lệch giờ, không phải để cộng thêm lợi nhuận) [oc_phasedisp].

## Bổ sung: độ nhạy blend 0,8/0,2 của book BOT (OpenCode oc_blendsens — sensitivity, no selection, không đổi)

Book legs dựng đúng `oc_dvolshort` (`o1` + `dmean=(D+Dq)/2`, blend `w(alpha)=alpha*o1+(1-alpha)*dmean`, alpha {1,0 O1-only; 0,9; 0,8 triển khai;
0,7; 0,0 D-only}), bear v410 FIRST, screen open-to-open 4h net `wb*R1−0,0005*|wb−wprev|` trên 10955 bars x 5 coin = 54775 rows [oc_blendsens].
Verdict y nguyên: NOT a clean plateau (sensitivity, no selection): bước cục bộ qua 0,8/0,2 trái dấu theo năm (E1/E2 same-sign 3/5, LOYO 2/5 —
không đạt ngưỡng mặc định 4/5 + 4/5) và KHÔNG nhỏ (mean adjacent step 0,0134 >= ngưỡng đăng ký trước 0,01); 2024 kéo về O1 (+0,033/step)
trong khi 2025 kéo về D (−0,019/step) [oc_blendsens]. Deployed 0,8/0,2 luôn interior (không năm nào nhất/cuối: 2021/2022/2024 phe O1 thắng,
2023/2025 phe D thắng); worst week phẳng mọi blend (chênh <= 0,7pp mọi năm); full 5y interior DD thấp nhất (O1 0,106606 / 0,9 0,105548 /
0,8 0,104644 / 0,7 0,104086 / D 0,130199), D-only vọt DD 2021 (0,130) và 2024 (0,123) [oc_blendsens]. Độ dốc nhỏ nhưng đổi dấu theo regime —
không plateau sạch, không chọn lại, giữ nguyên 0,8/0,2 [oc_blendsens].

## Bổ sung: PostOnly entries + risk guard (OpenCode bot_testnetfix, docs/BOT_EXECUTION.md CHANGES bot_testnetfix)

F1: book entries/adds và dip rung bids gửi `timeInForce:"PostOnly"` (maker-only, đúng giả định fill của research và `bot/paper.py`); TP/reduce
limit giữ GTC reduce-only; stops/market exits không đổi; PostOnly bị chạm bị từ chối (paper trả None, live lỗi PostOnly 110079/170146) thì
log `op=postonly_reject` và thử lại cycle sau cùng giá, không bao giờ đuổi thành market/taker [BOT_EXECUTION.md CHANGES bot_testnetfix].
V4: `bot/risk_guard.check()` lọc `want` sau cắt stale/plan_error và trước rounding/`diff` ở cả hai nhánh `Runner.cycle` (normal + ledger-only),
với equity sàn + ledger positions + giá đóng 1m mới nhất (rơi về 5m closes / plan marks), hạn mặc định per-coin 2,5x / dip 2,0x / total 4x /
single 1x; từ chối log `op=risk_reject` và không gửi, protection/reduce-only không bao giờ bị chặn [BOT_EXECUTION.md CHANGES bot_testnetfix].
Mặc định: ON ở testnet/live (`--no-risk-guard` mới tắt), OFF ở paper/dry trừ khi `--risk-guard` (paper giữ engine-faithful, vd R2-4P không trần
dip gross có thể vượt 2,0x) [BOT_EXECUTION.md CHANGES bot_testnetfix]; test ở `tests/test_bot_testnetfix.py` (`test_bot_mirror` entry payload
đã cập nhật PostOnly) [BOT_EXECUTION.md CHANGES bot_testnetfix]. QUICKSTART_VI bước 9 đã ghi: lệnh vào là PostOnly, risk guard bật mặc định,
`postonly_reject` = thử lại không đuổi giá, `risk_reject` trong log [QUICKSTART_VI].

## Bổ sung: screens mới đóng đợt này (mỗi hướng một dòng, số y nguyên báo cáo)

- oc_expirybook (idea #62, halving book x0,5 cả hai phía trong 48h trước expiry Deribit hàng tháng, 68 expiries, ~6,6% bars): PROMISING (as assigned) —
DD không tệ hơn 4/5 và P&L >= 98% base 4/5 (2021 fail cả hai: retention 0,932, DD 0,086514→0,090484; 2022–2025 window base lỗ −0,006..−0,031 nên halving
thành lãi nhỏ +0,003..+0,015; full 5y P&L 2,061253→2,077167 (+0,0159), maxDD 0,100471→0,090484; worst week y hệt mọi năm) — hiệu ứng nhỏ, parameter-free,
cần prospective [oc_expirybook].
- oc_expirycb (COMBINATION post-hoc oc_expirybook + oc_cbpremium, BOTH = expiry halving SAU premium tilt): NOT PROMISING (as assigned) — P&L cao hơn
base 4/5 (pass) NHƯNG DD không tệ hơn chỉ 1/5 (fail: chỉ 2022 đỗ cả hai, DD 0,0715→0,0667, P&L 0,2520→0,2748); full 5y both cao nhất 2,114578
(base 2,061253 / exp 2,077167 / prem 2,102446), maxDD both 0,089602 (base 0,100471 / exp 0,090484 / prem 0,102295) — tilt premium nuốt mất lợi DD
của expiry, cộng return mà không giữ DD [oc_expirycb].
- oc_cbpremium (idea #60, tilt long book x1,15 khi z>1 / x0,85 khi z<−1, tín hiệu premium BTC-only cho cả 5 coin trên base v410): NOT PROMISING
(as assigned) — P&L cao hơn 5/5 (pass) NHƯNG DD không tệ hơn chỉ 2/5 (2021 −0,30pp, 2022 −0,36pp đỗ; 2023 +0,01pp, 2024 +0,75pp, 2025 +0,39pp fail);
full 5y P&L 2,061253→2,102446 (+0,0412 toàn qua long leg), maxDD 0,100471→0,102295 (+0,18pp) — tilt chỉ cộng return bằng variance [oc_cbpremium].
- oc_skewbook2 (idea #59, gate long x0,75 khi BTC skew_z90 > walk-forward p80, q80 ổn định 0,61–0,67, coverage z 100%): NOT PROMISING (as assigned) —
P&L gated >= 97% base chỉ 1/5 (2025 0,976 đỗ duy nhất; ratios 0,89–0,98) và DD không tệ hơn 4/5; full 5y P&L 2,061253→1,960521 (−0,101), maxDD
0,087278→0,086447 gần như phẳng — đánh thuế long có lãi mà không hạ DD [oc_skewbook2].
- oc_basisbook (idea #61, gate long x0,5 khi basis impulse 7d < walk-forward p20, p20 −0,053367..−0,017200, coverage 1,0): NOT PROMISING (as assigned) —
P&L kept (>=97%) 4/5 VÀ DD không tệ hơn chỉ 3/5 (cần 4/5 cả hai); full 5y P&L 2,061253→2,072244 (+0,0110), maxDD 0,100471→0,098859 (−0,16pp);
2023 gãy cả hai (flag 16,8% bars nhiều nhất, P&L 96,7%, DD +0,07pp) — impulse chỉ mua DD khi collapse là stress thật, năm grind-up chỉ thuế long [oc_basisbook].
- oc_breadthbook (idea #63, brake long x0,75 khi breadth==1,0 — cả 5 majors trên mean 200d daily, on-share toàn cục 23,2%): NOT PROMISING (as assigned) —
DD không tệ hơn 5/5 NHƯNG P&L >= 95% base chỉ 2/5 (2021 91,3%, 2024 86,4%, 2025 94,2% fail; 2023 95,8% pass; 2022 103,4% pass duy nhất lãi);
full 5y P&L 2,061253→1,923118 (−0,1381, −6,7%), maxDD 0,100471→0,100471 (bằng) — 2024 on 42% bars bleed −13,6%, đỉnh mở rộng cứ lên tiếp [oc_breadthbook].
- oc_breadthdip (idea #64, dip size x0,8 khi breadth==1,0 tại open, bars on 2538/10956=23,2%): VERDICT NOT PROMISING — DD không tệ hơn 5/5 (bằng 2021/2023,
cắt 2022/2024/2025) NHƯNG sum >= 95% base chỉ 1/5 (chỉ 2025 99,6%; còn lại 83–94%: 2021 94,3% / 2022 83,0% / 2023 89,4% / 2024 85,7%); FULL BASE sum
9,671→RULE 8,729 (90,3%), fills breadth-on 1570/5498=28,6% (30,3% weight) toàn winner bị cắt — giữ B1 full-size [oc_breadthdip].
- oc_bookholdcap (idea #65, cap giữ tối đa 42 bars cùng dấu → flat 1 bar rồi resume, n_forced 129–184/năm ~1,2–1,7% cells): NOT PROMISING (as assigned) —
P&L RULE >= 97% BASE chỉ 2/5 và DD không tệ hơn chỉ 2/5 (chỉ 2024 đỗ cả hai: P&L 97,5%, DD 0,0653→0,0612); full 5y P&L 1,970907→1,883804 (−0,0871),
maxDD 0,104644→0,113519 (tệ hơn) — mỗi forced close phải mở lại nên cost +0,006..+0,017/năm (+45% tổng cost) [oc_bookholdcap].
- oc_fomcbook (idea #66, halving book x0,5 cả hai phía trên RULEBARs [R−24h,R+4h] quanh 56 FOMC scheduled, 40 cái trong span x 7 bars = 280/10955 bars
= 2,56%): NOT PROMISING (as assigned) — DD không tệ hơn 4/5 NHƯNG retention >= 98% chỉ 2/5 (chỉ 2022 1,0427 và 2024 1,0020 đỗ; 2021 0,9515 / 2023 0,9583 /
2025 0,9557 fail vì window P&L dương +0,026/+0,043/+0,033 nên halving tốn 4–5% P&L năm); full 5y P&L 1,970907→1,928287 (−0,0426), maxDD 0,104644→0,103597;
worst week y hệt cả 5 năm — đóng hướng [oc_fomcbook].

## Bổ sung: cash-and-carry trên vốn nhàn (OpenCode oc_cashcarry, BTC/ETH quarterlies)

Phương pháp khóa trước trong PLAN.md (vào 1 lần mỗi hợp đồng quý, ENTER iff basis năm hóa ln(F/S)*365/DTE >= 4%/yr, long spot + short quarterly
notional bằng nhau f mỗi coin rows 0.25/0.50, giữ tới delivery, phí spot 0.1%/side + futures 0.055% entry + 0.02% delivery = drag 0.275% allocated;
delivery futures KHÔNG trả funding nên rule funding perp AGENTS.md không liên quan; chỉ BTC+ETH vì SOL quarterlies từ 2024-09, BNB/XRP là
coin-margined không dùng; data `data/raw/qbasis_20261003`) [oc_cashcarry]. 50 contracts thấy (25 BTC + 25 ETH expiries 2021-03..2027-03)
-> 33 vào, 13 skip (basis < 4%), 2 incomplete (delivery 2026-12/2027-03 quá spot bar cuối, loại, không impute P&L); cả 33 lệnh vào đều net
dương (min +0.18% allocated); 8 pre-window (vào trước 2021-09-24, sum +0.292 allocated) loại khỏi stat 5 năm gộp [oc_cashcarry].

| năm (theo ENTRY; ret_alloc = P&L/allocated) | BTC n / mean basis / sum | ETH n / mean basis / sum | sum năm | worst MtM (alloc) | acct +%/th f=0.25 | acct +%/th f=0.50 |
|---|---|---|---|---|---|---|
| 2021-09-24 | 2 / 8.9% / 0.0261 | 2 / 8.0% / 0.0209 | 0.0470 | -1.01% | 0.098 | 0.196 |
| 2022-09-24 | 3 / 5.6% / 0.0424 | 1 / 5.7% / 0.0105 | 0.0528 | -0.71% | 0.110 | 0.220 |
| 2023-09-24 | 4 / 13.3% / 0.1579 | 4 / 12.7% / 0.1381 | 0.2960 | -2.65% | 0.617 | 1.233 |
| 2024-09-24 | 4 / 7.4% / 0.0638 | 4 / 7.4% / 0.0581 | 0.1219 | -0.39% | 0.254 | 0.508 |
| 2025-09-24 | 1 / 4.2% / 0.0058 | 0 (cả 5 skip, basis < 4%) | 0.0058 | -2.17% | 0.012 | 0.024 |
[oc_cashcarry].

Gộp 5 năm (25 trades in-window, sum 0.5234 allocated): f=0.25 cộng +13.09% sau 5 năm = +0.218%/tháng số học (+0.213%/tháng hình học);
f=0.50 cộng +26.17% = +0.436%/tháng số học (+0.416%/tháng hình học); bộ lọc idle đúng — năm gần nhất chỉ 1/6 cơ hội vượt 4%/yr nên sleeve
đóng góp ~+0.01%/tháng, không ép rủi ro khi không có premium [oc_cashcarry]. Worst MtM 4h-close mỗi năm trên allocated:
-1.01 / -0.71 / -2.65 / -0.39 / -2.17%; ra account x f: f=0.25 tệ nhất -0.66% (2023), f=0.50 tệ nhất -1.33% (2023) — nhỏ cạnh DD BOT ~17%,
sleeve không cộng quá ~0.7% (f=0.25) account DD dù widening tệ nhất trùng phút tệ nhất BOT [oc_cashcarry]. Margin (Bybit unified cross
5x Hedge Mode; haircut 5% BTC / 10% ETH là ASSUMPTION; short quarterly cần IM 5x trên mark, spot không IM; bound check MỌI 4h close
2021-09-24..2026-09-23 trên `oc_kpi_g2/barsum_s0..s3` + `v421_runs.pkl`; BOT gross <= book_gross(t) + trần dip 2.0, mix max 3.41,
per-phase max 3.78): worst IM/equity f=0.25: 0.53 / 0.53 / 0.57 / 0.67 (s0..s3); f=0.50: 0.55 / 0.55 / 0.60 / 0.72; blocked 0 mọi phase
(limit 0.95; phút tệ nhất 2023-10-24 vẫn >= 28% free); pair delta-hedged nên gap đều chỉ mất basis widening, maintenance thêm 0.5% x carry
gross (~0.5-1.0% equity); median ~93% equity free (oc_margin) nên spot f=0.25/0.50 mua bằng cash nhàn [oc_cashcarry; oc_margin].
Verdict y nguyên: USEFUL ADD-ON YES — yield nhỏ trung thực gần như không rủi ro, không phải goal-changer; kỳ vọng +0.21%/tháng hình học
ở f=0.25 (+0.42 ở f=0.50); ~57% gain 5 năm từ regime basis cao 2023, năm gần nhất ~+0.01%/tháng; đóng ~4-8% khoảng trống tới mục tiêu BOT 5%/tháng,
không tốn DD/margin đo được; deploy gợi ý f=0.25 mỗi coin theo đúng roll rule PLAN.md, cần paper triển vọng như mọi thứ (venue data là Binance,
live là Bybit; cơ chế delivery/settlement phải xác nhận trên venue live) [oc_cashcarry]. PENDING: nghiên cứu combo BOT+carry và khả dụng
Bybit (oc_carrycombo) chưa chạy — tới khi xong thì carry là add-on độc lập, chưa cộng vào số triển khai G2/D17BF [oc_cashcarry].

## Bổ sung: phương pháp sau 3/3 vectorised book screens rớt full engine (OpenCode oc_placebo, oc_premexpo, oc_usdt4p, oc_cmegap4p, oc_expiry4p, oc_placebo_dip)

Vectorised book screens FAIL full engine 3/3 trên cùng harness R2B1D17BFG2 4-phase (v421 wiring: phase_offset_full + pipe_setup("v321", agents on)
+ kd=1.7 corr-size + bear-book + G=2.0 cap + win_start=5; gate maker 0.0002/taker 0.00055; adverse long funding 0.0001; reset-metric year_reset +
v388.mix full-path DD; base tái tạo v421 exact 5y 5.41%/th, max yearly DD 16.91, full-path 16.82) [oc_expiry4p; oc_cmegap4p; oc_usdt4p]:
- oc_expiry4p (idea #62, halving book x0.5 cả hai phía 48h trước expiry Deribit hàng tháng, 68 expiries, 12 bars mỗi cái): VERDICT NO —
base 5.410 / worst 2.588 / maxDD 16.91 / full 16.82 / dev4 5.601 / win 0.6533 so với EXP 5.498 / 2.247 / 16.56 / 16.53 / 5.681 / 0.6525
(gap 5y +0.088, worst -0.341, maxDD -0.35pp, full -0.29pp); theo năm gap R: 2021 -0.341 (2.247/12.68 so với 2.588/10.86), 2022 +0.184
(3.466/16.56 so với 3.282/16.91), 2023 +0.625 (6.670/16.03 so với 6.045/15.81), 2024 -0.143 (10.534/8.39 so với 10.677/8.27),
2025 +0.121 (4.769/14.30 so với 4.648/12.90); KEEP cần full-path DD thấp hơn (16.53<16.82 YES) VÀ 5y>=5.30 (YES) VÀ không năm nào tệ hơn
>0.3%/th (2021 -0.341 NO) — rớt đúng chân thứ ba [oc_expiry4p].
- oc_cmegap4p (idea #69, tilt long theo CME weekend-gap proxy gap=P(Sun reopen)/P(Fri close)-1, DST winter Fri 21:00/Sun 22:00 summer Fri 20:00/
Sun 21:00, fill = trade-through đầu tiên của P_fri sau reopen trong 72h, active khi large-gap |gap|>2%: long x0.75 nếu gap>+2%, x1.25 nếu
gap<-2%, 262 weekends, 58 large 28 up/30 down, fill rate 0.50, active rows 742/10950 mỗi shift up 383/down 359): VERDICT NO — CME 5.424 /
worst 2.679 / maxDD 17.05 / full 17.03 / dev4 5.602 / win 0.6545 so với base (gap 5y +0.014, worst +0.091, maxDD +0.14pp, full +0.21pp);
gaps: 2021 +0.091 (2.679 so với 2.588), 2022 -0.081 (3.201 so với 3.282), 2023 -0.416 (5.629 so với 6.045), 2024 +0.430 (11.107 so với
10.677), 2025 +0.066 (4.714 so với 4.648); KEEP cần full-path DD thấp hơn (17.03<16.82 NO) VÀ 5y>=5.30 (YES) VÀ không năm tệ >0.3 (2023
-0.416 NO) — rớt chân 1 và 3 [oc_cmegap4p].
- oc_usdt4p (idea #71, tilt long book x1.15 khi z>1 / x0.85 khi z<-1 theo USDT/USD premium z từ Coinbase USDT-USD 1h 47240 rows
2021-05-04..2026-09-23, prem=close-1, mean24 rolling 24/min20, z=(mean24-trailing-2160 mean)/std shift 1, as-of end<=T-1s, coverage 100%,
median premium +0.5 bps, up 1909/down 2109 rows trên 10950): VERDICT NO — USDT 5.168 / worst 2.620 / maxDD 17.01 / full 17.00 / dev4 5.300 /
win 0.6521 so với base (gap 5y -0.242, worst +0.032, maxDD +0.10pp, full +0.18pp, dev4 -0.301, win -0.0012); gaps: 2021 +0.032 (2.620 so với
2.588), 2022 -0.143 (3.139 so với 3.282), 2023 -0.421 (5.624 so với 6.045), 2024 -0.701 (9.976 so với 10.677), 2025 -0.009 (4.639 so với
4.648); book-only attrib cũng thua 4/5 năm R và 5/5 năm DD (5y 2.200 so với 2.319, -0.119); KEEP cần full-path DD không cao hơn >0.3pp
(17.00-16.82=+0.18 YES) VÀ 5y>=5.45 (5.168 NO) VÀ không năm tệ >0.3 (2024 -0.701, 2023 -0.421 NO) VÀ dev4 cao hơn base (5.300>5.601 NO) —
rớt 3/4 chân [oc_usdt4p]. Live feasibility: GET Coinbase `/products/USDT-USD/candles?granularity=3600` window 2h HTTP 200, 3 candles,
0.517s, không auth — plan hourly khả thi [oc_usdt4p].
Ngay cả sau exposure + placebo book tilt vẫn rớt: oc_premexpo (control = constant long mult exposure-weighted in-year, placebo = 500
block-shuffles by run, z-vs-z corr full 0.878; costs 0.0002 unified): USDT ALPHA (gain vs control +0.049084, dương 4/5 năm, placebo 5y pct 99.4
mean -0.051517 sd 0.039581) / CB EXPOSURE (gain +0.035170, dương 5/5 năm, nhưng pct 88.2<95 mean -0.008337 sd 0.038409) / COMBINED ALPHA
(gain +0.042640, 4/5 năm, pct 97.2 mean -0.035501 sd 0.037056); rule ALPHA chỉ nếu gain>0 >=4/5 VÀ pct>=95 [oc_premexpo] — nhưng USDT ALPHA
vẫn VERDICT NO ở full engine trên [oc_usdt4p]. oc_placebo (seeded 1000 expiry-like + 1000 CME-like, seed 20261006, grid 10955 bars x 5 coins;
expiry-like 12-bar window/tháng coverage mean 0.066819 so với real 0.0648; CME-like 10 windows/năm len {12,18,24} coverage 0.081935 so với
real 0.0677; real rescored unified 0.0005: expiry dPnl +0.013292/dDD -0.008425 legs DD 3/5+ret98 4/5 FAIL, CME +0.005655/-0.0 legs pass
strict+loose): FPR expiry-like 0.037 (37 pass; DD>=4 0.302, ret>=4 0.082), CME-strict 0.002 (2 pass), CME-loose 0.024 (24 pass);
placebo dPnl mean expiry -0.077005 (p5 -0.163713/p50 -0.075762/p95 +0.005795/max +0.081580), dDD mean -0.001509; CME dPnl mean -0.003823
(p95 +0.042143), dDD mean +0.000324; real expiry percentile P&L 97.0 / DD 98.2% (genuine tail outlier nhưng vẫn fail leg-count unified vì tie
2023 6dp), real CME percentile 63.0/48.1 (typical random tilt — pass screen là selection luck, khớp engine NO 2023 -0.416%/th) [oc_placebo].
Gate thắt đề xuất (legs + joint placebo-tail: 5y dPnl>=placebo p95 VÀ full-path dDD<=placebo p05; gates expiry +0.005795/-0.007659, CME
+0.042143/-0.004164; joint FPR expiry 0.002 / CME-strict 0.000, single-tail <=0.017): không real rule nào pass joint gate — khớp cả hai
engine NO [oc_placebo].
Quy tắc phương pháp mới: book ideas đi THẲNG tới engine 4-phase (không quyết trên vectorised screen nữa); dip screens giữ chân DD nhưng cộng
gate placebo p95 +0.273 (pooled dSum5y p95 trên 300 placebo dip-rules: full PROMISING legs + dSum>=+0.273 cắt FPR gộp 6.7% (20/300; shapes A 6%/
B 0%/C 14%, sum-half alone A 40%) xuống 0.7% pooled (<=2% mỗi shape; biến thể S1 full legs + max shape p95 0.3%, +2%-of-base +0.154 thì 2.0%);
base 5y sum=7.718 nên +0.273 ~3.5% base; S2 sum-half+tail vẫn lọt 15% shape-A nên phải giữ chân DD [oc_placebo_dip]).

## Bổ sung: mô hình book C1/C2 v427 — bug calibration lần chạy Kaggle đầu, audit mù PASS, fixed-run pending

Pre-register C2 (docstring `v427_c2_rank_calibrated.py`, của max 2 variants, direction đóng sau C1/C2): refresh walk-forward book leg BOT/MANUAL
(dip+agents+execution giữ cố định); C2 thay return regression bằng calibrated rank target (cùng features/windows/embargo/folds/blend như C1,
majors-only để isolate target effect); data 5 majors (spot 2017 prefix làm training rows); train earliest->anchor-7d, predict [anchor,
anchor+365d); features O1 y hệt C1 (base v142 xs + TV(17) + v236 whale flow-6) tính trên 5 majors; HGB depth-4 budget (max_depth 4, lr 0.03,
max_iter 400, min_samples_leaf 300, l2 1.0, seed 0); targets pairwise listwise rank 5 majors 7d vol-norm returns mỗi bar (rank r 0..4 -> r/4*2-1
trong [-1,1]; v112 sign / v287-v288 path labels KHÔNG tái dùng); ranker HGB + Platt (logistic) với isotonic fallback fit CHỈ trên train folds
(last 20% pre-cutoff rows = calibration fold, không test-year); calibrated rank -> long/short weights qua v94.weights_ls (clip +-0.5, ribbon
gating, vol_target_scale giữ); embargo 7d (t_exit và label-realisation < anchor-7d; calibration fold cũng kết thúc trước anchor-7d); folds
2021-2024 để SELECT, 2025 scored ONCE cho finalist đông lạnh; members annual A/B + quarterly Aq/Bq (cutoff quarter start-7d; A full, B TV-only);
blend books=0.8x rank-O1 + 0.2x D (D byte-identical deployed (members_v154 D + members_quarterly_D)/2; O1=0.5x(A+B)/2+0.5x(Aq+Bq)/2); eval harness
reset-metric 4-phase (v376 + r2_decompose5/reset_metric.py, 1/4 vốn mỗi clock 0/1/2/3h, gate costs + adverse funding; book-only VÀ full-pipeline
với R2 dip cố định + cost-stress/latency-15 rows không selection); chọn CHỈ 2021-2024 theo robust criterion v204+ (DD<=20, không năm lỗ,
ưu mean>=5%/th nếu có, trong đó worst-year cao nhất, ties -> mean cao hơn); fail dev DD/worst-year thì đóng hướng không chạm năm cuối; không
statistic nào từ 2025-09-24+ feed choice [v427_c2_rank_calibrated.py PROCESS NOTE/docstring].
PROCESS NOTE 2026-10-06 (disclosed): lần chạy Kaggle đầu v2 lộ bug calibration (Platt label rank>0 base rate ~0.4 -> calibrated score p*2-1<0
hầu như luôn luôn -> mọi member short/flat mọi năm; dev R 0.88%/th — KHÔNG phải model result); fix centre trên calibration-fold base rate
(pre-cutoff rows only), không đổi gì khác; run buggy giữ làm C2-bug (not a model result) [v427_c2_rank_calibrated.py PROCESS NOTE + fit_calibrator
BUGFIX]. Leakage audit mù v427_out: PASS — 16 files mỗi file 2190 bars index `t` UTC strictly trong [anchor, anchor+365d) (vd 2022
2022-09-24 00:00 -> 2023-09-23 20:00; 2023 kết 2024-09-22 20:00 vì leap-year; quarterly 546/546/546/552 union 2190, mỗi quarter non-empty),
training rows anchor 2022 A n=44338 cutoff 2022-09-17 00:00 last t 2022-09-09 16:00 last label end 2022-09-16 20:00<=cutoff (embargo 7d=42 bars
>= horizon 42 bars +1-bar margin), panel (88818,90) feats A/B 83/77 allowlist không label/rank/pred, feature causality 20-row truncated recompute
v92/flow/TV/order-flow diffs exact 0.0 cross chỉ fp 4.44e-16<=1e-9, reproduction 2022 A Spearman 1.0 max abs diff 3.997e-15 mean 2.34e-16
bit-identical, 2025 sealed (không file *2025*, max timestamp 2025-09-23 20:00<2025-09-24 seal, log không anchor 2025, 4 dev anchors 47/80/117/159s),
symbols majors-only [BNBUSDT,BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT] finite, code hashes khớp prereg (c2 9088d311.../common 8b5b4ff13...), timing/leakage
checks feature/label/fit-windows + no-most-recent-year-in-choice PASS, fill timing n/a (output audit, books là limit-entry weights)
[v427_audit COMPARISON]. Fixed-run result PENDING — chưa có số fixed-run trong báo cáo này, không dùng run buggy 0.88%/th để kết luận model
[v427_c2_rank_calibrated.py; v427_audit COMPARISON].

## Bổ sung: anatomy phase-3 2023 (OpenCode oc_clockanat, R2B1D17BFG2) — vì sao mix sống

Nguồn `v421/v421_runs.pkl` + rerun phase-3 vendored (live 2021-09-24+3h..2024-09-24+3h, reproduction max abs diff 0.0/2190 bars; units year-start
points phase equity=1.0 tại 2023-09-24; không simulate/score data >=2025-09-24) [oc_clockanat]. Peak (close) 2024-01-03 11:00 UTC 1.3076; trough
(marked) 2024-09-20 03:00 0.7424 -> DD 43.23%; trough close 2024-09-20 11:00 0.7427; year end 0.7443 (R -2.431%/tháng); peak->trough-close drop
-0.5649 trên 1566 bars (~8.5 tháng) [oc_clockanat]. Top-10 losing days (p3 | p0 p1 p2 | mix): 01-03 -0.2453 (-0.018/-0.267/-0.319 | -0.2123);
06-07 -0.1192 (-0.384/-0.117/+0.011 | -0.1523); 04-13 -0.0965 (+0.020/-0.212/-0.166 | -0.1137); 12-11 -0.0602 (all neg | -0.0418); 11-09 -0.0441
(all pos | +0.0219); 03-05 -0.0396 (all neg | -0.1615); 04-12 -0.0286; 08-05 -0.0246 (others +0.06..+0.17 | +0.0804); 11-21 -0.0239; 09-28 -0.0191;
top-10 sum p3 -0.7011 so với mix cùng ngày -0.6129; mix lỗ 7/10 ngày [oc_clockanat]. Split peak->trough: book -0.1317 (23%), dip -0.4332 (77%),
total -0.5649; dip exits trong window 85 stop / 326 take-profit / 267 timeout (215 losers); top dip losers toàn rung_sl: 01-03 BTC fills min
51/55/56 của bar T 11:00 depth 2.5/3.0/3.5/4.0 sigma stopped 12:09 (-717 bps, -0.029/-0.019/-0.019/-0.015), 06-07 XRP fills min 180 của bar T
15:00 depth 2.5/3.0/3.5 sigma stopped trong 5 phút (-979/-914/-849 bps), 04-13 BNB fill min 53 của bar T 19:00 stopped 17 phút sau
(-1103/-1028 bps), 04-12 XRP fill min 148 stopped giờ sau (-1304 bps) [oc_clockanat]. Đọc: slow bleed 8.5 tháng punctuated by stop cascades,
không phải một crash — chỉ ngày tệ nhất (-0.2453, 96% year net) giống single event, còn lại là cụm dip-stop lặp lại (01-03, 04-12/13, 06-07)
cộng 267 timeout exits grind trong downtrend; top-10 loss (-0.70) vượt year net (-0.26) nên +0.44 kiếm lại giữa các episode; boundary phase-3
cứ arm rungs vài phút trước cascade (fills min 51-61 stopped 10-20 phút sau; XRP min 180 stopped 5 phút sau) [oc_clockanat]. Mix 4-phase thoát
chủ yếu nhờ dilution (weight 1/4) cộng cushion dày hơn (mix year end 2.02 so với phase-3 0.74; clocks khác +4..+11%/th năm đó), không phải hedge:
6-7/10 ngày tệ nhất là common losses mọi clock, chỉ 3-4 ngày (11-09, 08-05, partly 04-12/11-21) offsets [oc_clockanat].

## Bổ sung: mỗi closed screen một dòng (số y nguyên báo cáo, nguồn trong ngoặc)

- oc_usdtprem (idea #71, tilt long x1.15/z>1 x0.85/z<-1, costs 0.0005, coverage z 100%): NOT PROMISING — total P&L không thấp hơn 4/5 nhưng maxDD
không tệ hơn chỉ 2/5 (2021 DD 0.092278→0.089537 đỗ/P&L 0.278895→0.278144 fail; 2022 0.235444→0.242656 đỗ cả hai; 2023-2025 P&L đỗ nhưng DD fail
+0.0001/+0.0037/+0.0028; full 5y total 1.970907→2.062149 +0.091, maxDD 0.104644→0.101883 cải full-path nhưng 3/5 per-year tệ hơn) — return edge,
no DD control [oc_usdtprem].
- oc_premexpo (exposure/placebo diagnostic cho 2 premium tilts, costs 0.0002 unified): USDT ALPHA (gain +0.049084, 4/5 năm, pct 99.4) / CB EXPOSURE
(gain +0.035170, 5/5 năm, pct 88.2<95) / COMBINED ALPHA (gain +0.042640, 4/5 năm, pct 97.2); verdict rule ALPHA chỉ nếu gain>0 >=4/5 VÀ pct>=95 —
nhưng ALPHA vẫn NO ở full engine [oc_premexpo; oc_usdt4p].
- oc_placebo (1000 expiry-like + 1000 CME-like, seed 20261006): FPR expiry-legs 3.7% (37 pass), CME-strict 0.2% (2 pass) / loose 2.4% (24 pass);
real expiry P&L pct 97.0 / DD 98.2% (genuine outlier nhưng fail unified leg-count vì tie 2023) / real CME pct 63.0/48.1 (typical null) — adopt legs +
joint placebo tails (joint FPR 0.2%/0.0%), cả hai real đều không promote, khớp engine NO [oc_placebo].
- oc_placebo_dip (300 placebo dip-rules, base 5y sum 7.718): pooled FPR 6.7% (20/300; A 6%/B 0%/C 14%; sum-half alone A 40%) — require full legs +
dSum>=pooled p95 +0.273 (~3.5% base) cắt xuống 0.7% pooled (<=2% mỗi shape) [oc_placebo_dip].
- oc_usdt4p: VERDICT NO (USDT 5.168 so với base 5.410, gap -0.242; 2024 -0.701, 2023 -0.421; full-path DD 17.00 so với 16.82 +0.18pp; rớt 3/4 chân
KEEP) [oc_usdt4p].
- oc_cmegap4p: VERDICT NO (CME 5.424 so với base 5.410 +0.014 nhưng maxDD 17.05 so với 16.91 +0.14pp / full 17.03 so với 16.82 +0.21pp; 2023 -0.416;
rớt chân DD + chân năm tệ) [oc_cmegap4p].
- oc_expiry4p: VERDICT NO (EXP 5.498 so với base 5.410 +0.088, maxDD 16.56 so với 16.91 -0.35pp / full 16.53 so với 16.82 -0.29pp, nhưng 2021 -0.341;
rớt đúng chân không-năm-tệ->0.3) [oc_expiry4p].
- oc_clockanat (diagnostic, không phải screen đóng): DD 43.23% phase-3 2023 là grind chậm đồng bộ 2023-04-17→06-15 + cascades (book -0.1317/dip
-0.4332; 85 stop/326 TP/267 timeout), mix sống nhờ dilution không phải hedge [oc_clockanat].
- oc_fillttl (fill-relative exits T240/T120 vs D0 next-bar-open, paired 22312 rungs, phase0=D0 5498 tick-identical): T240 sum>=D0 3/5 + DD<=+0.01 1/5
(chỉ 2024) + disp thấp hơn 1/5 (chỉ 2023) / T120 3/5 + 2/5 (2023,2024) + 2/5 (2021,2023) — cả hai NOT PROMISING, giữ time exit theo đồng hồ 4h;
win cao hơn mọi năm (D0 66-75% -> T120 68-77% -> T240 70-79%) nhưng sums thua 2021/2025 (-0.40/-0.25, -0.15/-0.04 mean4) và tails tệ hơn (T240 DD
+0.35/+0.16/+0.03/-0.07/+0.43) [oc_fillttl].
- oc_stoptf (idea #72, close15 S15 / every-1m S1 vs deployed close5 D0, paired 22312, phase0 D0 sums 2.388/0.183/3.810/2.579/0.712 tick-identical):
S15 sums 4/5 (trừ 2021) nhưng DD chỉ 2/5 (tệ 2021 +0.100, 2022 +0.027, 2024 +0.047; cascade 2021-12-04 -3.68 so với -2.87) / S1 DD 5/5 nhưng sums
chỉ 2/5 (2021,2022; bleed 2023/2024/2025) — cả hai NOT PROMISING, giữ close5 stop [oc_stoptf].
- oc_seasondepth (idea #70, seasonal rung depth sigma_eff=sigma_4h*sqrt(s), s walk-forward per-coin hour-of-week [anchor-365d,anchor) 5x5x42,
sqrt(s) 0.71-1.26, unpaired arms 43424 fills checksum 8ee7c1bdc9afed87): sum RULE>=BASE 1/5 (chỉ 2022 0.877 so với 0.833) và DD<=+0.01 1/5 (chỉ 2024
2.975/0.305 so với 3.197/0.355; renorm Sr cũng thua 4/5) — NOT PROMISING, đóng hướng [oc_seasondepth].
- oc_rearm (idea #67, re-arm cùng bid sau TP trong bar, tối đa 1 refill/rung/bar, majors x R2 depths, 4 phases; V1 deployment-scale G1=2.0/K~31.2
never-binds vs V0 literal G=2.0 binds median-fill-bar, candidates/exits/fees/scoring/decision V0-identical; base shift-0 fills 990/1045/1330/989/1144
sums 2.39/0.18/3.81/2.58/0.71 tick-identical oc_b1deeper): V1 sum cao hơn 3/5 (2023/2024/2025; base vs rule mean4 0.911→0.466/0.833→0.663/
2.100→2.171/3.197→3.548/0.677→0.716) VÀ DD trong 1pp 0/5 (tệ mọi năm +0.13..+0.21) VÀ re-armed win 69.0% (62-74% mỗi năm, 4745 fills; V0 64.9%) —
VERDICT NOT PROMISING (V0 1/5+1/5 cũng NO), giữ limit once-per-bar rung; re-armed fills short-gamma (thua 2021 -0.96x rule total, 2022 -0.26x;
worst day tệ hơn cả 5 năm) [oc_rearm].
- oc_liqhist (Binance public archive probe 2026-10-06, prefixes `data/futures/um/daily|monthly/liquidationSnapshot/<SYM>` 5 majors, 4 req/s):
USABLE for 2021-2026 research NO — UM daily/monthly listings IsTruncated=false 0 Contents/CommonPrefixes cả 5 symbols (10 XML saved), parent
prefixes cũng empty, control aggTrades 1000 keys/page IsTruncated=true nên method đúng; alt names forceOrders/liquidations cũng empty; download 0
bytes; coverage 2020-2026 zeros; COIN-M liquidationSnapshot tồn tại nhưng sai margin type và dừng sớm (BTCUSD_PERP 472 zips 2023-06-25..2024-10-14,
ETHUSD_PERP 474 zips); alternatives verified HTTP 200: UM metrics daily (OI/top-trader/taker ratios 5m từ 2020-09-01, proxy không phải order-level),
Futures DATA REST + Bybit v5 + OKX public (recent-only), own collectors từ 2026-10-04 (forward-only quá ngắn), /fapi/v1/forceOrders 401 unauthenticated
[oc_liqhist].

## Bổ sung docs_update5 (2026-10-06): triển khai khuyến nghị = G2 + carry f=0.25 một UTA

KHUYẾN NGHỊ HIỆN TẠI: BOT G2 (R2B1D17BF + `--dip-gross-cap 2.0`, v421: 5,41 %/tháng, worst 2,588, maxDD năm 16,91, full-path 16,82) + sleeve cash-and-carry
quý f=0,25 trên CÙNG MỘT Bybit UTA (cross, hedge, 5x) [oc_carrycombo; oc_utamargin; FINAL_REPORT_VI mục 1].
Sleeve độc lập cộng tuyệt đối dương mọi năm (33/33 cặp net dương allocated, min +0,18% allocated [oc_cashcarry]) nhưng tỷ suất gộp nhích nhẹ vì pha loãng
trên tài khoản tăng nhanh (2024 tài khoản x3,3 trong khi sleeve ăn ~5% cố định trên notional lúc vào) [oc_carrycombo].

Số base (hai quy ước đo, chênh do rebalance — ghi cả hai, nguồn trong ngoặc):
- Quy ước roll-only rebalance (thực tế vận hành, `oc_carrycombo`): G2 đơn 5,410 / worst 2,588 / maxDD 16,91 / full marked 16,82 (close 16,05);
G2+carry f=0,25: 5,413 / 2,647 / 16,78 / full 16,34 (close 15,60); f=0,50: 5,418 / 2,705 / 16,65 / full 15,86 (close 15,15) [oc_carrycombo].
Từng năm G2+carry f=0,25 (R %/tháng / DD %): 2021 2,647/10,79; 2022 3,283/16,78; 2023 6,168/15,72; 2024 10,559/8,08; 2025 4,593/12,57 [oc_carrycombo].
- Quy ước year-start rebalance (`oc_carryfric`, lift cao hơn nên KHÔNG dùng làm kỳ vọng): G2+carry f=0,25: 5,533 / 2,736 / 16,78 / 16,78;
f=0,50: 5,654 / 2,881 / 16,64 / 16,64 [oc_carryfric].
Caveat vốn (split-capital): overlay cần tới 2f cash EXTRA cho chân spot khi cả hai coin cùng mở (f=0,25 -> tới 1,5x funded); R trên tính trên base equity,
trên tổng vốn funded lift còn nhỏ hơn [oc_carrycombo].
Dưới ma sát (`oc_carryfric`, cùng quy ước year-start): G2 đơn S1..S5: 4,571 / 5,212 / 4,578 / 4,898 / 4,883; G2+carry f=0,25: 4,696 / 5,339 / 4,717 /
5,033 / 5,016; f=0,50: 4,820 / 5,463 / 4,853 / 5,166 / 5,147 — giữ >=5,0 ở base, S2, S4 f=0,25/0,50, S5 f=0,25/0,50; RỚT ở S1 (kể cả f=0,50 chỉ 4,820)
và S3 (f=0,50 chỉ 4,853); sleeve cộng +0,12–0,15pp (f=0,25) / +0,25–0,28pp (f=0,50) và bớt DD 0,1–0,3pp, không năm lỗ ở cả 36 combo [oc_carryfric].
Margin một UTA (`oc_utamargin`, 43.805 giờ, IM=(G2 gross+carry short)/5, MM tiered live Bybit 2026-10-06, balance=equity−5% spot): f=0,25: free min 22,49%,
IM/bal max 77,51%, 0 giờ blocked, 0 MM breach, MM/bal max 1,95%, spot cost max 95,8% Eq, gap −10% ở giờ tệ nhất −28,85% không liq — ADDITIVE OK;
f=0,50: free min 1,85%, IM/bal max 98,15%, 1 giờ blocked (2025-09-25 18:00), spot cost max 179,9% (thiếu USDT mua spot, phải vay) — KHÔNG clear,
trên 0,25 chỉ SPLIT CAPITAL [oc_utamargin].
Khả dụng Bybit (`oc_carrycombo` §3 + `bybitq`): linear quarterlies Trading BTCUSDT-25DEC26 / BTCUSDT-26MAR27 / BTCUSDT-25JUN27 (cả ETH), weeklies
09/16/23/30OCT26 + 27NOV26, deliveryFeeRate 0, fundingInterval 0, maxLeverage 50, unifiedMarginTrade true; inverse quarterlies Trading BTCUSDZ26 /
BTCUSDH27 / ETHUSDZ26 / ETHUSDH27; phí VIP0 futures taker 0,055%/maker 0,02%, spot 0,1% đúng giả định gate/carry; spot BTC/ETH làm collateral 95%
(tốt hơn giả định 5%/10%) [oc_carrycombo]. Chuỗi quarterly phủ đủ 5 năm chỉ có inverse coin-margined (H/M/U/Z; USDT-dated chỉ từ 2025-02-18, USDC
weeklies 2023-03..2025-03) [bybitq]. Yield Bybit-inverse ≈ Binance proxy: +0,4973/23 trades so với +0,5234/25 trades (−5%), f=0,25 +12,43% sau 5 năm =
+0,207%/tháng số học (+0,202% hình học) so với Binance +13,09% = +0,218 (+0,213); f=0,50 +24,86% (+0,414/+0,396) so với +26,17% (+0,436/+0,416);
worst MtM allocated Bybit −0,42/−0,74/−2,49/−0,52/−1,36% so với Binance −1,01/−0,71/−2,65/−0,39/−2,17% (account f=0,25 tệ nhất −0,62% cả hai venue);
USDT-linear không tái lập backtest 2021–2024 (chưa tồn tại) [bybitq].
Carry làm tay được (~4 quyết định roll/năm, ~5 cặp/năm ≈ 15 vé tay/năm; mỗi cặp vào ~3 vé: mua spot + short futures, bán spot lúc đáo hạn, futures tự
tất toán) [oc_carrycombo; oc_manualcarry]. Bước chủ tài khoản làm (quy tắc đóng băng `oc_cashcarry` PLAN + docstring `scripts/carry_paper.py`):
(1) mỗi coin BTC/ETH xếp quarterly tới hạn tăng dần, front = đáo hạn sớm nhất còn sống; (2) khi front còn <=7 ngày HOẶC lần đầu có hàng thì xét hợp đồng
KẾ TIẾP (quarterly chu kỳ Mar/Jun/Sep/Dec thứ Sáu cuối tháng; live dùng inverse Z26/H27 hoặc linear DEC26/MAR27/JUN27); (3) tính basis năm hóa
ln(F/S)*365/DTE, CHỈ VÀO nếu >=4%/năm (ETH skip vd 3,7% [PROSPECTIVE_20261006]); (4) sizing mỗi chân = f x vốn lúc vào (khuyến nghị f=0,25), long spot +
short quarterly notional bằng nhau; (5) giữ tới delivery, phí spot taker 0,1%/bên + futures vào 0,055% + delivery 0,02% (drag 0,275% allocated), futures
delivery KHÔNG funding; (6) sổ paper: `.venv\\Scripts\\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry` (public REST only,
không key, không đặt lệnh; state `artifacts/bot/paper_carry/state.json` + `actions.jsonl`, sha256 quy tắc in đầu run) [carry_paper.py docstring].
Paper carry thực 2026-10-06 06:05Z f=0,5: BTC BTCUSDT-25DEC26 entered (basis +5,42%/năm), ETH skip, MtM alloc −0,15% (−3,68 USDT), giữ tới Dec ~80 ngày,
quá sớm chưa kết luận [PROSPECTIVE_20261006].

## Bổ sung docs_update5: stretch DD<15, MANUAL+carry, plateau, 8-phase, restart, screens đóng

- Stretch DD<15 (`oc_carryd13` + `oc_carryfric`): D13BF đơn (v424 R2B1D13BF) 4,971 / worst 2,485 / maxDD 14,98 / full 14,86; +carry f=0,25: 5,104 /
worst 2,634 / maxDD 14,85 / full 14,85; f=0,50: 5,234 / 2,781 / 14,71 / 14,71 — ĐẠT cả 4 bar (≥5,0, DD năm <15, full <15, không năm lỗ) TRÊN GIẤY base
[oc_carryd13]. TRUNG THỰC dưới ma sát: CHỈ giữ cả hai bar ở base và S2 f=0,50 (5,062/14,80); S2 f=0,25 DD đạt (14,94) nhưng return rớt (4,929);
S1/S3/S4/S5 kể cả f=0,50 đều rớt (tốt nhất S4 f=0,50 4,845/15,82; DD tệ nhất S5 f=0,50 15,81; return tệ nhất S3 f=0,50 4,453) — DD<15 không bền dưới ma
sát thực tế, kỳ vọng thận trọng ~4,2–4,8%/tháng DD ~15–16 [oc_carryfric].
- MANUAL+carry vẫn <5 (`oc_manualcarry` yearly-level + cross-check equity-level `oc_carrycombo`): M5_human đơn 3,728 / worst 0,847 / maxDD 17,94 /
full 17,79 win book 64,82%; f=0,25: 3,862 / 0,936 (equity-level 3,746); f=0,50: 3,993 / 1,024 (equity 3,765) — combo tốt nhất vẫn thiếu ~1,0pp
(yearly) / ~1,2pp (equity); G15 f=0,25 3,157 / f=0,50 3,304 (DD 14,93); G10 2,774/2,927 (DD 13,54); humanBF 3,754/3,888 nhưng DD 21,55 FAIL; top2
3,210/3,350 (DD 19,53) — verdict NO, không hàng MANUAL+carry nào tới floor 5% [oc_manualcarry].
- G2 plateau (`oc_plateau2`, mỗi biến thể đổi MỘT tham số dip, harness y hệt v421): ref 5,410/2,588/16,91/16,82 win 0,6533; TP08 5,183/2,698/15,84/15,82
win 0,6796; TP12 5,482/2,546/18,19/18,08 win 0,6326; SL35 5,324/2,617/17,15/17,06; SL45 5,394/2,610/16,80/16,79; G175 5,503/2,527/16,74/16,68;
G225 5,252/2,598/16,87/16,76 — ON PLATEAU cả ba chiều (5y trong 0,3%/tháng, fullDD trong 1,5pp cả hai phía), không năm lỗ hàng nào, giữ nguyên
R2B1D17BFG2 [oc_plateau2].
- 8-phase NO (`oc_phase8`, 8 đồng hồ lệch 30 phút mỗi cái 1/8 vốn, cùng config G2): 8-phase mix 4,960 / worst 2,709 / maxDD 17,98 / full 17,32 win 0,656
so với 4-phase mix 5,410/2,588/16,91/16,82 — pha loãng return 0,45pp mà fullDD TĂNG 0,5pp; đồng hồ nửa giờ đơn lẻ wild hơn (fullDD 21–37%), crash cùng
năm 2022–2023 nên averaging không xóa phase luck; 10k USDT chia 8 (1250/clock) thì 47–60% lệnh BTC dưới minimum 100 USDT — NOT placeable —
verdict NO, giữ mix 4 pha [oc_phase8].
- Restart sau reboot: `scripts/restart_all.sh` (header) — idempotent, chỉ đọc process không kill, `--dry-run` xem plan, `--only bots|backend|carry`;
thứ tự backend local 127.0.0.1:8724 (KHÔNG tunnel) chờ /health + plan tươi <1h15m; loop.sh RETIRED từ 2026-09-30 (backend tự chạy advisor shadow);
5 runner paper chỉ dựng khi runner.lock free (`paper` R2-4P không tag; d17bf/d13bf/d17bfg2/g2k20 đúng `--tag`, `--interval 25`, d17bfg2/g2k20 kèm
`--dip-gross-cap 2.0 --adopt-fresh`), state.json backup + validate JSON; vòng carry `carry_paper.py --once --equity 5000 --f 0.5 --tag carry` mỗi 3600s;
cuối in bot_health 5 runner + daily_status; KHÔNG set BOT_ALLOW_LIVE, KHÔNG start testnet/live [restart_all.sh header].
- Screens đóng đợt này mỗi hướng một dòng (số y nguyên): oc_expirydip (idea #76, thêm 1 rung 5,0-sigma ở bar expiry Deribit, 24 fills/5 năm/4 phases/5 coin,
21/24 wins nhưng mẫu tí hon): sum 5/5 + DD 5/5 pass trivially nhưng dSum5y +0,0164 chỉ 6% gate placebo p95 +0,273 — NOT PROMISING, đóng không
full-engine [oc_expirydip]. oc_usdtdip (tilt size x1,2 khi z>1 / x0,8 khi z<−1 theo USDT premium, 22312 fills): sum 3/5 + DD 4/5 + dSum +0,047 (17% gate) +
control 3/5 (2021 −0,133 sum/+0,074 DD, 2024 edge thuần exposure) — NOT PROMISING, edge book-long USDT không chuyển sang dip [oc_usdtdip].

## Bổ sung docs_update6 (2026-10-06)

- Kỳ vọng trung thực sau hiệu chỉnh may mắn đồng hồ (`oc_clockluck`): bốn đồng hồ giờ triển khai MAY ở sleeve dip — replica dip 24 START offset
(S=sum(w*y), B1 sizes, R2 depths, D0 exits): min 4,55 / max 9,67 (offset 0) / mean 7,12 / median 7,13 / std 1,54; bốn offset triển khai
0=9,67 (percentile 100%, max) / 60=7,54 (58%) / 120=8,76 (88%) / 180=4,90 (8%); mean triển khai 7,72 so với mean 24 offset 7,12 (luck gap −0,59,
−8% deployed); may mắn tập trung 2023 (offset 0 tốt nhất 24, gap −0,42) + 2025 (gap −0,15), 2021/2022/2024 trung tính (gap +0,00/−0,03/+0,01)
[oc_clockluck]. Kỳ vọng đồng hồ ngẫu nhiên (approx: book giữ mix4 + dip(mix4) x ratio mean_all/mean_deployed theo năm; ratios 2021 1,002 / 2022 0,958 /
2023 0,798 / 2024 1,004 / 2025 0,779 / 5y 0,923; mix4 yearly R 2,588/3,282/6,093/10,677/4,648 = 5,42 ≈ deployed 5,41; adjusted 2,593/3,233/5,453/10,691/4,401):
5,24 %/tháng thay vì 5,41 — giữ SỐ CŨ 5,41 kèm giải thích ~0,17pp là luck dip-clock; kỳ vọng vẫn trên 5% theo approx này nhưng biên mỏng và method chỉ là
proxy (equal-bar replica, không gross cap/governor/compounding, book giả định clock-neutral) [oc_clockluck]. Đồng thời đồng hồ nửa giờ KÉM CẤU TRÚC
(book VÀ dip cùng thua 2022–2023, dip-2023 0,090 so với 0,706) — verdict BOTH [oc_clockluck].
- Carry (`oc_utamargin2`, `oc_carryfar` + Leader decision): chân short quarterly để 10x (đã hedge bằng spot) — margin trống thấp nhất 22,5% → 32,7%
ở f=0,25 (IM/bal max 77,51% → 67,33%, 0 blocked, 0 MM breach, gap −10% −28,85% không liq); bắt buộc Cross margin (isolated short cháy ngay khi squeeze
+30% ở mọi mức 5x/10x/20x) [oc_utamargin2]. Trần f=0,25 cho một UTA cộng gộp (5x, không đổi; spot cost max 95,8% Eq, headroom +4,2%, không vay)
[oc_utamargin2; oc_utamargin]. f=0,375 @10x là ngoại lệ có bound DUY NHẤT nếu chấp nhận auto-borrow USDT mua spot (27,47% free / 21,42% dưới hc10 /
5,67% dưới hc20, 0 blocked; 20x cũng qua về cơ học nhưng mỏng hơn nên ưu tiên 10x; spot cost peak 139% Eq, headroom −39%) [oc_utamargin2].
f=0,50 KHÔNG clear ở mọi đòn bẩy (ngay 20x vẫn 1 giờ blocked dưới hc20; 5x: 1,85% free / 1 blocked base, hc10 −9,41%/3 blocked, hc20 −41,98%/132 blocked)
[oc_utamargin2]. Tenor FAR KHÔNG adopt: FAR thắng 4/5 năm cả hai venue (Binance pooled 1,07064 so với base 0,523436; Bybit-inverse 0,931737 so với
0,497293; add f=0,25 +0,43%/tháng hình học Binance / +0,37% live so với base +0,21/+0,20) NHƯNG gain là exposure chứ không phải rate tốt hơn
(entry basis gần bằng nhau, vd 2023 12,9% so với 13,0%/năm; FAR giữ ~6 tháng nên 2 cặp/coin overlap, spot cost 1,04–1,12x Eq phải vay — cùng constraint
đã loại base f=0,50) — Leader decision 2026-10-06: giữ rule base (next quarterly, f=0,25); hướng carry ĐÓNG (2/2 variants đã dùng) [oc_carryfar].
- Vốn (`oc_capscale`, G2 v421, Bybit minima 5 USDT + qty steps BTC 0,001/ETH 0,01/SOL 0,1/BNB 0,01/XRP 0,1): R5/DD y hệt mọi size (5,41/2,588/16,91/16,82 —
UPPER bound vì engine chưa enforce qty step in-path) [oc_capscale]. Placeability (pooled 4 phases; 9051 book sizings, 21513 rungs): >=5.000 USDT đặt được
gần như mọi lệnh (book 0,9990 count / 0,9995 weight; dip 0,9780 count / 0,9985 net / 0,9967 gross); 10.000 USDT book 100%, dip gross 99,92%; 2.000 USDT chỉ
~93–96% count (book 0,9585/0,9704; dip 0,9269/0,9950/0,9804; BTC book 0,844/dip 0,799, ETH 0,954/0,895 — bottleneck BTC rồi ETH) [oc_capscale].
Khuyến nghị: TỐI THIỂU 5.000 USDT (1250/sub-book), THOẢI MÁI 10.000 USDT; dưới 5.000 (đặc biệt 2.000) KHÔNG chạy cấu hình này như mô phỏng
(~16% book BTC và ~20% rung dip BTC không đạt lot Bybit, chủ yếu do qty step) [oc_capscale].
- Paper runner `paper_d17bfg2c` (G2 + carry 0,25) started 2026-10-06 07:19 UTC (first action `bear_state` 07:19:09Z; state `carry.positions.BTC`
f=0,25 BTCUSDT-25DEC26 ann_basis ~5,31%, equity_entry 5000; equity paper 5000, flags G2 `--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0`
+ `--carry-f 0.25`): thu bằng chứng triển vọng cho combo triển khai một UTA; caveat 2026-10-06: carry orders trong paper bị generic diff hủy (fix đang làm,
xem `docs/BOT_EXECUTION.md` bot_carry) — tới khi fix xong thì số paper carry là tiến cứu có nhiễu thực thi, không phải engine-faithful [artifacts/bot/paper_d17bfg2c].
- Đóng hôm nay mỗi hướng một dòng (số y nguyên báo cáo): oc_linvinv — 0 lệnh vào (12 skip <3pp, max diff 2,55pp BTC Jun25 lin 7,50 so với inv 4,94;
16 cặp cùng expiry, net 0,0000) — NOT USEFUL, dislocation cần chưa từng in trong history [oc_linvinv]. oc_marktrig — sum>=BASE 4/5 (trừ 2022 −0,227)
NHƯNG maxDD chỉ 2/5 + worst-day 2/5 (5y delta +0,057 trên base 7,72; mark âm premium nên fire sớm hơn trong crash, cascade 2024-01-03 −0,405) —
NOT PROMISING, giữ last-price triggers [oc_marktrig]. oc_discsniper — S_bar>0 0/5 năm (5y −0,5291, win 42,5%, mean −13,7 bps/trade; placebo pct 13,3
dưới cả random-timing mean −0,452; corr dip +0,045) — NOT PROMISING [oc_discsniper]. oc_manual2coin — M5_human 3,73/17,9/17,8 so với 2coin x1,0
3,24/15,8/17,1 (dip win .701→.740 nhưng rung 6417→2495, P&L BTC/ETH/BNB bị loại không bù được) và 2coin x2,5 3,39/20,2/24,3 FAIL DD (gom 2,5x vào 2 coin
gom đuôi crash thay vì đa dạng) — cả ba NO vs MANUAL floor; load 51/d→21/d được nhưng không ra return; còn 1 shot MANUAL cuối phải thêm entry edge
[oc_manual2coin]. oc_phase8 — 8-phase mix 4,960/worst 2,709/maxDD 17,98/full 17,32 so với 4-phase 5,410/2,588/16,91/16,82 (pha loãng −0,45pp return mà
fullDD +0,5pp; half-hour đơn lẻ fullDD 21–37% crash cùng năm 2022–2023; 1250/clock thì 47–60% lệnh BTC dưới minimum) — NO, giữ mix 4 pha [oc_phase8].
