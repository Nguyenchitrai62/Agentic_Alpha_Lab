# oc_levfrontier — REPORT (2026-10-08; PLAN frozen before any outcome)

Deployable return/drawdown frontier on BYBIT prices with carry: leverage (kd 1.7 G2 vs 2.0
G2K20, every row with G2's gross cap G=2.0, everything else G2) x overlay (none / C2 / B7 /
B7xC2 uncapped product), each on Binance (base) AND Bybit S5, then the quarterly carry
overlay f=0.25 exactly as `research/tournament/oc_c2carry` (ONE-account UTA compounding).
PLAN.md was written BEFORE any outcome; no definition changed after outcomes. Engine for the
6 missing BOT legs only (24 phase sims) via heavy_slot, one job at a time; everything else
reused bit-exactly. pytest 6/6.

LABELS (pre-registered): C2's dev years nearly clean (Chronos-Bolt 2024-11, mostly
non-crypto + synthetic -> LESS risk than Kronos, but dev still possibly-contaminated ->
UPPER BOUND with a small caveat); B7 contaminated (oc_cascadeboost idea formed after
oc_cascadedelay's replica had covered all five years incl. the post-release year;
oc_cboostctrl: ~70% of B7's gain is plain extra exposure, timing keeps ~26-39%). The
post-release year (2025-09-24..2026-09-23) is a LABELLED DIAGNOSTIC for EVERY row that
contains C2 or B7 (all rows except L00/L10 BOT-only, whose Y4 are v421/v422 reproductions
but still labelled as a re-score wherever S5 or carry applies). Selection NEVER uses Y4.
S5 y2021 SHORT (Bybit live 2021-11-15, labelled). Carry overlay is post-hoc (same five
years, needs prospective paper). Carry marks close-marked (DD lower bound).

STATUS: DONE. 10/16 BOT legs reused to the digit, 6 new engine legs (G2K20_S5, G2K20+C2_S5,
G2K20+B7 base+S5, G2K20+B7xC2 base+S5) via heavy_slot; 32 account rows (16 BOT f=0 + 16
carry f=0.25) + stationary bootstrap per row (10d blocks, 4000 draws, seed 0, as oc_c2carry).

## 0. Reproduction gates (PASS, to the digit — else STOP)

- G2 base (L00_bin) == v421 R2B1D17BFG2 (5.410/W 2.588/DD 16.91/full 16.82).
- G2K20 base (L10_bin) == v422 G2K20 (5.874/W 2.832/DD 17.79/full 17.69).
- C2 base/S5 (L01) == oc_chronos C2 / oc_c2bybit C2_S5; B7 base/S5 (L02) == oc_cascadeboost B7
  / oc_cboostbybit B7_S5 (S5 5.906/full 20.31); B7xC2 base/S5 (L03) == oc_b7c2 B7C2
  (base 6.318/full 16.91; S5 5.685/full 17.43); G2K20+C2 base (L11_bin) == oc_c2frontier
  (5.983/full 16.24); REF_S5 identical across K2/C2 files (same engine).
- f=0 carry short-circuit reproduces each BOT leg bit-exact; G2+carry f=0.25 reproduces
  oc_c2carry (Binance 5.634/16.66; Bybit S5 5.111/17.93) to the digit as a method check.
- reset_metric.year_reset cross-check on reused rows matches the hourly-grid year_pass.

## 1. BOT legs f=0 (method/reproduction table; 4-phase reset %/mo, yearly DD in brackets)

S5 y2021 SHORT (*). No losing year in any of the 16 BOT legs.

| leg | 2021 | 2022 | 2023 | 2024 | dev4 mean/W/DDmax | 5y R/W | full DD | worst marked episode | Y4 R/DD |
|---|---|---|---|---|---|---|---|---|---|
| L00 G2 bin | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601/2.588/16.91 | 5.410/2.588 | 16.82 | 2023-04-17->2023-06-14 16.82% | 4.648/12.90 |
| L01 G2+C2 bin | 2.711/11.52 | 3.460/15.48 | 6.250/15.07 | 10.721/8.29 | 5.739/2.711/15.48 | 5.542/2.711 | 15.42 | 2023-04-17->2023-06-14 15.42% | 4.754/12.86 diag |
| L02 G2+B7 bin | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738/2.955/17.92 | 6.364/2.955 | 17.75 | 2023-04-17->2023-06-14 17.75% | 4.880/13.81 diag |
| L03 G2+B7xC2 bin | 2.922/15.45 | 3.573/17.05 | 7.795/16.27 | 12.598/11.04 | 6.652/2.922/17.05 | 6.318/2.922 | 16.91 | 2023-04-17->2023-06-14 16.91% | 4.990/14.17 diag |
| L10 G2K20 bin | 2.832/12.01 | 3.272/17.79 | 7.149/15.79 | 11.644/9.34 | 6.166/2.832/17.79 | 5.874/2.832 | 17.69 | 2023-04-17->2023-06-14 17.69% | 4.716/13.65 |
| L11 G2K20+C2 bin | 2.982/13.26 | 3.601/16.40 | 7.029/15.87 | 11.710/9.37 | 6.275/2.982/16.40 | 5.983/2.982 | 16.24 | 2023-04-17->2023-06-14 16.24% | 4.826/13.73 diag |
| L12 G2K20+B7 bin | 2.938/15.63 | 3.009/18.81 | 9.519/15.55 | 13.441/13.13 | 7.199/2.938/18.81 | 6.710/2.938 | 18.67 | 2023-04-17->2023-06-14 18.67% | 4.774/14.86 diag |
| L13 G2K20+B7xC2 bin | 3.168/14.55 | 3.355/17.41 | 8.245/16.45 | 13.424/13.24 | 7.149/3.168/17.41 | 6.669/3.168 | 17.19 | 2023-04-17->2023-06-14 17.19% | 4.770/15.23 diag |
| L00 G2 by | 2.129/12.36* | 2.735/18.11 | 4.932/16.89 | 10.377/9.22 | 4.994/2.129/18.11 | 4.883/2.129 | 18.09 | 2023-04-17->2023-06-14 18.09% | 4.443/12.37 |
| L01 G2+C2 by | 2.213/12.21* | 3.062/16.50 | 5.415/16.65 | 10.527/9.27 | 5.255/2.213/16.65 | 5.115/2.213 | 16.50 | 2023-04-17->2023-06-14 16.50% | 4.558/12.22 diag |
| L02 G2+B7 by | 2.200/15.07* | 2.457/19.08 | 8.368/15.98 | 12.172/12.54 | 6.217/2.200/19.08 | 5.906/2.200 | 20.31 | 2023-04-17->2023-10-02 20.31% | 4.670/13.43 diag |
| L03 G2+B7xC2 by | 2.253/15.77* | 3.064/17.56 | 6.503/17.02 | 12.243/12.58 | 5.944/2.253/17.56 | 5.685/2.253 | 17.43 | 2023-04-17->2023-06-14 17.43% | 4.657/13.88 diag |
| L10 G2K20 by | 2.338/13.52* | 2.753/18.76 | 6.550/16.48 | 11.726/10.40 | 5.555/2.338/18.76 | 5.342/2.338 | 19.61 | 2023-04-17->2023-10-02 19.61% | 4.494/13.27 |
| L11 G2K20+C2 by | 2.347/14.70* | 3.133/17.96 | 6.119/17.07 | 11.812/10.45 | 5.567/2.347/17.96 | 5.367/2.347 | 17.93 | 2023-04-17->2023-06-14 17.93% | 4.570/13.22 diag |
| L12 G2K20+B7 by | 1.792/17.76* | 1.867/21.57 | 9.519/15.55 | 13.441/13.13 | 6.482/1.792/21.57 | 6.124/1.792 | 24.28 | 2023-04-17->2023-10-02 24.28% | 4.706/14.86 diag |
| L13 G2K20+B7xC2 by | 2.072/16.85* | 2.145/18.74 | 8.245/16.45 | 13.424/13.24 | 6.220/2.072/18.74 | 5.922/2.072 | 18.95 | 2023-04-17->2023-06-14 18.95% | 4.737/15.05 diag |

BOT-only Bybit side ranking (dev4, DD<=20, no losing year; mean>=5 then highest W): L11
(5.567/2.347) beats L10 (5.555/2.338) and L03 (5.944/2.253); L02 is ineligible (full 20.31).

## 2. Deployable frontier: the same 16 legs WITH quarterly carry f=0.25 (ONE-account)

| leg+carry (Bybit = deployable) | dev4 years R/DD | dev4 mean/W/DDmax | 5y R/W | full DD | worst marked episode | Y4 R/DD (DIAG) | bootstrap med/P(m>=5%)/P(DD>20%)/P(lose) |
|---|---|---|---|---|---|---|---|
| L00 G2 by+c | 2.321/12.36*, 2.808/17.95, 5.484/16.67, 10.656/9.15 | 5.266/2.321/17.95 | 5.111/2.321 | 17.93 | 2023-04-17->2023-06-14 17.93% | 4.493/12.13 | 5.231/53.30/11.18/0.75 |
| L01 G2+C2 by+c | 2.405/12.17*, 3.135/16.35, 5.965/16.52, 10.806/9.20 | 5.527/2.405/16.52 | 5.342/2.405 | 16.35 | 2023-04-17->2023-06-14 16.35% | 4.607/12.09 | 5.421/56.00/10.60/0.70 |
| L02 G2+B7 by+c | 2.391/15.03*, 2.531/18.93, 8.904/15.77, 12.447/12.48 | 6.482/2.391/18.93 | 6.127/2.391 | 19.72 | 2023-04-17->2023-10-02 19.72% | 4.719/13.31 | 6.077/64.80/15.68/0.60 |
| L03 G2+B7xC2 by+c | 2.445/15.73*, 3.137/17.41, 7.047/16.81, 12.518/12.52 | 6.212/2.445/17.41 | 5.910/2.445 | 17.28 | 2023-04-17->2023-06-14 17.28% | 4.707/13.76 | 5.868/63.10/16.48/0.68 |
| L10 G2K20 by+c | 2.529/12.83*, 2.753/18.60, 6.550/16.48, 11.726/10.40 | 5.825/2.529/18.60 | 5.567/2.529 | 19.02 | 2023-04-17->2023-10-02 19.02% | 4.544/13.04 | 5.576/58.83/14.52/0.78 |
| L11 G2K20+C2 by+c | 2.539/13.95*, 3.133/17.80, 6.119/17.07, 11.812/10.45 | 5.838/2.539/17.80 | 5.593/2.539 | 17.78 | 2023-04-17->2023-06-14 17.78% | 4.619/13.05 | 5.663/60.00/14.00/0.60 |
| L12 G2K20+B7 by+c | 2.590/16.08*, 1.867/20.88, 9.519/15.55, 13.441/13.13 | 6.745/1.867/20.88 | 6.345/1.867 | 23.72 | 2023-04-17->2023-10-02 23.72% | 4.756/14.36 | 6.208/66.07/21.65/0.92 |
| L13 G2K20+B7xC2 by+c | 2.525/16.85*, 2.145/18.59, 8.245/16.45, 13.424/13.24 | 6.485/2.145/18.59 | 6.144/2.145 | 18.48 | 2023-04-17->2023-06-14 18.48% | 4.787/14.85 | 5.853/61.85/21.85/0.75 |

Binance with carry (same method; venue-independent carry MtM; for the record): G2 5.634/16.66
Y4 4.698; G2+C2 5.766/15.27 Y4 4.804; G2+B7 6.584/17.60 Y4 4.930; G2+B7xC2 6.540/16.75 Y4
5.040; G2K20 6.097/17.54 Y4 4.766; G2K20+C2 6.206/16.09 Y4 4.876; G2K20+B7 6.928/18.52 Y4
4.824; G2K20+B7xC2 6.888/17.04 Y4 4.820. No losing year anywhere (BOT or carry, either venue).

Robust pick on dev4 ON BYBIT WITH CARRY (pre-registered: full-path DD<=20, no losing dev
year; prefer mean>=5, then highest WORST, ties->mean): eligible L00, L01, L02, L03, L10,
L11, L13 (L12 full 23.72 ineligible, also dev DDmax 20.88). All means >= 5. Highest WORST:
L11 2.539 > L10 2.529 > L03 2.445 > L02 2.391 > L01 2.405?? order: L11 (2.539) top, then L10
(2.529), L03 (2.445), L01 (2.405), L02 (2.391), L00 (2.321), L13 (2.145). PICK: L11 =
G2K20+C2 on Bybit with carry (dev4 5.838/W 2.539/DDmax 17.80; 5y 5.593; full 17.78).

## 3. Plain table of (5y %/mo, full-path DD %) for all 16 carry points (f=0.25)

| kd \ overlay | none (bin/by) | C2 (bin/by) | B7 (bin/by) | B7xC2 (bin/by) |
|---|---|---|---|---|
| 1.7 (G2) | (5.634, 16.66) / (5.111, 17.93) | (5.766, 15.27) / (5.342, 16.35) | (6.584, 17.60) / (6.127, 19.72) | (6.540, 16.75) / (5.910, 17.28) |
| 2.0 (G2K20) | (6.097, 17.54) / (5.567, 19.02) | (6.206, 16.09) / (5.593, 17.78) | (6.928, 18.52) / (6.345, 23.72) | (6.888, 17.04) / (6.144, 18.48) |

(BOT f=0 side table for the method check: Binance 5.410/16.82, 5.542/15.42, 6.364/17.75,
6.318/16.91, 5.874/17.69, 5.983/16.24, 6.710/18.67, 6.669/17.19; Bybit 4.883/18.09,
5.115/16.50, 5.906/20.31, 5.685/17.43, 5.342/19.61, 5.367/17.93, 6.124/24.28, 5.922/18.95.)

Reading the frontier on Bybit with carry: every row clears 5y >= 5 (lowest 5.111 G2); DD<=20
holds for all except L12 (23.72). Highest 5y is L12 6.345 but it breaches DD; among DD<=20
the highest 5y is L02 (G2+B7) 6.127, then L13 (G2K20+B7xC2) 6.144?? numerically L13 6.144 >
L02 6.127 — the 5y-best eligible is L13, while the dev4-robust pick is L11 (2.539 worst-year).
The robust rule deliberately prefers worst-year over mean (dev-mean gains did not transfer
in v189-v197): L11's dev4 WORST 2.539 beats L13's 2.145 and L02's 2.391.

Most-recent-year answer (labelled diagnostic): on Bybit with carry NO row reaches >= 5 %/mo
(best L13 4.787, then L12 4.756, L02 4.719; G2 4.493, G2+C2 4.607, G2K20+C2 4.619). On Binance
with carry only L03 touches 5.040. So the assignment's second question is NO.

## 4. Leakage / causality checks (how verified)

- Feature timing: C2 forecast for bar open T uses ONLY the 512 closes ending at the bar
  closing at T on that shift's grid (inherited Part A); B7 triggers use closes with
  close_time <= tc only (SIG window excludes the tested bar; boost window strictly after tc
  0 < T-tc <= 7d); stack lookup uses only (sym,shift,T) at the holding bar.
  `test_truncation_causal_on_frozen_tables` recomputes stack mults from truncated frozen
  boost+Chronos tables -> identical on kept prefix; multisets asserted
  (C2 {0.75,1.0,1.25}, B7 {1.0,1.5}, stack {0.75,1.0,1.125,1.25,1.5,1.875}).
  Engine exact (shift,T) match with causal ffill fallback (latest grid time <= T).
- Label windows: no labels fit anywhere in this study (no harness join).
- Fit windows: no refit; threshold 4.0, windows 540/120, boost 1.5, N=7, kd 1.7/2.0, G 2.0,
  carry threshold 0.04/f 0.25 all frozen ex-ante, never scanned; no statistic from any test
  year feeds any choice (S5 = price-source switch, carry = account switch, not fits). Year y
  uses anchor-y C2 fit only (shift-0 + 7d embargo inherited); B7 triggers strictly causal.
- Fill timing: win_start=5 asserted in test (S5 live0 2021-11-15 + Bybit dir in source);
  engine fills only on 1m trade-through with stop-first (inherited harness); carry MtM uses
  last CLOSED hourly bar strictly before t; bootstrap uses daily causal ffill, no 1m peeking.
- Gate costs inside the engine (maker 0.0002/taker 0.00055/longs pay 0.0001 per 8h; carry
  fees spot 0.001/side + fut 0.00055/0.0002 frozen). Coverage: no skipped anchor year;
  missing boost -> 1.0, missing ch_q10 -> 1.0 (new engine miss_c2 = 0 on all 24 phase sims).
- Tests: `tests/test_oc_levfrontier.py` 6/6 pass
  (`.venv/Scripts/python.exe -m pytest tests/test_oc_levfrontier.py -q`).

## 5. What failed / caveats

- The high-exposure B7 rows fail the DD gate on Bybit: G2K20+B7 (L12) full-path DD 23.72
  with carry (24.28 without; dev yearly DDmax 20.88/21.57) — kd 2.0 x B7 boost sizes into the
  2023 leg (worst episode 2023-04-17->2023-10-02). G2+B7 (L02) passes but only just
  (19.72 with carry; 20.31 without — carry's +0.22 5y is what pulls it under 20).
- The 5y-best eligible (L13 6.144, L02 6.127) is NOT the robust pick (L11 5.593): the robust
  criterion pays ~0.55pp 5y mean for +0.15-0.39pp worst-year (L11 W 2.539 vs L02 2.391 vs L13
  2.145 on Bybit-carry dev4). That is the pre-registered tradeoff, not a post-hoc choice.
- C2 dev edges are UPPER BOUNDS (small caveat) and B7 edges are contaminated + ~70%
  exposure (oc_cboostctrl); the carry overlay is post-hoc on the same five years. The clean
  recent year clears 5% NOWHERE on Bybit (best 4.787). Bootstrap P(DD>20% in a year) is
  14.0% for the pick L11, 15.7% for L02, 21.9% for L13 — the frontier's return comes with
  real yearly-DD risk even where full-path DD <= 20.
- S5 y2021 SHORT; carry marks close-marked (DD lower bound); bootstrap assumes ~stationary
  daily returns with ~10-day dependence (no annual regime structure).

## Tom tat 5 dong cho chu tai khoan (Bybit + carry f=0,25)

1. Tren gia Bybit kem carry: G2 5,11%/thang (DD 17,93), G2+C2 5,34 (16,35), G2+B7 6,13 (19,72),
   G2+B7xC2 5,91 (17,28), G2K20 5,57 (19,02), G2K20+C2 5,59 (17,78), G2K20+B7 6,35 NHUNG DD
   23,72 (vo DD), G2K20+B7xC2 6,14 (18,48).
2. Pick robust dev4 tren Bybit+carry la G2K20+C2 (L11): dev4 5,84, WORST 2,54 (cao nhat),
   5y 5,59, full DD 17,78, nam gan nhat (diagnostic) 4,62 < 5.
3. Return 5y cao nhat ma DD<=20 la G2+B7 (6,13, DD 19,72) va G2K20+B7xC2 (6,14, DD 18,48),
   nhung worst-year dev4 cua chung (2,39 / 2,15) thua pick (2,54).
4. Nam gan nhat KHONG hang nao dat cong 5% tren Bybit (cao nhat 4,79 G2K20+B7xC2;
   pick chi 4,62; G2+B7 4,72) — cau hoi thu hai tra loi KHONG.
5. Ky vong that (bootstrap pick): trung vi 5,66%/thang, P(thang>=5%) 60%, P(DD>20%/nam) 14%,
   P(nam lo) 0,6%; B7/C2/carry deu can paper prospective, khong adopt von that.

## Vietnamese verdict (3 lines)

- Pick deployable duy nhat theo luat robust tren Bybit+carry la G2K20+C2 (5,59%/thang 5y, DD 17,78, worst-year dev4 2,54 cao nhat), nhung nam sach gan nhat chi 4,62 (duoi cong 5%) nen khong adopt.
- Cac hang return 5y cao hon (G2+B7 6,13, G2K20+B7xC2 6,14) deu thua pick ve worst-year va deu duoi 5% o nam sach (4,72 / 4,79), con G2K20+B7 (6,35) vo DD 23,72 — khong co hang nao dat ca hai.
- Ket luan: needs prospective evidence — giu pick va frontier trong paper runner hien tai, khong trien khai that.
