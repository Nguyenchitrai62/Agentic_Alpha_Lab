# REPORT.md — oc_lit_calendar (calendar book gates H1+H2+H7)

Engine: v426_book_brake mechanism on G2 (inv/k1.0/kd1.7/bear/G2.0); G2-5y reproduced to the digit (5.41/W2.588/DD16.91/full16.82) before judging overlays.

## Dev4 selection table (2021-09-24 .. 2025-09-23 anchors 2021-2024; R %/mo, DD yearly-max)

| row | dev4 mean | dev4 worst | dev4 DD | losing | beats control |
|---|---|---|---|---|---|
| R2B1D17BFG2 | 5.601 | 2.588 | 16.91 | 0 | - |
| V1 | 5.815 | 2.828 | 16.97 | 0 | - |
| V2 | 5.632 | 2.621 | 17.84 | 0 | - |
| V3 | 6.131 | 2.646 | 17.24 | 0 | - |
| S1 | 5.856 | 2.75 | 16.66 | 0 | - |
| S2 | 2.274 | 0.904 | 13.71 | 0 | - |
| S3 | 5.908 | 2.717 | 16.76 | 0 | - |
| G1H | 5.563 | 2.581 | 16.91 | 0 | - |
| G2H | 5.415 | 2.314 | 16.91 | 0 | - |
| G3H | 5.63 | 2.748 | 16.91 | 0 | - |
| C_V1 | 5.794 | 2.697 | 16.9 | 0 | variant-control +0.021 |
| C_V2 | 5.918 | 2.579 | 16.58 | 0 | variant-control -0.286 |
| C_V3 | 5.601 | 2.588 | 16.91 | 0 | variant-control +0.530 (NO-OP=bug replica, kept; judged vs _FIX) |
| C_S1 | 5.601 | 2.588 | 16.91 | 0 | variant-control +0.255 (NO-OP=bug replica, kept; judged vs _FIX) |
| C_S2 | 5.601 | 2.588 | 16.91 | 0 | variant-control -3.327 (NO-OP=bug replica, kept; judged vs _FIX) |
| C_S3 | 5.601 | 2.588 | 16.91 | 0 | variant-control +0.307 (NO-OP=bug replica, kept; judged vs _FIX) |
| C_G1 | 5.641 | 2.581 | 16.87 | 0 | variant-control -0.078 |
| C_G2 | 5.442 | 2.314 | 16.65 | 0 | variant-control -0.027 |
| C_G3 | 5.635 | 2.656 | 16.87 | 0 | variant-control -0.005 |
| C_V3_FIX | 5.966 | 2.399 | 17.14 | 0 | V3-control +0.165 (JUDGED) |
| C_S1_FIX | 5.701 | 2.833 | 16.56 | 0 | S1-control +0.155 (JUDGED) |
| C_S2_FIX | 4.296 | 1.609 | 13.26 | 0 | S2-control -2.022 (JUDGED) |
| C_S3_FIX | 5.84 | 2.997 | 16.47 | 0 | S3-control +0.068 (JUDGED) |

G2 dev4 reference: {'R': 5.601, 'W': 2.588, 'DD': 16.91, 'losing': 0, 'years': [[2.588, 10.86], [3.282, 16.91], [6.045, 15.81], [10.677, 8.27]]}. Rule: candidate iff dev4 mean > 5.601 AND worst > 2.588 AND DD <= 17.41 AND beats own exposure control (judged: _FIX rows for V3/S1/S2/S3). Qualifiers: ['V1', 'V3', 'S1', 'S3']; robust tie-break (highest dev4 worst-year) -> pick: V1.

## Gate accounting (standard index; share of IN bars + realised mean mults)

