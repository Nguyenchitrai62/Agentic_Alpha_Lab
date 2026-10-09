# oc_k2bybit — REPORT (2026-10-07)

Question: does the Kronos K2 dip tilt keep its edge on BYBIT prices (S5) and
under the other frictions? (Unlike the Amihud A1 book tilt, which vanished on
S5 in oc_amihudrobust.) PLAN.md was written BEFORE any outcome; no definition
changed after outcomes (see post-hoc log). Engine via heavy_slot (sequential
shifts, heartbeat every 600 s). pytest 4/4.

STATUS: DONE. 12 engine rows (REF/K2 x base/S1/S2/S3/S4/S5, 4 phases each = 48
phase sims) + CPU scoring. Reproduction gates PASS to the digit.

## 0. Reproduction gates (PASS, to the digit — else STOP)

- Base REF == `v421_result.json` G2 (R2B1D17BFG2) all 5 years + 5y 5.410 +
  full-path DD 16.82.
- Base K2 == `oc_kronoshidden` REPORT/results.json (dev 2.469/3.478/6.679/10.653,
  Y4 4.801, full-path DD 16.09).
- REF_S1..S5 == `v421_audit/ROBUST.md` G2 friction row to the digit
  (S1 4.571/17.45/17.37, S2 5.212/16.91/16.86, S3 4.578/17.32/17.24,
  S4 4.898/17.31/17.24, S5 4.883/18.11/18.09), so friction implementations are
  exactly the existing ones. Comparison valid.

## 1. Dev4 (anchors 2021..2024 — CONTAMINATION CAVEAT: likely IN Kronos pretraining -> UPPER BOUND)

4-phase reset %/mo (yearly DD in brackets) [2021, 2022, 2023, 2024] | dev4 mean / W / maxDD:

| fric | REF | K2 | gap dev4 |
|---|---|---|---|
| base | 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27 \| 5.601/2.588/16.91 | 2.469/11.78, 3.478/16.20, 6.679/15.69, 10.653/8.54 \| 5.772/2.469/16.20 | +0.171 |
| S1 | 1.975/11.18, 2.592/17.45, 4.853/16.01, 9.712/8.31 \| 4.740/1.975/17.45 | 1.827/12.72, 2.744/16.82, 5.574/15.84, 9.621/8.56 \| 4.898/1.827/16.82 | +0.158 |
| S2 | 2.513/11.09, 3.132/16.91, 5.624/15.82, 10.479/8.29 \| 5.391/2.513/16.91 | 2.379/12.24, 3.301/16.18, 6.247/15.76, 10.469/8.55 \| 5.552/2.379/16.18 | +0.161 |
| S3 | 2.070/11.85, 2.476/17.32, 4.346/16.03, 9.798/8.36 \| 4.628/2.070/17.32 | 2.014/12.48, 2.766/16.62, 5.253/15.74, 9.746/8.61 \| 4.902/2.014/16.62 | +0.274 |
| S4 | 2.363/11.06, 2.915/17.31, 4.422/17.08, 10.460/8.27 \| 4.992/2.363/17.31 | 2.239/12.02, 3.233/16.43, 4.668/17.01, 10.407/8.51 \| 5.090/2.239/17.01 | +0.098 |
| S5 | 2.129/12.36, 2.735/18.11, 4.932/16.89, 10.377/9.22 \| 4.994/2.129/18.11 | 1.957/13.52, 2.982/17.49, 5.209/16.66, 10.355/9.10 \| 5.077/1.957/17.49 | +0.083 |

S5 y2021 is a SHORT window (Bybit from 2021-11-15, labelled). No losing dev year
in any row. K2 DD <= REF DD in 5/6 dev4 rows (S5: 17.49 vs 18.11 — lower too).

## 2. Post-release year Y4 2025-09-24..2026-09-23 (clean BUT already scored once by
oc_kronoshidden for base — every Y4 number here is a labelled DIAGNOSTIC re-score)

