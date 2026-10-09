# oc_c2bybit — REPORT (2026-10-08)

Question: does the Chronos C2 dip tilt keep its edge on BYBIT prices (S5) and
under the other frictions? Same check oc_k2bybit did for K2, now for C2
(risk = -ch_q10, x1.25/x0.75 outer quintiles, frozen oc_chronos fits.json).
PLAN.md was written BEFORE any outcome; no definition changed after outcomes.
Engine via heavy_slot (sequential shifts, heartbeat every 600 s). pytest 4/4.

STATUS: DONE. 12 engine rows (REF/C2 x base/S1/S2/S3/S4/S5, 4 phases each = 48
phase sims) + CPU scoring. Reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- Base REF == `v421_result.json` G2 (R2B1D17BFG2) all 5 years + 5y 5.410 +
  full-path DD 16.82.
- Base C2 == `oc_chronos` REPORT/results.json (dev 2.711/11.52, 3.460/15.48,
  6.250/15.07, 10.721/8.29; Y4 4.754/12.86; full-path DD 15.42).
- REF_S1..S5 == `v421_audit/ROBUST.md` G2 friction row to the digit
  (S1 4.571/17.45/17.37, S2 5.212/16.91/16.86, S3 4.578/17.32/17.24,
  S4 4.898/17.31/17.24, S5 4.883/18.11/18.09), so friction implementations are
  exactly the existing ones. Comparison valid.

## 1. Dev4 (anchors 2021..2024 — CONTAMINATION CAVEAT: Chronos-Bolt released 2024-11, mostly non-crypto + synthetic -> LESS risk than Kronos but dev still possibly-contaminated -> UPPER BOUND)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| fric | REF | C2 | gap dev4 |
|---|---|---|---|
| base | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 \| 5.601/2.588/16.91 | 2.711/11.52, 3.460/15.48, 6.250/15.07, 10.721/8.29 \| 5.739/2.711/15.48 | +0.138 |
| S1 | 1.975/11.18, 2.592/17.45, 4.853/16.01, 9.712/8.31 \| 4.740/1.975/17.45 | 2.108/11.98, 2.812/16.08, 4.846/15.27, 9.815/8.34 \| 4.853/2.108/16.08 | +0.113 |
| S2 | 2.513/11.09, 3.132/16.91, 5.624/15.82, 10.479/8.29 \| 5.391/2.513/16.91 | 2.655/11.46, 3.277/15.63, 5.965/15.11, 10.533/8.31 \| 5.562/2.655/15.63 | +0.171 |
| S3 | 2.070/11.85, 2.476/17.32, 4.346/16.03, 9.798/8.36 \| 4.628/2.070/17.32 | 2.141/12.33, 2.630/15.58, 4.683/15.25, 9.773/8.42 \| 4.764/2.141/15.58 | +0.136 |
| S4 | 2.363/11.06, 2.915/17.31, 4.422/17.08, 10.460/8.27 \| 4.992/2.363/17.31 | 2.560/12.24, 3.173/15.85, 4.822/16.35, 10.591/8.30 \| 5.240/2.560/16.35 | +0.248 |
| S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 \| 4.994/2.129/18.11 | 2.213/12.21, 3.062/16.50, 5.415/16.65, 10.527/9.27 \| 5.255/2.213/16.65 | +0.261 |

S5 y2021 is a SHORT window (Bybit from 2021-11-15, labelled). No losing dev year
in any row. C2 DD <= REF DD in 5/6 dev4 rows by maxDD (S4: 16.35 vs 17.31; S5:
16.65 vs 18.11 — lower too).

K2 side-by-side dev4 gaps (oc_k2bybit, read-only): base +0.171, S1 +0.158,
S2 +0.161, S3 +0.274, S4 +0.098, S5 +0.083. C2 trails K2 on base/S1/S3 but beats
K2 on S4 (+0.248 vs +0.098) and S5 (+0.261 vs +0.083).

## 2. Post-release year Y4 2025-09-24..2026-09-23 (clean BUT already scored once by oc_chronos for base — every Y4 number here is a labelled DIAGNOSTIC re-score under frictions)

| fric | REF R/DD | C2 R/DD | gap Y4 |
|---|---|---|---|
| base | 4.648/12.90 | 4.754/12.86 | +0.106 |
| S1 | 3.900/13.61 | 3.988/13.75 | +0.088 |
| S2 | 4.501/12.98 | 4.598/12.94 | +0.097 |
| S3 | 4.380/12.75 | 4.482/12.65 | +0.102 |
| S4 | 4.522/13.54 | 4.618/13.68 | +0.096 |
| S5 | 4.443/12.37 | 4.558/12.22 | +0.115 |

