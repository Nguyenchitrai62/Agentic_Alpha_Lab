# oc_bookichorizon REPORT — at which horizon does the DEPLOYED book's skill live?

Method per PLAN.md (pre-registered; one implementation note logged in PLAN:
per-(year,h) bootstrap streams for checkpoint resume, same seed family/B/L).
Caches read-only (`member_A/Aq_O1_orders`, `member_B/Bq_tv`, `members_v154[D]`,
`members_quarterly_D` + `opens_v154`); series on the `books_v154` standard
grid: `O1=(A+Aq+B+Bq)/4`, `CB=(D+Dq)/2`, `FULL=0.8*O1+0.2*CB`,
`FINAL`=FULL with the v421 x0.5 bear filter on longs. Target per (t,coin,h):
`y = (open[t+h]/open[t]-1)/sigma[t]`, sigma = trailing-360-bar std of 1-bar
open returns (min120, causal from 2017 history). h in {1,2,6,18,42} 4h bars
(=4h,8h,1d,3d,7d). Years `[A,A+365d)`, dev Y0..Y3 + most-recent Y4 labelled.
Full numbers in `results.json` (250 rows: 10 series x 5 y x 5 h).

## 1. FINAL (deployed book): pooled IC per (year, h) [95% block CI]

| h | 2021 | 2022 | 2023 | 2024 | 2025 (recent) |
|---|---|---|---|---|---|
| 1 (4h) | +0.018 [-0.01,+0.05] | +0.018 [-0.00,+0.04] | +0.023 [-0.00,+0.05] | +0.024 [+0.00,+0.04] | +0.036 [+0.01,+0.07] |
| 2 (8h) | +0.025 [-0.01,+0.06] | +0.008 [-0.02,+0.04] | +0.026 [-0.01,+0.06] | +0.028 [-0.01,+0.06] | +0.045 [+0.00,+0.09] |
| 6 (1d) | +0.047 [-0.02,+0.10] | +0.012 [-0.03,+0.06] | +0.043 [-0.01,+0.09] | +0.030 [-0.01,+0.08] | +0.067 [+0.00,+0.13] |
| 18 (3d) | +0.066 [-0.02,+0.16] | +0.012 [-0.06,+0.08] | +0.052 [-0.04,+0.15] | +0.029 [-0.04,+0.10] | +0.105 [+0.01,+0.20] |
| 42 (7d) | +0.144 [-0.00,+0.29] | -0.036 [-0.14,+0.07] | +0.042 [-0.12,+0.18] | +0.085 [-0.01,+0.18] | +0.107 [-0.04,+0.24] |

Dev4 sign stability: h=1,2,6,18 → 4/4 positive; h=42 → 3/4 (2022 flips).
CIs are WIDE: only 1/4 dev years exclude 0 at h=1 (2024), 0/4 at h=2,6,18,42.

## 2. FINAL: TS mean (mean of 5 per-coin ICs) vs XS mean (ranks across coins)

| h | TS 21/22/23/24 (recent) | XS 21/22/23/24 (recent) |
|---|---|---|
| 1 | +0.019/+0.017/+0.022/+0.023 (+0.033) | +0.006/+0.008/+0.017/+0.011 (+0.023) |
| 2 | +0.025/+0.006/+0.025/+0.028 (+0.041) | +0.001/+0.027/+0.015/+0.024 (+0.041) |
| 6 | +0.048/+0.008/+0.041/+0.029 (+0.062) | +0.001/+0.042/+0.027/+0.043 (+0.038) |
| 18 | +0.072/+0.004/+0.048/+0.026 (+0.102) | -0.007/+0.053/+0.028/+0.066 (+0.064) |
| 42 | +0.147/-0.038/+0.039/+0.084 (+0.108) | -0.018/-0.003/+0.034/+0.058 (+0.048) |

Pooled ≈ TS at every h (stacking coins ≈ timing each coin); XS is ~2-3x
smaller and less stable (2021 XS ≤ 0 at h=18,42). The timing P&L is carried
by the TIME-SERIES dimension, not by coin selection at each bar.

## 3. Where does it come from? Dev4 pooled means (all positive at h=1..18)

| series | h=1 dev4 | h=6 dev4 | h=42 dev4 (2022 flips) |
|---|---|---|---|
| A (whale-flow ann) | +0.020 [4/4] | +0.030 [4/4] | +0.061 [3/4] |
| Aq (whale-flow qtr) | +0.018 [4/4] | +0.025 [4/4] | +0.048 [3/4] |
| B (TV ann) | +0.020 [4/4] | +0.036 [4/4] | +0.058 [3/4] |
| Bq (TV qtr) | +0.019 [4/4] | +0.031 [4/4] | +0.052 [3/4] |
| D (CB-prem ann) | +0.016 [4/4] | +0.022 [4/4] | +0.067 [3/4] |
| Dq (CB-prem qtr) | +0.015 [4/4] | +0.023 [3/4] | +0.060 [3/4] |
| O1 | +0.020 [4/4] | +0.032 [4/4] | +0.054 [3/4] |
| CB | +0.016 [4/4] | +0.024 [4/4] | +0.066 [3/4] |
| FULL / FINAL | +0.020/+0.021 [4/4] | +0.031/+0.033 [4/4] | +0.057/+0.059 [3/4] |

