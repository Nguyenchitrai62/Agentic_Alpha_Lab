# oc_eventstress REPORT — crash-week anatomy of G2 + carry f=0.25 (2026-10-06)

Reporting task, research only, MEDIUM. No engine reruns: G2 = stored
`v421/v421_runs.pkl` R2B1D17BFG2 (v422 bit-identical, asserted in-script);
hourly close/marked equity via exact `v388.hourly()` (eq_min = stored
1m-marked intrabar low; G2-only full-path DD reproduces v421 16.82 to the
digit). P&L = account-realistic compounding of `oc_carrycompound`
(A(t)=A(t-1)*(1+r_bot)+dU, carry notionals f x live equity, f=0.25).
Margin = `oc_carrymargin` method verbatim (IM perp G/5 + carry short/10,
balance = Eq − haircut x spot at 5%/10%, conservative short/5x row; tiers
frozen from `oc_utamargin`, no network). Dip/book gross = hourly rebuild
from stored `oc_kpi_g2` events with the exact `oc_margin` q-units math.
Market lows cross-checked against local 1m klines
(`majors_intraday_20260924` + `btc_intraday_20260924`, coverage OK all
windows). Window = anchor−24h .. anchor+7d; recovery = first breach of
pre-event equity inside the window, then first return (0.0 = never went
under; null = never). Full numbers in results.json. All five years are
research data; needs prospective validation like everything else.

## Bảng chủ sở hữu (10 hàng = 6 đợt riêng biệt; DROP1≈AUG24, DROP2≈FTX+1d, DROP3≈3AC, DROP4≈LUNA+1d)

| Sự kiện (anchor UTC) | P&L G2+carry −1d..+7d (G2 riêng) | DD close / DD đánh dấu 1m | Đáy (giờ UTC) | Dip gross max (giờ) | Margin UTA max (Eq / Bal5% / stress10% / cons; giờ block; MM breach) | Stop (book+rung) / TP / timeout; liq? | Hồi phục về vốn trước event |
|---|---|---|---|---|---|---|---|
| LUNA 2022-05-11 | −6.05% (−6.03%) | 9.66 / 10.38% | 05-12 04:00 | 0.45x (05-12 04:00) | 0.140 / 0.143 / 0.145 / 0.173; 0 giờ; không | 132 / 392 / 197; không | 35.8 ngày |
| 3AC 2022-06-13 | +3.54% (+3.64%) | 4.01 / 4.91% | 06-13 09:00 | 0.52x (06-14 02:00) | 0.116 / 0.117 / 0.118 / 0.134; 0 giờ; không | 0 / 194 / 202; không | 0.5 ngày |
| FTX 2022-11-08 | −2.47% (−2.47%) | 8.41 / 9.78% | 11-10 08:00 | 0.77x (lúc mở cửa sổ) | 0.194 / 0.194 / 0.194 / 0.194; 0 giờ; không | 86 / 515 / 170; không | 13.8 ngày |
| USDC 2023-03-11 | −0.14% (−0.14%) | 4.47 / 5.53% | 03-14 19:00 | 0.29x (03-14 20:00) | 0.088 / 0.088 / 0.088 / 0.088; 0 giờ; không | 19 / 65 / 39; không | 0.3 ngày |
| AUG24 2024-08-05 | +5.06% (+5.02%) | 6.43 / 9.56% | 08-05 07:00 | 0.54x (08-05 01:00) | 0.198 / 0.202 / 0.206 / 0.241; 0 giờ; không | 70 / 238 / 123; không | 0.3 ngày |
| DROP1 basket −21.1% 2024-08-05 12:00 | +4.34% (+4.30%) | 6.43 / 9.56% | 08-05 07:00 | 0.54x | 0.198 / 0.202 / 0.206 / 0.241; 0; không | 70 / 238 / 123; không | 0.0 ngày (không thủng) |
| DROP2 basket −20.1% 2022-11-09 16:00 | +1.86% (+1.86%) | 6.47 / 7.87% | 11-10 08:00 | 0.32x (11-10 18:00) | 0.096 / 0.096 / 0.096 / 0.096; 0; không | 79 / 437 / 88; không | 2.1 ngày |
| DROP3 basket −19.5% 2022-06-13 14:00 | +3.42% (+3.50%) | 4.46 / 5.35% | 06-13 09:00 | 0.52x | 0.116 / 0.117 / 0.118 / 0.134; 0; không | 0 / 192 / 179; không | 0.0 ngày (không thủng) |
| DROP4 basket −18.4% 2022-05-12 05:00 | −6.25% (−6.22%) | 9.46 / 10.18% | 05-12 04:00 | 0.45x | 0.140 / 0.143 / 0.145 / 0.173; 0; không | 132 / 298 / 161; không | 34.6 ngày |
| DROP5 basket −17.3% 2021-12-04 11:00 | +1.26% (+1.02%) | 3.26 / 6.27% | 12-04 05:00 | 0.60x (12-04 05:00) | 0.191 / 0.197 / 0.203 / 0.258; 0 giờ; không | 50 / 144 / 96; không | 2.3 ngày |

