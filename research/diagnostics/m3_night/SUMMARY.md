# M3 night schedule (diagnostic only)
M3 = v342 L2 on CB books (book x0.75 + bracket dip limits 3.0 / 4.0 sigma, native 8-sigma touch stop). A human in Vietnam (UTC+7) cannot act at
the 03:00 local close (20 UTC). On a skipped bar no new book order and no dip limit (resting orders, SL, TP stay). 15-minute reaction elsewhere.
Rows (dev4 / worst dev year / DD | 5y | most recent year | gate DD; no losing year anywhere):
- every bar, 15-min reaction      6.057 / 3.461 / 17.66 | 5.786 | 4.708 | 17.66
- skip the 20 UTC bar (03:00 VN)   5.264 / 2.661 / 17.81 | 5.150 | 4.692 | 17.81
- skip 16 + 20 UTC (23:00, 03:00)  4.395 / 2.232 / 18.47 | 4.413 | 4.485 | 18.47
Bootstrap of the base (every bar, minute-5 rule): monthly p50 6.08, P(>=5) 0.655, DD p95 18.99, P(DD > 20) 0.035.
Reading: a trader who acts at 07/11/15/19/23 h local keeps the 5y floor (5.15); skipping 23 h too drops below it (4.41).
