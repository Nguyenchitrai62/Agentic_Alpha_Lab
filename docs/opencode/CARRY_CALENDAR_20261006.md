# Lich carry quarterly nghich dao (Bybit) — 2026-10-06

Script chi doc: `scripts/carry_calendar.py` (endpoint cong khai Bybit V5, khong key, khong dat lenh).
Quy tac dong bang nhap tu `scripts/carry_paper.py` (`RULE_PARAMS`, `is_quarterly_delivery`,
`annualised_basis`; nguong basis 4%/nam, cua so roll <= 7 ngay). Test offline:
`tests/test_carry_calendar.py` (3 test, fake API, da pass).

Ket qua live (mainnet) luc 2026-10-06 ~15:15 UTC — hop dong quarterly INVERSE dang niem yet:

- BTC: `BTCUSDZ26` dao han 2026-12-25 08:00 UTC = 15:00 gio VN, DTE ~79.7 ngay,
  basis ~+5.06%/nam -> DAT nguong (>= 4%); `BTCUSDH27` dao han 2027-03-26 08:00 UTC
  = 15:00 gio VN, DTE ~170.7 ngay, basis ~+5.04%/nam -> DAT nguong.
- ETH: `ETHUSDZ26` cung ngay dao han, basis ~+3.8%/nam -> DUOI nguong (SKIP);
  `ETHUSDH27` basis ~+3.9%/nam -> DUOI nguong (SKIP).

Cua so roll (mo vi the KE TIEP chi khi basis >= 4%/nam): tu 2026-12-18 08:00 UTC
(= 15:00 VN) cho ky han DEC26; tu 2027-03-19 08:00 UTC (= 15:00 VN) cho ky han MAR27.
Den han: futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong
luc 08:00 UTC (= 15:00 gio VN). Tuan `--json` de lay JSON cho bot.

Output dan truc tiep (text):

```
carry_calendar now=2026-10-06T15:15:21.356000+00:00 threshold=4%/yr roll<=7d (inverse quarterly, public only)
== BTC ==
BTCUSDZ26 delivery 2026-12-25T08:00 UTC = 2026-12-25T15:00 VN | DTE 79.7d | basis +5.06%/yr -> ENTER-ABLE
  roll window: tu 2026-12-18T08:00 UTC (= 2026-12-18T15:00 VN)
  * Tu 2026-12-18 (2026-12-18 gio VN): mo cua so roll BTCUSDZ26 (front chi con <=7 ngay); vao cap spot-long + quarterly-short KE TIEP chi khi basis >= 4%/nam.
  * Den han 2026-12-25 08:00 UTC = 2026-12-25 15:00 gio VN: futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong luc 08:00 UTC (= 15:00 gio VN).
BTCUSDH27 delivery 2027-03-26T08:00 UTC = 2027-03-26T15:00 VN | DTE 170.7d | basis +5.04%/yr -> ENTER-ABLE
  roll window: tu 2027-03-19T08:00 UTC (= 2027-03-19T15:00 VN)
  * Tu 2027-03-19 (2027-03-19 gio VN): mo cua so roll BTCUSDH27 (front chi con <=7 ngay); vao cap spot-long + quarterly-short KE TIEP chi khi basis >= 4%/nam.
  * Den han 2027-03-26 08:00 UTC = 2027-03-26 15:00 gio VN: futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong luc 08:00 UTC (= 15:00 gio VN).
== ETH ==
ETHUSDZ26 delivery 2026-12-25T08:00 UTC = 2026-12-25T15:00 VN | DTE 79.7d | basis +3.79%/yr -> SKIP (<4%)
  roll window: tu 2026-12-18T08:00 UTC (= 2026-12-18T15:00 VN)
  * Tu 2026-12-18 (2026-12-18 gio VN): mo cua so roll ETHUSDZ26 (front chi con <=7 ngay); vao cap spot-long + quarterly-short KE TIEP chi khi basis >= 4%/nam.
  * Den han 2026-12-25 08:00 UTC = 2026-12-25 15:00 gio VN: futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong luc 08:00 UTC (= 15:00 gio VN).
ETHUSDH27 delivery 2027-03-26T08:00 UTC = 2027-03-26T15:00 VN | DTE 170.7d | basis +3.91%/yr -> SKIP (<4%)
  roll window: tu 2027-03-19T08:00 UTC (= 2027-03-19T15:00 VN)
  * Tu 2027-03-19 (2027-03-19 gio VN): mo cua so roll ETHUSDH27 (front chi con <=7 ngay); vao cap spot-long + quarterly-short KE TIEP chi khi basis >= 4%/nam.
  * Den han 2027-03-26 08:00 UTC = 2027-03-26 15:00 gio VN: futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong luc 08:00 UTC (= 15:00 gio VN).
```
