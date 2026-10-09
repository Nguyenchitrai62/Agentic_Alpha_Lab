# oc_bybitgap REPORT — where exactly does G2 lose ~0.5-0.6 %/month on Bybit prices?

DESCRIPTIVE ONLY (no rule change; fixes described-not-run for the leader).
PLAN.md pre-registered before any new computation. Engine-adjacent 1m scan ran via
heavy_slot (`oc_bybitgap_diag`, 0.8 min, per-coin streaming). No new 4-phase engine
replay: G2/G2_S5 already reproduce to the digit in oc_amihudrobust + oc_amihudbybit
with the identical v426 harness; a third replay adds no information (logged choice).

## 0. Reproduction gate (PASS, to the digit)

oc_amihudrobust/engine_results.json + v421_result.json assert OK in-script:
G2 dev4 5.601 / W 2.588 / DD 16.91; 5y 5.410 / full-DD 16.82;
G2_S5 dev4 4.994 / W 2.129 / DD 18.11; 5y 4.883 / full-DD 18.09;
v421 cached 5.41 / 16.91 / 16.82.

| dev year | G2 R/DD | G2_S5 R/DD | gap (G2-G2_S5) |
|---|---|---|---|
| 2021-22* | 2.588/10.86 | 2.129/12.36 | **0.459** |
| 2022-23 | 3.282/16.91 | 2.735/18.11 | **0.547** |
| 2023-24 | 6.045/15.81 | 4.932/16.89 | **1.113** |
| 2024-25 | 10.677/8.27 | 10.377/9.22 | **0.300** |
| dev4 mean | 5.601 | 4.994 | **0.607** |
| 5y labelled | 5.410/16.82 | 4.883/18.09 | **0.527** |
| Y4 labelled (2025-26) | 4.648/12.90 | 4.443/12.37 | **0.205** |

\* 2021 S5 is a short window from 2021-11-15 (labelled). Gap concentrates in
2023-24 (1.11pp, ~2x any other dev year); 2024-25 contributes least (0.30pp).
Full-path DD widens on Bybit (18.09 vs 16.82, +1.27pp).

## 1. Book vs dip leg (quoted read-only, single-phase R2B1D17BF diagnostic — NOT the 4-phase gate)

From research/diagnostics/oc_bookvenue/results.json (hybrids size on Binance opens,
so book_byb-base = pure book execution, book_bin-base = pure dip execution):

| phase | base | s5 | gap | book eff | dip eff | residual |
|---|---|---|---|---|---|---|
| s=0 full-window | 7.054 | 6.781 | -0.273 | +0.005 (-2%) | -0.153 (56%) | -0.125 |
| s=2 full-window | 5.620 | 4.972 | -0.648 | -0.100 (15%) | -0.484 (75%) | -0.064 |

Per-year s5-base / book-eff / dip-eff (%/month):
s0: 2021 -0.504/-0.001/-0.530; 2022 -0.356/-0.021/+0.201; 2023 +0.128/-0.118/+0.363;
2024 -0.355/-0.132/-0.271; 2025 -0.296/+0.282/-0.574.
s2: 2021 -0.917/-0.169/-0.801; 2022 -1.100/+0.072/-1.147; 2023 -0.759/-0.067/-0.456;
2024 -0.039/-0.281/+0.253; 2025 -0.416/-0.079/-0.251.
Book eff never exceeds |-0.28| in any coin-year cell (bnbvenue §4 quote); per-year
book eff flips sign (s0 2025 even +0.282). The gap rides the DIP ladder + a
sizing/interaction residual (Bybit-open vol-target/governor + book/dip interaction),
not book execution. Caveat: single-phase R2B1D17BF (no G-governor 2.0 mix), so yearly
splits are directional, not 4-phase-additive.

## 2. Per coin (B1 replica rung-y sums are NOT %/month; deployment per-coin book split does not exist)

oc_venuegap per_coin_year gaps (bin-byb rung-y): 5y XRP +0.553 ≈ entire +0.516 net;
BNB +0.348; SOL -0.277; ETH -0.069; BTC -0.038. Yearly: XRP positive 4/5y, but no coin
is same-sign-large every year (2024 XRP flips -0.172 while BNB +0.110; 2022 SOL -0.143
vs XRP +0.248). Whole B1 5y gap = 3.6% of Bybit rung P&L — the static ladder is
almost venue-insensitive. Deployment dip shortfall (-34/-59 TPs, §3) does NOT
reproduce in B1 (Bybit even holds MORE solo TPs 79 vs 57, oc_bybittp) — it needs the
deployment dips (kd 1.7 corr sizing, risk budget, learned R2 sizes/TPs, venue-open
timeouts). oc_bookvenue publishes no per-coin book table (bnbvenue §4: UNKNOWN, not
imputed); only BNB book number is the spread bound §3 + venue-open shift -3.59 bps,
which does not convert into P&L in B1. BNB deployment weight (oc_contrib via
bnbvenue §5, additive mix%): +4.16/-0.02/+5.43/+12.06/+17.71 per year, pooled +39.33
(13.7%); removing BNB cannot fix a diffuse 0.5-0.6 drag (see §5c).

