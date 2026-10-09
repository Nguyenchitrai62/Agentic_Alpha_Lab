# oc_tailhedge REPORT — long BTC puts do NOT move the frontier (negative result)

Rule frozen in PLAN.md before any outcome. One account
A(t)=A(t-1)*(1+r_bot(t))+dHedge(t) (UTA: BOT sizes on total equity).
Repro: `.venv/Scripts/python.exe research/tournament/oc_tailhedge/analyze_tailhedge.py`
(one process, streams one yearly 1m file at a time, no engine reruns) + test
`tests/test_oc_tailhedge.py`. Trade ledger: `hedge_ledger.csv` (972 rows).

Validation: no-hedge legs reproduce v421_result G2 (5.41 / W 2.588 / DD 16.91 /
full 16.82) and v422_result G2K20 (5.874 / W 2.832 / DD 17.79 / full 17.69) TO THE
DIGIT (asserted in-script). Grid/hours/1m/IV all capped 2026-09-24T00:00Z.

## Dev4 (anchors 2021-2024; R %/mo | cons DD | opt DD | hedge cost/yr | buys/TPs)

| row | 2021 | 2022 | 2023 | 2024 | dev4 mean/W/maxDD | full DD |
|---|---|---|---|---|---|---|
| G2 | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601/2.588/16.91 | 16.82 |
| G2K20 | 2.832/12.01 | 3.272/17.79 | 7.149/15.79 | 11.644/9.34 | 6.166/2.832/17.79 | 17.69 |
| G2+H(.15,1) | 0.891/23.85 | 1.623/20.07 | 4.485/17.95 | 8.855/15.17 | 3.917/0.891/23.85 | 28.84 |
| G2+H(.15,2) | -0.985/38.97 | -0.216/30.60 | 2.732/34.01 | 6.849/27.82 | 2.049/-0.985/38.97 | 55.71 |
| G2+H(.25,1) | 1.292/20.44 | 2.009/17.64 | 4.765/15.78 | 9.293/14.01 | 4.293/1.292/20.44 | 23.55 |
| G2+H(.25,2) | -0.035/32.89 | 0.702/24.56 | 3.452/27.46 | 7.876/24.08 | 2.953/-0.035/32.89 | 43.66 |
| G2K20+H(.15,1) | 1.136/24.00 | 1.618/20.75 | 5.582/18.45 | 9.811/14.84 | 4.479/1.136/24.00 | 29.69 |
| G2K20+H(.15,2) | -0.739/38.94 | -0.215/31.42 | 3.821/32.79 | 7.794/26.70 | 2.608/-0.739/38.94 | 55.78 |
| G2K20+H(.25,1) | 1.535/20.63 | 1.999/18.42 | 5.864/16.10 | 10.256/13.67 | 4.855/1.535/20.63 | 24.46 |
| G2K20+H(.25,2) | 0.206/33.07 | 0.694/25.19 | 4.546/26.14 | 8.835/23.74 | 3.513/0.206/33.07 | 44.33 |

Optimistic (hourly-low) DD equals conservative to ~0.1pp everywhere: the low-mark
view changes nothing. Hedge cost/yr (paid minus received, year-start-equity units):
h=1: 0.17-0.23 (2021) rising to 0.30-0.42 (2024, equity and BTC both higher);
h=2 doubles it. TPs fired only in real crashes: LUNA May-2022 (5.4-5.6x), FTX
Nov-2022 (5.2-6.1x), Jul-2024 dip (5.4x). Expiry-ITM settlements: Dec-2021, Jan-2022,
Jun-2022 (m.15 also Feb-2025, Nov-2025). 12 rolls + 1 TP per dev year, every row.

## Top-5 G2 DD episodes (gate DD series) vs chosen-row hedge P&L