| variant | year | IN share | mean mult | mean long | mean short | c/cL/cS |
|---|---|---|---|---|---|---|
| V1 | 2021-09-24 | 0.164384 | 0.874658 | 0.874009 | 0.873585 | 0.874658/0.874658/0.874658 |
| V1 | 2022-09-24 | 0.164384 | 0.874658 | 0.875945 | 0.872282 | 0.874658/0.874658/0.874658 |
| V1 | 2023-09-24 | 0.164384 | 0.874658 | 0.875134 | 0.874206 | 0.874658/0.874658/0.874658 |
| V1 | 2024-09-24 | 0.164384 | 0.874658 | 0.874301 | 0.874721 | 0.874658/0.874658/0.874658 |
| V2 | 2021-09-24 | 0.164384 | 0.749315 | 0.748019 | 0.747169 | 0.749315/0.749315/0.749315 |
| V2 | 2022-09-24 | 0.164384 | 0.749315 | 0.751889 | 0.744563 | 0.749315/0.749315/0.749315 |
| V2 | 2023-09-24 | 0.164384 | 0.749315 | 0.750269 | 0.748412 | 0.749315/0.749315/0.749315 |
| V2 | 2024-09-24 | 0.164384 | 0.749315 | 0.748603 | 0.749442 | 0.749315/0.749315/0.749315 |
| V3 | 2021-09-24 | 0.164384 | 0.761205 | 0.874009 | 0.578616 | 0.761205/0.874009/0.578616 |
| V3 | 2022-09-24 | 0.164384 | 0.739511 | 0.875945 | 0.574272 | 0.739511/0.875945/0.574272 |
| V3 | 2023-09-24 | 0.164384 | 0.764155 | 0.875134 | 0.580687 | 0.764155/0.875134/0.580687 |
| V3 | 2024-09-24 | 0.164384 | 0.771169 | 0.874301 | 0.582403 | 0.771169/0.874301/0.582403 |
| S1 | 2021-09-24 | 0.166667 | 0.903105 | 0.791879 | 1.0 | 0.791879/0.791879/1.0 |
| S1 | 2022-09-24 | 0.166667 | 0.898813 | 0.79169 | 1.0 | 0.79169/0.79169/1.0 |
| S1 | 2023-09-24 | 0.166667 | 0.876142 | 0.791699 | 1.0 | 0.791699/0.791699/1.0 |
| S1 | 2024-09-24 | 0.166667 | 0.875479 | 0.7918 | 1.0 | 0.7918/0.7918/1.0 |
| S2 | 2021-09-24 | 0.166667 | 0.61242 | 0.167517 | 1.0 | 0.167517/0.167517/1.0 |
| S2 | 2022-09-24 | 0.166667 | 0.595251 | 0.166761 | 1.0 | 0.166761/0.166761/1.0 |
| S2 | 2023-09-24 | 0.166667 | 0.504566 | 0.166795 | 1.0 | 0.166795/0.166795/1.0 |
| S2 | 2024-09-24 | 0.166667 | 0.501918 | 0.167201 | 1.0 | 0.167201/0.167201/1.0 |
| S3 | 2021-09-24 | 0.333333 | 0.922694 | 0.833954 | 1.0 | 0.833954/0.833954/1.0 |
| S3 | 2022-09-24 | 0.333333 | 0.918995 | 0.833239 | 1.0 | 0.833239/0.833239/1.0 |
| S3 | 2023-09-24 | 0.333333 | 0.900913 | 0.833359 | 1.0 | 0.833359/0.833359/1.0 |
| S3 | 2024-09-24 | 0.333333 | 0.900525 | 0.833677 | 1.0 | 0.833677/0.833677/1.0 |
| G1H | 2021-09-24 | 1.0 | 0.75 | 0.75 | 0.75 | 0.75/0.75/0.75 |
| G1H | 2022-09-24 | 0.09589 | 0.976027 | 0.994031 | 0.956068 | 0.976027/0.976027/0.976027 |
| G1H | 2023-09-24 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0/1.0/1.0 |
| G1H | 2024-09-24 | 0.336986 | 0.915753 | 0.917392 | 0.92101 | 0.915753/0.915753/0.915753 |
| G2H | 2021-09-24 | 1.0 | 0.75 | 0.75 | 0.75 | 0.75/0.75/0.75 |
| G2H | 2022-09-24 | 0.09589 | 0.976027 | 0.994031 | 0.956068 | 0.976027/0.976027/0.976027 |
| G2H | 2023-09-24 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0/1.0/1.0 |
| G2H | 2024-09-24 | 0.336986 | 0.915753 | 0.917392 | 0.92101 | 0.915753/0.915753/0.915753 |
| G3H | 2021-09-24 | 0.934247 | 0.766438 | 0.78163 | 0.754006 | 0.766438/0.766438/0.766438 |
| G3H | 2022-09-24 | 0.09589 | 0.976027 | 0.994031 | 0.956068 | 0.976027/0.976027/0.976027 |
| G3H | 2023-09-24 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0/1.0/1.0 |
| G3H | 2024-09-24 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0/1.0/1.0 |