## 3. Per component (quoted + bounded)

- Entry fills MISSED/EXTRA: book fills Bybit-minus-Binance +2 (s0: 1293->1295,
  fill rate 30.27->30.48%) and +14 (s2: 1253->1267, 29.91->30.26%). Bybit fills
  slightly MORE. Dip fills -25 (s0: 5301->5276) / -57 (s2: 4971->4914).
- Exit prices: matched limit/fill diffs <1 bp median (s0 limits -0.66/-0.13 mean/med,
  fills -0.47/-0.09; s2 -0.66/-0.14, -0.65/-0.09); stops medians <=0.5 bps
  (s0 +1.66/-0.45, s2 -2.05/-0.49); TPs outlier-driven means, medians <=0.3 bps.
  No systematic stop/TP slippage. Stops differ by <=5, TPs by <=1 on ~1300 book fills.
- Dip exits carry the gap: TPs -34 (2761->2727, rate 52.08->51.69%) / -59
  (2476->2417, 49.81->49.19%); stops +6 (168->174) / +11 (197->208); timeouts
  +3/-9. TP-rate -0.4/-0.6pp.
- Funding: adverse longs-only 0.0001/8h; venue funding diff comes ONLY from divergent
  position paths. Bound: fills/exits near-identical on books, so extra Bybit long
  carry << 10% of window notional -> <<0.1 %/month (order 0.01-0.05 even under a
  hostile 10%-extra-long assumption: 0.1*0.0001*3*365/12 ≈ 0.09). Negligible.
- Vol-scale (NEW, this study): venue-native 4h-open rolling-360 sigma ratio
  byb/bin median 0.9994-1.0013 (BTC 1.0012, ETH 1.0013, SOL 1.0012, BNB 1.0013,
  XRP 0.9994); p50 |ratio-1| 0.0016-0.0025. Implied rung shift k*dsigma ≈ 0.5 bps
  — nothing to fix.
- Governor: g is equity-drawdown-driven (no separate fit); hybrids hold sizing to
  Binance opens, so sizing divergence lives in the residual (-0.125/-0.064),
  not in a fittable parameter.

## 4. Price-series diagnostics per coin (NEW, overlap [2021-11-15, 2026-09-23), 2.55M min/coin)

| coin | close basis med / p95\|.\| / mean\|.\| | minute-low diff med / p95 | wick-depth diff med / p95 | 4h-open med / mean\|.\| |
|---|---|---|---|---|
| BTC | +0.04 / 4.69 / 1.52 | +0.20 / 5.04 | 0.00 / 2.47 | +0.01 / 1.53 |
| ETH | -0.17 / 4.68 / 1.52 | -0.04 / 4.85 | -0.00 / 2.77 | -0.17 / 1.52 |
| SOL | +0.36 / 6.37 / 2.47 | +0.70 / 6.81 | 0.00 / 4.47 | +0.32 / 2.42 |
| BNB | -3.63 / 12.19 / 5.16 | -3.07 / 12.06 | -0.17 / 4.00 | -3.59 / 5.16 |
| XRP | 0.00 / 6.35 / 2.15 | +0.63 / 6.98 | 0.00 / 4.26 | 0.00 / 2.18 |

Only BNB has a level shift (median -3.6 bps, p95 12.2); all other coins 0-0.7 bps
median, p95 4.7-7.0. Wick-depth diffs centre on 0 (medians 0-0.17 bps). Cross-checks
match oc_venuegap/oc_bookvenue to ~0.03 bps.

Trade-through agreement (venue-native levels, strict low<lv, live 16..238m; NEW code,
rung rows reproduce oc_venuegap pair_counts exactly, e.g. BTC k2.5 430/9/13/10192):

| level | BTC bin→byb / byb→bin | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| book limit | .986/.989 (107/81 single) | .990/.990 (72/78) | .992/.991 (66/69) | .982/.986 (135/104) | .990/.991 (76/70) |
| k2.5 | .959/.981 (9/13) | .985/.972 (7/13) | .961/.969 (16/12) | .976/.976 (9/11) | .969/.969 (12/14) |
| k3.0 | .959/.981 (11/5) | .955/.979 (13/6) | .962/.962 (9/9) | .964/.977 (11/7) | .976/.973 (7/8) |
| k3.5/4.0/5.0 | same pattern, singles <=13 per cell, neither dominates (97-99% of bars) | | | | |