| fric | REF R/DD | K2 R/DD | gap Y4 |
|---|---|---|---|
| base | 4.648/12.90 | 4.801/12.10 | +0.153 |
| S1 | 3.900/13.61 | 4.009/12.98 | +0.109 |
| S2 | 4.501/12.98 | 4.620/12.10 | +0.119 |
| S3 | 4.380/12.75 | 4.582/11.57 | +0.202 |
| S4 | 4.522/13.54 | 4.621/12.96 | +0.099 |
| S5 | 4.443/12.37 | 4.553/11.63 | +0.110 |

K2 beats REF in the clean year under every friction (diagnostic).

## 3. Five-year path + full-path DD (v388.mix from 2021-09-24)

| fric | REF 5y R/W/DD/full | K2 5y R/W/DD/full | gap 5y |
|---|---|---|---|
| base | 5.410/2.588/16.91/16.82 | 5.577/2.469/16.20/16.09 | +0.167 |
| S1 | 4.571/1.975/17.45/17.37 | 4.720/1.827/16.82/16.71 | +0.149 |
| S2 | 5.212/2.513/16.91/16.86 | 5.365/2.379/16.18/16.03 | +0.153 |
| S3 | 4.578/2.070/17.32/17.24 | 4.838/2.014/16.62/16.46 | +0.260 |
| S4 | 4.898/2.363/17.31/17.24 | 4.996/2.239/17.01/16.32 | +0.098 |
| S5 | 4.883/2.129/18.11/18.09 | 4.972/1.957/17.49/17.41 | +0.089 |

All K2 full-path DDs <= 20 (worst 17.41 on S5) and below the matching REF
full-path DD in every friction. All-trade win rates move ≤ 0.002 (e.g. base Y4
K2 0.6263 vs REF 0.6267; S5 Y4 K2 0.6248 vs REF 0.6247) — the tilt is sizing,
not trade selection.

## 4. Leakage / causality checks (how verified)

- Feature timing: Kronos forecast for bar open T uses ONLY the 400 bars closing
  <= T on that shift's grid (inherited Part A); tilt reads only (coin,
  holding-bar T) low1. `test_k2_truncation_causal_on_frozen_features`
  recomputes K2 multipliers from a truncated frozen feature table — identical
  on the kept prefix; multiset ⊂ {0.75, 1.0, 1.25}.
- Label windows: fits.json reused frozen (harness rows t_exit < A - 7d,
  shift-0 only); year y uses anchor-y fit only, never a later anchor.
- Fit windows: no refit here; S5 is a price-source switch, not a fit.
- Fill timing: win_start/sleeve_start/stop_slip per friction asserted in
  `test_friction_constants_match_robust_v421` (S1 globals patch + restore in
  source; S5 live0 2021-11-15 + Bybit dir); engine fills only on 1m
  trade-through with stop-first (inherited harness).
- `tests/test_oc_k2bybit.py` 4/4 pass.

## 5. Post-hoc log

- No PLAN definition changed after outcomes. One pre-outcome code fix (before
  any engine run): per-variant copy of the friction kwargs (shared-dict
  `pop("win_start")` would have reset S2/S3 latency to 5 on the second variant)
  + misleading comment cleanup. No rows added, no thresholds touched.
- S1 TAKER = 0.0007 + 0.0005 = 0.0012 (same as robust_v421.py).

## Vietnamese verdict (3 lines)

- K2 hơn REF ở mọi ma sát trên cả dev4 (+0.08 tới +0.27) và đường 5 năm (+0.09 tới +0.26), kể cả giá Bybit S5 (dev4 +0.083, 5y +0.089), và năm sạch diagnostic cũng dương ở mọi ma sát (+0.10 tới +0.20); full-path DD của K2 luôn ≤ 20 (tệ nhất 17.41 ở S5) và thấp hơn REF ở mọi hàng.
- Khác với tilt sách A1 (S5 về 0 ở oc_amihudrobust), tilt dip K2 giữ được edge dưới giá khác và mọi ma sát, nhưng dev vẫn là cận trên (Kronos pretraining) và mức tuyệt đối năm sạch 4.80%/tháng vẫn dưới cổng 5% nên không đổi REJECT adopt của oc_kronoshidden.
- Kết luận: robust theo tiêu chí ma sát (YES) — giữ K2 trong paper runner hiện tại để lấy bằng chứng prospective, không đưa vào G2 lúc này.
