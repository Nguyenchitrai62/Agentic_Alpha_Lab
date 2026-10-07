# Tóm tắt cho chủ tài khoản — 2026-10-08 (VI)

Phạm vi: BOT = book + thang dip G2; mọi số walk-forward 5 năm, reset 1/4 vốn mỗi anchor, chi phí gate Bybit (maker 0.02%/taker 0.055%, long trả 0.01%/8h). Nguồn số: docs/CLOSED_DIRECTIONS.md §11+, docs/FRONTIER_MAP_VI.md, REPORT.md/COMPARISON.md được dẫn ở đó. Không có số mới.

## 1. Đang chạy: giữ nguyên G2 + carry f=0.25 — kỳ vọng thật theo giá Bybit dưới 5%/tháng
- G2 (R2B1D17BF + trần dip 2.0x) giá Binance: 5y 5.410 / full-path DD 16.82; dev4 5.601 / W 2.588 / DD 16.91; năm gần nhất 4.648/12.90 [oc_bybitgap §0; oc_amihudrobust §0; FRONTIER_MAP_VI].
- Cùng G2 trên giá Bybit (S5): 5y 4.883 / full DD 18.09; dev4 4.994 / W 2.129 / DD 18.11; năm gần nhất 4.443/12.37 [oc_bybitgap §0; oc_amihudrobust §1].
- Gap G2−S5: dev4 0.607 (đỉnh 2023 1.113, các năm khác 0.300–0.547), 5y 0.527, năm gần nhất 0.205; DD rộng thêm +1.27pp (16.82→18.09) [oc_bybitgap §0].
- Nói thẳng: mốc 5%/tháng hiện chỉ đạt trên giá Binance; live Bybit kỳ vọng ~4.88%/tháng 5y là RỚT mốc 5, DD ~18 vẫn dưới 20. Carry +0.224 (G2+carry 5.634/16.75/16.66, năm gần nhất 4.698 [FRONTIER_MAP_VI; oc_carrycompound]) cũng đo trên giá Binance nên thực tế Bybit thấp hơn. Book khớp gần hệt nhau (fill Bybit +2/+14, giá median <1bp); gap nằm ở thang dip (ít fill −25/−57, thiếu −34/−59 TP, TP-rate −0.4/−0.6pp) + phần dư sizing, phân tán mọi coin, không có fix venue nào [oc_bybitgap §1–§6] — dự trù ~−0.5 điểm %/tháng cho live Bybit.

## 2. Điều đã xác nhận (giữ, không đổi luật)
- Book sống bằng timing chứ không phải beta: timing dương cả 5 năm (2021 +3.25, 2022 +1.82 %/tháng gross), placebo 96.8–100%, beta thị trường chỉ 0.05–0.14; book-only net 2.531 %/tháng (2021 chỉ 0.59), DD 18.96 > G2 16.82 (thang dip đa dạng hóa DD) [oc_bookattrib].
- Skill book ở chân trời ngắn 4h–3d (h=1..18 bar): pooled IC +0.02..+0.04, 4/4 năm dev dương ở cả 6 member, năm gần nhất +0.036 (h=1); nhãn 7 ngày h=42 đảo dấu 2022 — presample cũ đo sai chân trời nên IC ~0 [oc_bookichorizon] (ĐANG KIỂM LẠI 2026-10-08: thước đo IC có thể rò rỉ biến động của chính nến t — oc_horizonfix; chưa dùng kết luận này).
- Mọi lớp phòng thủ đều đáng tiền: bỏ B1 vỡ DD (maxDD 23.65/full 20.20), close5 hơn touch (+0.38 lợi nhuận/−1.7 DD), bỏ cap thì gap −10% lỗ gấp đôi (32.9→60.9%), bỏ governor vỡ 20% (20.04/19.60); vol-target là núm return/DD (bỏ thì +0.86 nhưng +1.6 DD); bear-filter x0.5 ≈ 0 [oc_ablation].
- Model không decay: tươi−cũ IC +0.013 (A)/+0.002 (D), nhiễu ~0.04; retrain hàng năm là đủ [oc_staleness].
- Feed dư địa tốt: bỏ whale-flow hay Coinbase-premium chỉ lệch dev4 +0.01/+0.02pp, DD +0.5 (16.82→17.32/17.41); outage flow 3 ngày chi phí ≈ 0 (±25 bps/episode, đổi dấu) — feed stale vài ngày cứ trade tiếp [oc_memberdrop].
- Thang dip sống được ở 2017–2020 (spot, chưa từng dùng chọn luật): 2018 2.50 %/tháng DD 8.4; 2019 0.48/DD 11.3; Y2017 10.71/5.04; Y2020p 0.27/17.52 (pha s1 COVID DD 24.5 — cấm chạy pha đơn); B1 cắt nửa DD cả 4 kỳ, KD13<G2<KD20 đơn điệu cả return lẫn DD, cap không kích hoạt, TP1.5 lãi hơn nhưng DD cao hơn, touch chỉ thắng close5 ở nhịp COVID [oc_presample; oc_presample2].