No single member carries it: A/Aq/B/Bq/D/Dq are ALL 4/4 positive at h=1,2,18
(Dq 3/4 at h=6,18 — same 2022/2021 soft spots as everyone). O1 and CB agree.
FULL≈FINAL at every h (bear filter changes dev4 pooled IC by only +0.001 —
ranks barely move when longs are halved). Per-coin (FINAL h=6 dev):
2021 all 5 positive (BNB +0.075 strongest); 2022 ETH -0.029 the soft coin;
2023 all positive; 2024 SOL -0.037 the soft coin. At h=42: 2021 all strongly
positive (+0.08..+0.23), 2022 4/5 negative — the 7d skill is regime-driven.

## 4. Sign only (hit rate, FINAL pooled; CIs all cover 0.5)

h=1: .506/.512/.501/.511 (.508); h=2: .500/.506/.506/.509 (.517);
h=6: .510/.504/.505/.503 (.523); h=18: .511/.502/.503/.498 (.530);
h=42: .550/.481/.493/.503 (.538). Direction agrees with IC (weakly > 0.5
except 2022-h42 0.48), but no hit CI excludes 0.5 — signs alone are noise;
the IC lives in the RANK MAGNITUDE, not in binary direction.

## Key question

**The deployed book's timing skill lives at SHORT horizons h=1..18 bars
(4h..3d) in the TIME-SERIES dimension (pooled≈TS +0.02..+0.04, 4/4 dev years
positive for every member, O1 and CB alike; XS ~2-3x smaller and 2021-negative
at h=18/42) — NOT at the 7-day h=42 label (3/4 dev years, 2022 flips for all
six members; CIs cover 0 everywhere). That is exactly why TV/SPOT-flow/premium
rebuilds scored ~0 OOS IC vs the 7-day label even in 2021-2024, and why
quarter-to-quarter sign flips dominate at h=42: the presample studies tested
the one horizon where the deployed blend has no stable edge, while the engine
(sized on 4h decisions, SL/TP at ~sigma_d multiples) harvests the short-horizon
time-series drift the block-shuffle placebo detects.**

## What failed / limits (honest)

- Magnitudes are TINY (+0.02..+0.04 pooled at h=1..6) and NO dev-year CI
  excludes 0 except 2024-h1; hit rates are 0.50-0.52 with all CIs covering
  0.5. Stable sign ≠ tradeable edge after costs — this explains timing P&L
  direction, not its size.
- h=42 (the 7d label the presample studies used) is the WORST horizon:
  2022 negative for every series, widest CIs (±0.10..0.15). Any conclusion
  drawn at h=42 alone (including "no skill") does not transfer to h≤18.
- Vol-normalisation by trailing-360-bar sigma is one fixed choice
  (pre-registered); raw forwards were not scored. Sigma uses full 2017..
  history causally, but early-2021 sigma still warms up from pre-2021 regimes.
- Bear filter barely moves IC (+0.001): IC cannot judge the filter — its
  2021 P&L gain (bookattrib +0.34pp) is a sizing/downside effect, not rank skill.

## Leakage / execution statement

Series values at bar t are cached member values at t (known at t's close;
research fits frozen before each anchor, read-only here). sigma[t] uses only
opens ≤ t (2017.. history, trailing 360, min120). Forward returns are scoring
labels only, never features. No test-year or most-recent-year statistic
entered any weight/threshold/choice (blend + bear + horizons + B/L/seed fixed
in PLAN; most-recent year labelled, never used to choose). No fits in this
study. No fills claimed (IC diagnostic, no PnL/fees/funding). Tests:
causality/truncation + hand-checked synthetic
(`tests/test_oc_bookichorizon.py`).

## Verdict (tiếng Việt, kết luận chính)

- Skill của book G2 nằm ở chân trời NGẮN h=1..18 bar (4h–3d) theo chiều time-series (pooled≈TS dương cả 4 năm dev ở mọi member, XS nhỏ hơn 2–3 lần), chứ KHÔNG ở nhãn 7 ngày h=42 (2022 đảo dấu toàn bộ).
- Đó là lý do presample/flow/premium đo IC ~0 với nhãn 7 ngày ngay cả 2021–2024 mà timing P&L vẫn dương: họ đã đo sai chân trời, còn engine ăn drift ngắn hạn mà placebo phát hiện.
- Không đổi deployment sau nghiên cứu này; mọi quy tắc horizon mới (nếu có) phải đăng ký walk-forward và cần prospective log vì IC quá nhỏ (CI đều phủ 0, hit ~50–52%).