C2 beats REF in the clean year under every friction (diagnostic). K2 Y4 gaps for
reference: base +0.153, S1 +0.109, S2 +0.119, S3 +0.202, S4 +0.099, S5 +0.110 —
same sign, similar size.

## 3. Five-year path + full-path DD (v388.mix from 2021-09-24)

| fric | REF 5y R/W/DD/full | C2 5y R/W/DD/full | gap 5y |
|---|---|---|---|
| base | 5.410/2.588/16.91/16.82 | 5.542/2.711/15.48/15.42 | +0.132 |
| S1 | 4.571/1.975/17.45/17.37 | 4.679/2.108/16.08/15.99 | +0.108 |
| S2 | 5.212/2.513/16.91/16.86 | 5.369/2.655/15.63/15.56 | +0.157 |
| S3 | 4.578/2.070/17.32/17.24 | 4.707/2.141/15.58/15.54 | +0.129 |
| S4 | 4.898/2.363/17.31/17.24 | 5.115/2.560/16.35/15.77 | +0.217 |
| S5 | 4.883/2.129/18.11/18.09 | 5.115/2.213/16.65/16.50 | +0.232 |

All C2 full-path DDs <= 20 (worst 16.50 on S5) and below the matching REF
full-path DD in every friction. All-trade win rates move ≤ 0.002 (e.g. base Y4
C2 0.6276 vs REF 0.6267; S5 Y4 C2 0.6253 vs REF 0.6247) — the tilt is sizing,
not trade selection. K2 5y gaps for reference: base +0.167, S1 +0.149, S2 +0.153,
S3 +0.260, S4 +0.098, S5 +0.089; K2 full-path DDs 16.09/16.71/16.03/16.46/16.32/17.41.

## 4. Leakage / causality checks (how verified)

- Feature timing: Chronos forecast for bar open T uses ONLY the 512 closes ending
  at the bar closing at T on that shift's grid (inherited Part A); tilt reads
  only (coin, holding-bar T) ch_q10. `test_c2_truncation_causal_on_frozen_features`
  recomputes C2 multipliers from a truncated frozen feature table — identical
  on the kept prefix; multiset ⊂ {0.75, 1.0, 1.25}.
- Label windows: fits.json reused frozen (harness rows t_exit < A - 7d,
  shift-0 only); year y uses anchor-y fit only, never a later anchor.
- Fit windows: no refit here; S5 is a price-source switch, not a fit.
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in
  source; S5 live0 2021-11-15 + Bybit dir); engine fills only on 1m
  trade-through with stop-first (inherited harness).
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001
  per 8h; S1 stress maker 0.0004 / taker 0.0012).
- `tests/test_oc_c2bybit.py` 4/4 pass.

## 5. Post-hoc log

- No PLAN definition changed after outcomes. All 12 rows scored as
  pre-registered; reproduction gates passed to the digit (REF_base==v421 G2,
  C2_base==oc_chronos C2, REF_S1..S5==ROBUST.md G2).
- S1 TAKER = 0.0007 + 0.0005 = 0.0012 (same as robust_v421.py / oc_k2bybit).

## Vietnamese verdict (3 lines)

- C2 hơn REF ở mọi ma sát trên cả dev4 (+0.11 tới +0.26) và đường 5 năm (+0.11 tới +0.23), kể cả giá Bybit S5 (dev4 +0.261, 5y +0.232), và năm sạch diagnostic cũng dương ở mọi ma sát (+0.09 tới +0.12); full-path DD của C2 luôn ≤ 20 (tệ nhất 16.50 ở S5) và thấp hơn REF ở mọi hàng.
- Giống K2 (oc_k2bybit gaps +0.08 tới +0.27), tilt dip C2 giữ được edge dưới giá khác và mọi ma sát, nhưng mức tuyệt đối năm sạch 4.75%/tháng vẫn dưới cổng 5% nên không đổi REJECT adopt của oc_chronos.
- Kết luận: robust theo tiêu chí ma sát (YES) — giữ C2 làm bằng chứng độc lập củng cố K2 (hai foundation model đều giữ edge), không đưa vào G2 lúc này.