## 3. Lead mới duy nhất: Kronos K2 — theo dõi, chưa triển khai
- K2 là gì: nghiêng thang dip bằng Kronos-small (S=64, risk=−low1, hướng +1 mọi anchor): quintile ngoài thuận ×1.25 / nghịch ×0.75 [oc_kronoshidden].
- Binance: dev4 5.772/W 2.469/DD 16.20/full 16.09 vs G2 5.601/2.588/16.91/16.82 (+0.171); năm sạch 4.801/12.10 vs 4.648/12.90 (+0.153); 5y 5.577 vs 5.410 (+0.167) [oc_kronoshidden; audit_k2 PASS-WITH-NOTES khớp từng chữ số].
- Bybit (S1–S5): K2 hơn G2 ở cả 6 ma sát — dev4 +0.08..+0.27, năm sạch +0.10..+0.20, 5y +0.09..+0.26; S5 dev4 5.077 vs 4.994 (+0.083), 5y 4.972 vs 4.883 (+0.089), full DD 17.41 vs 18.09 (thấp hơn mọi hàng) [oc_k2bybit].
- Placebo timing ủng hộ K2: timing pct 97.2, block pct 98.7 (năm 2021 Kronos không có skill) [oc_k2placebo].
- Vì sao chưa triển khai: năm tệ nhất dev4 K2 2.469 < G2 2.588 nên tiêu chí robust vẫn chọn G2; năm sạch 4.801 < 5.0 vẫn rớt gate; edge dev là cận trên (Kronos đã thấy dữ liệu dev). Runner paper paper_d17bfg2k2 (k2-tilt + scripts/kronos_shadow.py log hourly) đang thu bằng chứng prospective — quyết định sau log [oc_kronoshidden; oc_k2bybit; BOT_K2FLAG_20261007].

## 4. Bug đã sửa + vận hành + chân trời bằng chứng
- Exit-cancel (cb14cb7): chưa fix 3 piece BARE vĩnh viễn; có fix xong trong ≤2 cycle, 0 piece hở, 10 test pass [BOT_EXITSOAK_20261007].
- Dust: mẩu 0.0999… làm S/T tròn về 0 (dust_close qty 0 bị reject 110094 mỗi cycle ×444); fix qty = max(round_step, min_qty) = 0.1, soak 5.5h 0 dust (trước 4), 4 test pass [BOT_DUSTFIX_20261007].
- Carry paper (63d65bd): dated short không được mark nên equity ẩn lãi; sau fix d17bfg2c ~5,039 vs twin ~5,030 — lỗi kế toán, không phải chiến lược [CARRYGAP_20261007; CLOSED_DIRECTIONS §11].
- Keepalive: tác vụ AlphaLabRunnersKeepAlive + watchdog backend, ExecutionTimeLimit = 0; OWNER đăng ký, agent không tự đăng ký [KEEPALIVE_20261007].
- Chân trời bằng chứng: 8 tuần QUÁ YẾU (zero-edge vẫn PASS 38.3%, lỗ 1%/tháng vẫn 32.0%); 12 tuần 30.8%/25.0%; khuyến nghị 26 tuần (13.7%/8.1%); 52 tuần 2.5%/1.0% [oc_paperpower].