P(byb fill | bin fill) 95-99%, P(bin | byb) 96-99% at every coin x level; book singles
are 1-2% of book fills (BNB highest at 135/104 but symmetric). No coin or level
concentrates the mismatch: fill disagreement is rare, symmetric, and diffuse.

## 5. Leakage / causality checks (how verified)

- Feature timing: levels use O(T) + trailing sigma (minutes strictly before T+16);
  fills use minutes 16..238 only; basis/wick are contemporaneous minute comparisons
  (no prediction, no fits, no thresholds tuned on any year). No statistic from any
  test year feeds any choice (descriptive study, no variant).
- Label windows: none fitted (realised 1m path only).
- Fit windows: none (sigma is trailing rolling-360/min-120/shift-1; XS/sizing quoted
  from frozen studies).
- Fill timing: strict `low < lv` + live-start-16 asserted in tests (stricter than the
  gate win_start=5, so agreement rates are conservative); stop-first/funding quoted
  from the frozen harness. `tests/test_oc_bybitgap.py` passes (see below).

## 6. Described — do not run — pre-registrable venue fixes (for the leader)

(a) Route XRP dip rungs to Binance: B1 XRP gap +0.553 ≈ whole B1 net, but that is
~4% of rung P&L and the deployment gap rides sizing-amplified TP shortfalls, not B1
levels — expected recovery << gap. (b) Exclude BNB on Bybit (10x spread): spread cost
is maker-side (~1.1 bps/side bound, <0.02 %/month on ~20% BNB book share) while BNB
carries +39.33 additive mix% (largest 2025 contributor); removal loses ~14% of P&L
and barely moves gate DD (BNB owns 1/5 DD windows). (c) Tighter Bybit TPs / wider rung
offsets: oc_bybittp exact replay — 5bps-inside recovers only 18/57 (32%) divergent TPs
at 5.1 bps shave per kept TP and manufactures ~6x more new Binance TPs (105); not a
venue fix. (d) Venue-specific vol-scale: sigma ratio ~1.00 everywhere — no fix exists.
Recommendation: no venue fix pre-registered from this evidence; gap is diffuse and
needs deployment-level (sizing/timeout) work, if anything.

## Post-hoc log

- No definition changed after outcomes (PLAN frozen; one pre-outcome code fix only:
  sigma-dict paren typo before the heavy_slot launch). Rung rows reproduce
  oc_venuegap pair_counts exactly (independent code path). 2021 S5 short-window and
  single-phase-vs-4-phase labels kept throughout.

## Vietnamese verdict (3 lines)

- Gap G2−G2_S5 dev4 0.61 (đỉnh 2023 1.11, các năm khác 0.30–0.55; 5y 0.53, năm gần
  nhất 0.21, DD full-path 16.82→18.09): book khớp lệnh gần như giống hệt (fill Bybit
  còn nhiều hơn +2/+14, giá khớp median <1bp), dip ladder gánh gap (ít fill hơn
  −25/−57, thiếu −34/−59 TP, thêm stop, TP-rate −0.4/−0.6pp) cộng phần dư sizing/tương
  tác, còn B1 replica chỉ lệch 3.6% rung P&L nên không giải thích được drag.
- Không coin/mức nào gom gap: basis chỉ BNB lệch −3.6bp (còn lại ≤0.7bp), wick diff
  ~0, sigma Bybit/Binance ~1.00, P(fill chéo) 95–99% mọi coin×rung (single-venue chỉ
  1–2%, đối xứng); XRP gánh toàn bộ gap B1 (+0.55/+0.52) nhưng đó là ~4% rung P&L,
  còn BNB spread ~10x chỉ bound ~1bp/fill trong khi BNB lãi +39.33 mix% — đều không
  phải chỗ mất 0.5–0.6%/tháng.
- Không pre-register fix venue nào từ bằng chứng này (route XRP, loại BNB, TP sâu
  hơn/wider rung, vol-scale riêng đều đã có số liệu bác bỏ — oc_bybittp thu 32% với
  giá shave 5.1bp và đẻ thêm TP Binance gấp 6x); gap phân tán, khuếch đại qua sizing
  deployment (kd1.7 corr, risk budget, R2 sizes/TPs, venue-open timeouts) — cần
  prospective ngoài mẫu nếu leader muốn theo tiếp.
