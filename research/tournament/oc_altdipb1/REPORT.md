# oc_altdipb1 REPORT (2026-10-07; PLAN pre-registered before any outcome)

## Setup

G2 dip ladder (R2 depths 2.5/3/3.5/4/5, TP 1sg, close5 stop 4sg, 8sg backstop,
timeout at next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding)
with corr-aware B1 sizing (w = 1/(1+n)) on three large alts DOGE/ADA/TRX
(Binance USD-M 1m, data/raw/alts_intraday_20260926 + manifest), 4 clock phases
(4h grid 2020-08-01 + 0/1/2/3h), bars open in [2021-09-24, 2026-09-24).
MAJORS = 5-majors reference (n among majors 0..4). ALT8 = all 8 coins traded,
n counts flushing coins among ALL 8 (0..7), budget per coin as the majors
(same rungs, same w formula). ALT3 = the 3 alts only, n counted on all 8,
sizes exactly as in ALT8 (subset; ALT8 = majors-leg + ALT3 by construction).
Units are w*y (established dip convention); no sleeve-to-%/month overlay or
leverage is claimed. Research only: owner trades majors, deployment needs OK.

## Coverage (listing-date check)

Manifest first/last: DOGE 2020-07-10 (156 missing 1m) / ADA 2020-02-01 /
TRX 2020-02-01, all last 2026-09-23 23:59 — all predate 2021-09-24, no alt
lists inside the test window. Traded bars/coin/year (valid O+sigma): every
coin 8760/8760/8784/8760/8757 (identical: no alt ever skipped a bar the
majors traded). G2 f=0 check: v421 R2B1D17BFG2 reproduced read-only to the
digit (R 5.41 / W 2.588 / DD 16.91 / full 16.82).

## Replica fidelity (MAJORS must come first)

Phase-0 fills/coin 1067/1126/952/1179/1174 = oc_dipexit to the tick;
4-phase-mean sums 0.911/0.833/2.100/3.197/0.677 and DDs
0.856/0.951/0.800/0.355/0.607 = oc_placebo_dip base exactly; 5y sum 7.718304.
22312 fills, checksum b0ce3ab25de34383. ALT8: 34632 fills (majors 22312
identical fill SET, only sizes reweighted by 8-coin n; alts 12320 =
DOGE 4576 / ADA 3899 / TRX 3845), checksum 30dcee7e609058a9.

## ALT3 standalone per year (4-phase mean S / DD / n / win / stop rate)

| year | S | DD | n | win | stop rate |
|---|---|---|---|---|---|
| 2021 | 0.432 | 0.623 | 564.0 | .674 | .057 |
| 2022 | 0.178 | 0.654 | 586.0 | .676 | .084 |
| 2023 | 0.628 | 0.718 | 811.3 | .707 | .063 |
| 2024 | 0.949 | 0.464 | 537.8 | .695 | .031 |
| 2025 | 0.286 | 0.285 | 581.0 | .645 | .034 |
| 5y | 2.473 | — | 12320 fills | — | — |

ALT3 is positive in all 5 years with majors-like win rates; stop rates 3-8%.
Correlation of ALT3 daily P&L vs the majors-leg daily P&L (exit-date sums,
pooled phases): pooled 0.565; per year 0.68/0.68/0.44/0.20/0.66 — the alt
sleeve fires together with the majors book (not a diversifier).

## ALT8 vs MAJORS per year (4-phase mean) + dip-gate legs (labelled)

| year | S MAJORS / ALT8 | DD MAJORS / ALT8 | (a) sum>=base | (b) DD<=base+0.01 |
|---|---|---|---|---|
| 2021 | 0.911 / 1.405 | 0.856 / 1.226 | YES (+0.493) | NO (+0.370) |
| 2022 | 0.833 / 1.086 | 0.951 / 1.264 | YES (+0.253) | NO (+0.313) |
| 2023 | 2.100 / 2.558 | 0.800 / 1.210 | YES (+0.458) | NO (+0.410) |
| 2024 | 3.197 / 3.673 | 0.355 / 0.447 | YES (+0.475) | NO (+0.092) |
| 2025 | 0.677 / 0.948 | 0.607 / 0.799 | YES (+0.270) | NO (+0.192) |
| 5y | 7.718 / 9.669 | — | 5/5 | 0/5 |

(c, labelled stricter) 5y 4-phase-mean dSum ALT8-MAJORS = +1.950, i.e. +1.677
above the +0.273 pooled placebo p95: the sum gain is far beyond reweighting
noise. Dev4 (2021-2024, the comparison set): sum 4/4, DD 0/4. Last year
(2025-09-24..2026-09-23, scored ONCE for the frozen ALT8/ALT3 + reference):
sum YES, DD NO — same picture, labelled.

## Notes

- The +1.95 splits into ALT3 +2.473 of new alt P&L minus -0.523 of majors-leg
  shrinkage (7.196 vs 7.718): counting alt flushers in n correctly shrinks
  majors sizes in correlated flushes, and that insurance costs P&L.
- B1 across 8 does NOT defuse the extra book's DD: ALT8 DD is worse every
  year (+0.09 to +0.41), so the v398 lesson stands for large alts too —
  correlated alt dips add absolute DD even with corr-aware sizing.
- No post-hoc change to variants, thresholds, costs, or the decision rule.
  Pre-outcome code fix only: single-coin smoke branch (never-stack guard;
  smoke saw 28 fills on 300 bars, no study outcome). One process, peak
  RAM < 3 GB via scripts/heavy_slot.py. All 5 years are research data; a
  positive result would still need prospective paper + owner OK.
- Repro: research/tournament/oc_altdipb1/{PLAN.md,compute_altdipb1.py,
  results.json,REPORT.md} + tests/test_oc_altdipb1.py (11 tests pass).

## Verdict

KHÔNG trình cho owner: ALT8 thắng MAJORS về tổng 5/5 năm (+1.95, vượt xa ngưỡng placebo +0.273) nhưng thua về DD cả 5/5 năm (+0.09 tới +0.41, không năm nào trong +1pp).
ALT3 đơn lẻ dương cả 5 năm (2.47, win ~65-71%) nhưng tương quan cao với book majors (0.57 gộp), nên chỉ là đòn bẩy tương quan chứ không đa dạng hoá.
Giữ nguyên universe majors-only cho deployment; hướng alt khép lại ở đây (nghiên cứu thuần túy).
