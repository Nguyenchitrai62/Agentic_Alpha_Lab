# KE HOACH TANG VON THEO GIAI DOAN (paper -> testnet -> live) — G2

> Chuong trinh IDEAS10 #2. Chien luoc G2 (R2B1D17BFG2, v421: 5,41%/thang, DD nam 16,91,
> full-path 16,82). Nguong dung tu DEV 2021-2024, KHONG dung nam gan nhat. Khong lenh live o day.

## 1. Thang von (V1) — % tren von du kien

- Tuan 0-4: 5%. Tuan 4-8: 25%. Tuan 8-12: 100%. Len bac chi khi tuan truoc KHONG dung.
- V2 = V1 + luat giam mot nua (muc 4): DD chien luoc 90 ngay >19% -> giam von mot nua ngay.

## 2. Nguong DUNG (dong bang mo moi, giu SL/TP)

- (H1) Lech live-vs-replay 4 tuan: |m_live - m_replay| > 0,5%/thang thi DUNG.
  m = %/thang hinh hoc 28 ngay. Live = `scripts/fm_paper_eval.py` (common-uptime,
  restart-floored). Replay = chay lai CUNG plan (gia Bybit, phi maker 0,02%/
  taker 0,055%, funding long 0,01%/8h short 0, khop trade-through, cam 5 phut dau, stop-first).
- (H2) DD 28 ngay cua sleeve (quy ve 100%): >17,0% thi DUNG. Quy ra tai khoan:
  size 5% ~0,85%; 25% ~4,25%; 100% ~17,0%.
- Nguon nguong: DEV max28 14,71% +2diem; max90 16,82% +2diem (oc_underwater 39 dot DEV,
  xau nhat 16,8%, dai nhat 149 ngay; flash 2024-01-03 la co che gay DD).

## 3. Ai kiem tra gi moi tuan (Chu nhat)

- CHU TAI KHOAN: chay fm_paper_eval + DD 28/90 ngay, ghi 1 dong (equity, DD, lech, fills, halt Y/N).
- BOT: paper truoc, testnet sau; giu 4 runner + backend (plan tuoi <4h30m).
- Vuot nguong: dung mo moi tuan do, chi giu SL/TP; mo lai sau 4 tuan sach.

## 4. Viec chu lam TRUOC tien that (1 lan)

1. Testnet 7 ngay PASS theo `docs/TESTNET_PLAN_VI.md` (unprotected 0, qty khop, PostOnly).
2. Tu dien key vao `.env` local (BYBIT_TESTNET_*, khong commit/dan chat); live chi sau testnet + paper >=8 tuan.
3. Tai khoan: UTA, Hedge, Cross 5 coin, don bay 5x; von toi thieu ~5000 USDT.
4. Nap tung bac (5% -> 25% -> 100%), khong tat luat dung bang tay; moi lan bo qua phai ghi log.

## 5. Ky vong trung thuc

- DEV 2021-2024: 5,60%/thang (tung nam 2,59/3,28/6,05/10,68), DD 16,91, khong nam lo.
- Nam gan nhat (REF-ONLY, cham 1 lan): 4,65%/thang, DD 12,9. Can paper 8-12 tuan xac nhan.
