# oc_carryutil REPORT -- how often the frozen carry rule is invested (descriptive, no tuning)

Frozen rule (oc_cashcarry PLAN.md, unchanged): per coin enter the next quarterly when front has <= 7d left, ENTER iff annualised basis ln(F/S)*365/DTE >= 4 %/yr, equal-notional spot long + quarterly short (f = 0.25/coin), hold to delivery, fee drag 0.00275/allocated. Local 4h parquet only; no network, no 1m, no orders. Repro: `research/tournament/oc_carryutil/analyze_carryutil.py` -> `results.json`; test `tests/test_oc_carryutil.py`. Cross-checks oc_cashcarry pooled sums.

## Utilization per coin per calendar year (numerator = days an ENTERED pair is open)

| year | days | BTC ent/skip | BTC share | BTC bE/bS | ETH ent/skip | ETH share | ETH bE/bS |
|---|---|---|---|---|---|---|---|
| 2021 | 365 | 5/0 | 91.0% | 15.9%/n/a | 5/0 | 90.7% | 18.1%/n/a |
| 2022 | 365 | 1/3 | 47.7% | 7.5%/1.8% | 1/3 | 47.7% | 4.5%/0.7% |
| 2023 | 365 | 4/0 | 76.7% | 7.4%/n/a | 2/2 | 29.0% | 8.6%/3.5% |
| 2024 | 366 | 4/0 | 100.0% | 13.2%/n/a | 4/0 | 100.0% | 13.1%/n/a |
| 2025 | 365 | 4/0 | 100.0% | 5.2%/n/a | 3/1 | 98.4% | 5.6%/3.4% |
| 2026 | 279 | 0/2 | 30.5% | n/a/2.7% | 0/2 | 0.0% | n/a/1.9% |

Overall 2021-01-01..last spot bar: BTC invested 1602/2105 = 76.1%; ETH 1336/2105 = 63.5%. Skips cluster: 2022 bear (8 skips) and 2025-2026 low-basis (5 of 6 skipped in the most recent anchor year) -- the filter idles instead of forcing risk.

## Contribution to the +0.22 %/mo carry lift (anchor pool 2021-09-24..2026-09-24, f = 0.25)

- BTC: n=14, sum_ret_alloc=0.2959 -> +0.1233 %/mo = 56.5% of the lift.
- ETH: n=11, sum_ret_alloc=0.2275 -> +0.0948 %/mo = 43.5% of the lift.
Total +0.2181 %/mo arithmetic at f = 0.25 (matches oc_cashcarry +0.2181; geometric +0.2130).

## What a skipped ETH quarter costs in expectation

Skipped ETH quarters: n=8 (2022-09-30, 2022-12-30, 2023-03-31, 2023-06-30, 2023-12-29, 2026-03-27, 2026-06-26, 2026-09-25); mean skipped basis 2.0% over ~98.0d.
Counterfactual (same settlement math, had they been entered): mean 0.332% on allocated (range -0.391..1.020%), = ~0.0830% of account per skipped quarter at f = 0.25.
Reference: entered ETH quarters in the anchor window average 2.068% on allocated; basis-implied lock at the skipped mean = 0.275%. A skipped ETH quarter costs about one-sixth of an entered quarter's premium -- small by design, the price of the 4% filter.

## Today (assignment context from scripts/carry_calendar.py, not refetched)

BTC Dec-26 basis ~+5.1 %/yr (>= 4%: ENTER-able); ETH ~+3.8 %/yr (< 4%: SKIP). So today the book would carry BTC and sit out ETH -- exactly the idle-ETH pattern above.

## Ghi chu cho chu (4 dong, carry nam im la binh thuong)

Carry co luc nam im hang thang, nhat la khi basis duoi 4%/nam quy phai bo qua.
Lich su 2021-2026: ETH chi dau tu ~2/3 thoi gian, nhieu quy lien tiep dung ngoai.
Bo mot quy ETH neu co vao chi them ~0.08% tai khoan (quy dat chuan ~0.5%); doi lai khong om basis re.
Nam im la tinh nang cua bo loc, khong phai loi -- cu de no cho premium quay lai.