## 5. Đã đóng trong 2 ngày (mỗi dòng một họ)
- Options/VRP: straddle V2 dev4 3.441/worst −0.165/DD 25.82, overlay f0.25 5y 6.408/DD 16.10; robust k0.97 overlay 6.566/4.365/16.10, traded IV/DVOL mean 0.868 (thổi phồng ~11%); consistent R087 overlay 5.740/3.578/17.22 (+0.139) nhưng R080 −0.352, winner vẫn R100; strangle Z2 0.632/DD 14.01, G2+Z2 5y 5.601/DD 16.50; VRP-gate R087 5.740/3.578/17.22; VRP strike thật dev4 −0.99, 3 năm lỗ, DD 35.9, overlay −0.19pp — cả họ CLOSED, KHÔNG TRIỂN KHAI (headline +1pp là bias giá DVOL), chỉ còn ledger paper straddle [oc_vrpstraddle; oc_vrprobust; oc_vrpconsistent; oc_vrpstrangle; oc_vrpgate; oc_vrpstrike; audit_vrpstraddle PASS-WITH-NOTES].
- GEX: level đúng dấu 2/4 năm, vol corr sai dấu — ĐÓNG (level + change) [oc_gex; oc_gexchange].
- IV term structure: dip tệ khi TS cao 3/4 năm nhưng 2022 đảo; book |IC|≤0.11 — ĐÓNG [oc_ivterm].
- Option flow: pooled |IC|≤0.009, 0/3 ứng viên — ĐÓNG [oc_optflow].
- HL funding: 2023/24 +0.40/+0.28 kèm thêm DD, năm chấm một lần −0.07, IC ~0 — ĐÓNG [oc_hlspread].
- ETF flow: T1/T2 2024 −0.049/−0.178, 5y 5.375/5.313 < 5.410 — ĐÓNG [oc_etfflow].
- Stablecoin: G1 5.537 < G2 5.601 < CTRL 5.699; dip D2 dSum +0.450 nhưng DD đạt 3/5 — ĐÓNG [oc_stablegate].
- USDT depeg: overlay +0.001pp — ĐÓNG [oc_usdtdepeg].
- Literature gates: FHL-momentum M1 dev4 +0.17 nhưng năm gần nhất 3.89 vs 4.65 — ĐÓNG; calendar V1 năm gần nhất 4.304 vs 4.648 — ĐÓNG [oc_lit_fhlh; oc_lit_calendar].
- Amihud: A1 dev4 5.844/W 2.798/DD 16.81 vs 5.601/2.588/16.91 (+0.18 vs control, 4/4 năm, recent 4.750 vs 4.648) nhưng S5 Bybit gap −0.005 và DD 21.32 — KHÔNG TRIỂN KHAI; AB1_S5 5.039 vs 4.994 (+0.045) nhưng DD 22.48 — ĐÓNG [oc_lit_xs; oc_amihudrobust; oc_amihudbybit].
- MVRV: M1 dev4 6.192/DD 16.26 nhưng tách riêng cổng MVRV làm book tệ hơn (2.461 < 2.531) — lợi là tương tác governor (tránh 1 lần tắt pha 3 đầu 2024), năm gần nhất không kích hoạt — KHÔNG ADOPT [oc_lit_position; oc_mvrvmech; oc_mvrvrobust].
- Governor: GV3 6.107/W 2.830/DD 17.89, recent 4.824 (+0.18), 5y 5.849/full 17.50 = cùng điểm frontier với G2K20 — núm rủi ro, không phải frontier mới — ĐÓNG [oc_governor].
- Alt dip: ALT8 dip sum +25% 5/5 năm nhưng DD tệ hơn 5/5, corr 0.57 — ĐÓNG [oc_altdipb1].
- Native clock: TIMING mỗi pha ngang nhau (±0.2pp), không đáng rebuild — ĐÓNG [oc_nativeclock].
- MANUAL: split-TP H2 3.508/full 17.24 vs M5 3.728 (thiếu 1.49pp tới sàn 5); Kronos MANUAL 3.44/3.40 vs 3.73; book-vol Kronos 5y 5.308/DD 18.67 vs 5.410/16.82 — ĐÓNG [oc_manualsplit; oc_kronosmanual; oc_kronosbookvol].

## 6. Việc chủ tài khoản làm theo thứ tự
1. Giữ nguyên G2 + carry f=0.25 một UTA; kỳ vọng live Bybit ~4.88 (dưới 5) — không tăng vốn vì số Binance.
2. Nuôi mọi paper runner (gồm paper_d17bfg2k2 cho K2) đủ 26 tuần trước mọi quyết định deploy/K2/A1/M1.
3. OWNER đăng ký keepalive + watchdog backend; giữ paper sạch, loại cửa sổ lỗi exit-cancel/carry-mark đã ghi.
4. Không đưa VRP/Amihud/MVRV/governor/alt-dip vào live khi chưa có prospective ngoài mẫu.