## Most-recent year, scored once (2025-09-24 .. 2026-09-23; G2 + pick/control only)

- R2B1D17BFG2: R 4.648 %/mo, DD 12.9, full-path DD 16.82.
- V1: R 4.304 %/mo, DD 13.83, full-path DD 16.93.
- C_V1: R 4.374 %/mo, DD 13.82, full-path DD 16.82.

## Leakage checks

- Feature timing: gate at T uses only T's date/hour + public calendars (TOM dates, UTC windows, halving dates) known at T's close; applied after the bear filter (open[T]-inclusive) and before shifted-clock ffill (v426 order).
- Label windows: engine forward returns start at the next 4h open after close.
- Fit windows: none — all multipliers/thresholds/windows are frozen constants (0.85/0.70/0.50/0.75/0.0, dip 0.7692); 7-day embargo vacuous.
- Fill timing: 5-min ban + 1m trade-through + stop-first (inherited from engine).
- H2 operability: literal 'fully inside 21-23 UTC' is empty on the 4h grid; PLAN pre-registered the overlap analogue (20:00 bar; S3 20:00+00:00) before outcomes.
- G2H dip: time-varying fill scale 0.7692 in-window (operable analogue of a 0.26->0.20 budget cut; caps unchanged); C_G2 uses the per-year mean scale as a flat control.

## What failed and why

- H1 TOM: V1 (+0.214 pp/mo vs G2 dev4) and V3 (+0.530) pass, but V1 beats its exposure control by only +0.021 — the TOM level effect is almost entirely a flat exposure cut (outside-TOM downscaling), with negligible timing value. V2 (x0.7 outside) breaches the DD bound (17.84 > 17.41) and loses to its control.
- H2 overnight: S1 (+0.255 vs G2, +0.155 vs C_S1_FIX) and S3 (+0.307 vs G2, +0.068 vs C_S3_FIX) pass dev4, but both timing edges are small and neither survives as the robust pick. S2 (longs-only-in-window, flat outside) collapses to 2.274 %/mo — the window holds no exploitable long edge worth concentrating in.
- H7 halving: all three fail cleanly. G1H/G2H/G3H gate at most one partial year each (2021-22 fully in-window, 2023-24 never, 2024-25 partially); G1H/G3H trail G2 and their controls, G2H (extra dip cut) is the worst of the family (5.415). With 3-4 halving events the CI is hopelessly wide — direction CLOSED, as §C predicted.
- Implementation error, disclosed: first-run C_V3/C_S1/C_S2/C_S3 were fancy-index no-ops (= G2 bit-exact). Original rows kept above; candidacy was re-judged against the corrected C_*_FIX extra rows (9-test pytest file pins both behaviours).
- Dev4 pick V1 (+0.214 pp/mo vs G2 dev4, beats C_V1 by +0.021); 2025 once: 4.304 %/mo vs G2 4.648 / C_V1 4.374 — the frozen finalist underperforms both in the only blind year, so no deployment.

## Verdict (3 dong tieng Viet)
CAN THEM BANG CHUNG PAPER: V1 picked on dev4 but 2025 mixed vs G2/control.
Chon tren dev4 (2021-2024) theo luat robust so voi G2; nam 2025 cham mot lan cho ung vien dong bang.
Chot: needs prospective evidence — khong mo them bien the lich trong huong nay.