| peak -> trough | G2 DD | hedge P&L (chosen, % of peak eq) |
|---|---|---|
| 2023-04-17 -> 2023-06-14 | 16.82 | -0.60 |
| 2024-01-03 11:00 -> 12:00 | 14.71 | +0.01 |
| 2023-07-14 -> 2023-10-02 | 13.80 | -0.22 |
| 2022-07-20 -> 2022-11-10 (FTX) | 13.18 | -2.01 |
| 2024-03-05 flash | 13.17 | +0.10 |

The puts pay only inside multi-week BTC waterfalls (May/Nov-2022, Dec-2025); G2's
gate DDs are dip-sleeve disposals and flash crashes the monthly put barely sees,
while the 17-42 %/yr premium bleed deepens every other drawdown.

## Key question

**Does any G2K20+H row beat G2 on dev4 mean AND have yearly/full DD <= G2's
(conservative view)? No.** The best hedge row (G2K20+H m0.25 h1.0: dev4 4.855 vs G2
5.601) loses 0.75pp/mo AND raises DD (20.63/24.46 vs 16.91/16.82). No hedge row
passes DD <= 20 with no losing dev year (h=2 rows lose money in 2021-2022); the
robust-criterion fallback picks G2K20+H(m0.25,h1.0) (highest dev4 worst-year 1.535).

## Last year, scored once (chosen + G2 only)
G2K20+H(m0.25,h1.0): 3.381 %/mo, DD 17.89 (cost 0.179, 12 buys, 1 TP).
G2: 4.648 %/mo, DD 12.90. The chosen row trails by 1.27pp/mo at +4.99pp DD, despite
a 41.5x TP payout in the Dec-2025 crash (cash +2.12 full-path units) — the other
eleven months' bleed plus the Jan-2026 slide (row full-DD trough 2026-01-31) eat it.

## Why it failed (3 lines)
Monthly 15-25% OTM BTC puts at ~100% IV cost ~1.5-2.5% of notional per month, i.e.
17-42% of equity per year at h=1-2, but G2's DDs are not monthly-BTC-waterfall
shaped, so the payout (a few 5-6x TPs + small expiry intrinsics per 5y) covers only
a third of the bleed. Doubling h doubles both bleed and DD instead of insuring it.
A cheaper hedge (further OTM, longer dated, or event-triggered rather than always-on)
is a different pre-registered direction, not an extra row here.

## Caveats
Aggregated OTM IV + fixed skew add-on (+0.05/+0.10) is not a strike-level quote;
deep-OTM puts trade wider, so real bleed is weakly LARGER than reported. Bybit
check 2026-10-07 (public GET instruments-info, BTC spot ~85.7k): options are
USDT-settled (not USDC); monthly/quarterly expiries list puts covering 15-25% OTM
(e.g. 30OCT26: 46k-106k; 27NOV26: 58k-112k) but dailies/weeklies do not (78k-104k
only); strikes step 1000-2000 so a floored-to-1000 K can miss a listed strike by up
to 1000; min order 0.01 BTC; delivery fee 0.00015. No exchange orders were placed.

## Leakage / timing checks
IV at t = last 4h bar with close <= t (searchsorted right on bar-close ns; asserted
in tests). S_close(t)/S_low(t) use 1m minutes strictly before t. Settlement mean
07:30-07:59 applied at first grid hour after 08:05. No fits/thresholds; all
constants in PLAN.md. Cap 2026-09-24T00:00Z enforced on grid, 1m, IV (test asserts
max ledger/grid timestamps < cap). Last-year data touched only in the single
last-year pass for the chosen row + G2.

## Vietnamese verdict
KHÔNG chấp nhận hedge put mua-định-kỳ: mọi hàng rào đều giảm lợi nhuận dev4 và TĂNG DD, không hàng nào qua cổng.
Nguyên nhân là phí bảo hiểm ~1.5-2.5%/tháng vượt xa khoản chi trả trong các đợt DD của G2 (vốn không phải dạng waterfall BTC).
Hướng này đóng lại ở dạng always-on; nếu mở lại phải là biến thể rẻ hơn và đăng ký trước (xa OTM hơn / theo sự kiện).
