# oc_amihudrobust REPORT — is the Amihud A1 book tilt real?

Frozen A1 (oc_lit_xs, copied not edited): book weights x (1 + 0.25 z),
z = cross-sectional z (across 5 majors at same bar) of trailing-30d Amihud
(|daily return| / daily quote volume), both legs, clip [0.5,1.5], NaN->1,
v426 slot (STANDARD rows after bear filter, before shifted-clock ffill;
rows before 2021-09-24 untilted). Given: dev4 5.844 / worst 2.798 / DD 16.81
vs G2 5.601 / 2.588 / 16.91; Y4 4.750/11.14 vs 4.648/12.90. 1 of ~20 screened
today -> multiple-testing risk. All rows below are ROBUSTNESS of frozen A1
(no re-selection); dev4 + 5-year path reported.
PLAN.md written BEFORE any engine run; one pre-outcome harness fix logged below.
Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h, shorts nothing;
limits fill only on 1m trade-through, no fill first 5 min (base), stop-first.
Engine via heavy_slot (Pool 2); G2/A1 reproduced to the digit first.

## 0. Reproduction gate (PASS, to the digit)

Cached `v421_runs.pkl` asserts 5.41 / W 2.588 / DD 16.91 / full 16.82 in-script.
Engine re-ran G2 AND A1 bit-exact vs oc_lit_xs `engine_results.json`:

| row | 2021 R/DD | 2022 R/DD | 2023 R/DD | 2024 R/DD | 2025(Y4) R/DD | 5y R/W/DD/full | dev4 R/W/DD |
|---|---|---|---|---|---|---|---|
| G2 | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 4.648/12.90 | 5.410/2.588/16.91/16.82 | 5.601/2.588/16.91 |
| A1 | 2.798/12.21 | 3.395/16.81 | 6.390/15.77 | 10.987/8.42 | 4.750/11.14 | 5.624/2.798/16.81/16.66 | 5.844/2.798/16.81 |

G2_S1..S5 also reproduce `v421_audit/ROBUST.md` to the digit
(S1 4.571/17.45, S2 5.212/16.91, S3 4.578/17.32, S4 4.898/17.31, S5 4.883/18.11),
so friction implementations are exactly the existing ones. Comparison valid.

## 1. Frictions on A1 and G2 (S1..S5 exactly as robust_v421.py)

S1 maker 0.0004/taker 0.0012 (globals patched+restored); S2 win 15/sleeve 16;
S3 win 30/sleeve 31; S4 stop_slip 0.5 (win 5); S5 Bybit 1m prices from
2021-11-15 (2021 = short window, labelled). 4-phase engine, per-year reset metric.

| scen | G2 dev4 R / A1 dev4 R / gap | G2 5y R / A1 5y R / gap | A1 DD dev4 / full |
|---|---|---|---|
| base | 5.601 / 5.844 / **+0.243** | 5.410 / 5.624 / **+0.214** | 16.81 / 16.66 |
| S1 | 4.740 / 4.839 / **+0.099** | 4.571 / 4.675 / **+0.104** | 17.90 / 17.81 |
| S2 | 5.391 / 5.626 / **+0.235** | 5.212 / 5.421 / **+0.209** | 16.91 / 16.75 |
| S3 | 4.628 / 4.787 / **+0.159** | 4.578 / 4.750 / **+0.172** | 17.70 / 17.61 |
| S4 | 4.992 / 5.163 / **+0.171** | 4.898 / 5.059 / **+0.161** | 17.14 / 16.99 |
| S5 | 4.994 / 4.989 / **-0.005** | 4.883 / 4.884 / **+0.001** | 18.58 / 21.32 |

Per-year S5 (dev4): G2 (2.129/2.735/4.932/10.377) vs A1 (2.145/2.316/4.934/10.789):
2022 is the leak (-0.42pp), others flat. A1_S5 full-path DD 21.32 (>20) vs
G2_S5 18.09 — under the alternate price source the tilt adds tail risk.
Sub-verdict: gap > 0 under base+S1..S4, essentially ZERO under S5
(dev4 -0.005pp, 5y +0.001pp) -> strict FAIL on "every friction".

## 2. Jitter on A1 only (one knob each, 4-phase engine)

| row | knob | dev4 R/W/DD | 5y R | Y4 R/DD | dev4 - G2 |
|---|---|---|---|---|---|
| J_K015 | K=0.15, W30/min20 | 5.766/2.583/16.75 | 5.537 | 4.625/11.44 | +0.165 |
| J_K035 | K=0.35, W30/min20 | 5.809/2.825/16.94 | 5.577 | 4.655/10.68 | +0.208 |
| J_W20 | K=0.25, W20/min13 | 5.685/2.783/17.47 | 5.497 | 4.748/11.05 | +0.084 |
| J_W45 | K=0.25, W45/min30 | 5.801/2.784/16.82 | 5.575 | 4.677/11.17 | +0.200 |

All 4 jitters beat G2 on dev4 (+0.08..+0.21) with no losing year and DD <= 17.47.
Frozen K=0.25/W30 (5.844) still beats all four jitters on dev4, so no
jitter-hacking claim; direction is insensitive to K in [0.15,0.35] and W in
[20,45]d. Sub-verdict: PASS (4/4 > G2).

## 3. Timing placebo (VECTORISED proxy, 500 draws — not 50 engine runs, stated)

