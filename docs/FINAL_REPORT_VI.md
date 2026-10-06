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
may mắn của seed - một lý do nữa để coi bằng chứng paper/tiến cứu là kiểm định chính, và kỳ vọng thận trọng (~4,5-5 %/tháng thay vì 5,4).

## Bổ sung: hồ sơ thận trọng D13BF dưới ma sát (OpenCode oc_d13robust, oc_kpi_d13)

D13BF (dip x1,3 + bear-book): gốc 4,97 %/tháng, DD năm 14,98 / toàn đường 14,86. Dưới mọi ma sát DD vượt 15 (chi phí x2: 4,27 / 15,51;
trễ 15': 4,79 / 15,08; trễ 30': 4,16 / 15,62; trượt stop: 4,56 / 15,90). => DD < 15 chỉ đạt trên giấy, không bền dưới ma sát thực tế;
hồ sơ thận trọng nên kỳ vọng ~4,2-4,8 %/tháng với DD ~15-16. Cấu hình triển khai chính vẫn là G2 (DD 16,9; ma sát giữ DD <= 18,1).