Đọc thêm trong results.json mỗi event: P&L theo giờ, 1m-lows từng coin
(ví dụ SOL −71% FTX, ETH −43% tuần 3AC, XRP −41% 2021-12-04), BTC nến 1m tệ
nhất (−2.0..−5.0%), spot-cost/Eq (0.42–0.47 khi carry mở, 0.0 khi không).

## Đối chiếu các nghiên cứu crash trước (tái dùng bảng, không tính lại)

- `oc_stresshist` (cùng G2, cửa sổ đặt tên khác): LUNA −3.0%/DD 9.7,
  3AC +3.6%/4.1, FTX −2.2%/9.2, AUG24 +6.3%/7.3 — cùng dấu và cùng độ lớn
  với hàng trên (chênh do cửa sổ −1d..+7d và vốn cộng dồn có carry).
- `oc_crashfreq`: các tuần này KHÔNG chứa one-bar dip-loss ≥10% nào
  (3AC thậm chí 0 stop: bleed nhiều ngày → timeout, không cascade trong
  một bar). Nỗi đau one-bar thật của bot là 2024-01-03 (−17..−22%/phase,
  xem `oc_ddanat4p`/`oc_ddanat_g2`), vốn không lọt top-5 basket-24h —
  lens basket-24h và lens single-bar bổ sung nhau.
- `oc_crash2020`: COVID W1 (−16% mix 4 pha) và 19/05/2021 (−10%) vẫn tệ
  hơn mọi tuần 2021–2026 ở trên (tệ nhất −6.3%).
- Margin toàn mẫu (`oc_carrymargin`): max 0.67 bal-base tại 2025-09-25,
  0 giờ block — các cửa sổ crash ở trên (max 0.26) còn xa ngưỡng.

## Kết luận 4 dòng (câu trả lời chính)

Một tuần crash với bot này trông như sau: thị trường rơi 17–21%/24h nhưng
bot chỉ mất tối đa ~6% vốn (LUNA −6.1%, còn lại −2.5%..+5.1% vì short book
và TP dip trả tiền), DD đánh dấu 1m 5–10%, dip gross không quá 0.8x nên
margin UTA chỉ dùng ≤26% (0 giờ block, không margin-call/liquidation nào,
stop thì có kích hoạt 19–132 lần trừ tuần bleed 3AC).
Ca tệ nhất là LUNA (mất 36 ngày hồi vốn), còn các crash nhanh gọn (FTX,
AUG24, 2021-12-04) hồi trong 0–14 ngày vì TP/timeout ngay sau đó.
Điểm mù thật không nằm ở các tuần này mà ở one-bar cascade kiểu
2024-01-03 và COVID — xem oc_crashfreq/oc_crash2020.
Giữ nguyên cấu hình (G2 + carry f=0.25 một UTA): crash week không phải
lý do để giảm f hay thêm cap mới.