50 engine runs x4 phases (~200 extra phase replays) exceed the compute budget,
so per the assignment fallback we ran the oc_bookattrib book-timing proxy
(bear-ffill books, next-bar open-to-open, cumprod per year, 4-phase mean of R;
gross timing, levels not comparable to the gated engine, only ordering).
Per year per coin, raw Amihud30 circular-shifted by {0,30,...,330}d (180-bar
multiples), XS z recomputed, A1 mult applied; seed 12345; 500 draws.
Proxy anchors: G2 dev4 3.522, A1 dev4 3.568 (gap +0.046 — same sign as engine
+0.243, smaller as expected for a gross proxy).
Placebo dev4 distribution: mean 3.488, sd 0.047, min 3.391, max 3.641;
A1 (3.568) percentile **93.0%**. Sub-verdict: PASS (>=90).

## 4. Static coin-tilt control (4-phase engine, 1 row)

Per (year, coin) CONSTANT = mean realised A1 mult over TRAIN=[Y-365d,Y-7d)
(7d embargo; realised-exposure only, no returns). 2021 TRAIN predates book
history -> 1.0 for all coins (no tilt, disclosed). Later TRAIN means show a
persistent slow tilt: BTC ~0.73-0.79, ETH ~0.76-0.81 (underweight),
BNB ~1.13-1.38, XRP ~1.07-1.23 (overweight), SOL mixed —
i.e. the "just overweight XRP/BNB?" hypothesis in plain numbers.
C_STATIC: dev4 5.201 (years 2.588/3.048/4.609/10.759, DD 17.45) vs A1 5.844:
gap **+0.643**; 5y 5.143 vs 5.624 (+0.481). The slow overweight alone LOSES to
G2 (5.201 < 5.601) while time-varying A1 wins, so A1 is not a slow coin bet.
Sub-verdict: PASS (beats static control).

## 5. Per-coin decomposition of A1's gain vs G2 (same vectorised proxy)

Per-coin yearly R (proxy, 4-phase mean) and A1-G2 gain in pp:

| year | BTC g | ETH g | SOL g | BNB g | XRP g |
|---|---|---|---|---|---|
| 2021 | -0.205 | -0.047 | -0.007 | +0.193 | +0.092 |
| 2022 | -0.172 | -0.037 | +0.098 | -0.024 | +0.030 |
| 2023 | -0.345 | -0.228 | -0.005 | +0.292 | +0.070 |
| 2024 | -0.214 | -0.095 | -0.007 | +0.341 | +0.443 |
| 2025 | -0.142 | -0.153 | -0.030 | +0.373 | +0.081 |

Dev4 mean yearly gain per coin: BTC -0.234, ETH -0.102, SOL +0.020,
BNB +0.201, XRP +0.159 (sums to proxy dev4 gap +0.046). The A1 edge is a
BNB+XRP timing tilt funded by BTC/ETH underweight — consistent every year for
BTC (negative) and BNB/XRP (net positive); 2022 is the weakest year for the
tilt (matches engine: smallest A1-G2 gap in 2022 on both base and S5).
Not a pure XRP story: BNB contributes more than XRP on dev4.

## Leakage / causality checks (how verified)

- Feature timing: `D+1 00:00<=T`; `test_signal_truncation_causal` recomputes
  Amihud30 at D0 from data truncated to <=D0 (matches 1e-12), checks the +-1s
  boundary exposes exactly the prior day, and sampled-T truncation leaves
  multipliers unchanged (`amihud_signal` matches `xs_signal` A1 to 0.0 on
  sampled T); `test_handchecked_synthetic` checks z/clip/K maths.
- Label windows: none fitted (engine realised 1m path; proxy realised next-bar opens).
- Fit windows: no fits; XS mean/std at same T only; K/windows/clip/placebo
  offsets/static TRAIN fixed in PLAN.
- Fill timing: engine `win_start`/`sleeve_start`/`stop_slip` per friction +
  1m trade-through + stop-first (v426 harness; G2+A1+G2_S1..S5 bit-exact vs
  published audits). `tests/test_oc_amihudrobust.py` passes (2 tests).

## Post-hoc log

- First engine run used freshly `_load`ed hist/v221 modules per friction without
  setting `hist.R2_TABLE` (dip-agent table stayed default): G2 came out
  5.289 (not 5.41), A1 5.449 (not 5.624). Those numbers were DISCARDED as a
  harness bug (no economic change to signal/PLAN), fixed to reuse the worker's
  modules (same R2_TABLE/shift as oc_lit_xs), cache deleted, full re-run gave
  the to-the-digit reproduction above. No PLAN definition changed.
- No threshold/multiplier/window changed after outcomes. Jitter mins stayed
  PLAN-fixed (20->13, 45->30). Placebo used the pre-registered proxy path.

## Vietnamese verdict (3 lines)

- A1 giữ được lợi thế trước G2 dưới base và S1–S4 (dev4 +0.10 tới +0.24, 5y cùng dấu), cả 4 jitter đều hơn G2, placebo đạt phân vị 93.0% và hơn control tĩnh +0.64, nhưng dưới giá Bybit S5 chênh lệch về 0 (dev4 −0.005, 5y +0.001) kèm DD full-path 21.32 nên theo tiêu chí nghiêm ngặt là KHÔNG robust.
- Phân rã theo coin cho thấy edge đến từ tilt động nghiêng về BNB/XRP (chứ không phải overweight tĩnh — control tĩnh thua cả G2), funded bởi underweight BTC/ETH; hiệu ứng nhỏ (+0.24 dev4, +0.10 năm gần nhất trong nghiên cứu gốc) và từng là 1-trong-~20 biến thể nên rủi ro multiple-testing vẫn còn.
- Không nên đưa A1 vào G2 lúc này; nếu theo đuổi thì cần bằng chứng prospective ngoài mẫu và phải xử lý rủi ro S5/DD trước.
