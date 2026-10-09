# oc_k2seeds — REPORT (2026-10-07, diagnostic only)

Question (pre-registered): is the Kronos K2 clean-year gain (+0.15 %/month,
timing placebo pct 97-99) robust to the model's SAMPLING seed? Program rule
(v259): >= 5 seeds before any claim. K2 was run with ONE seed (1234).
Nothing here selects or changes anything. Post-release year 2025-09-24 ..
2026-09-23 was already scored once by oc_kronoshidden; dev years are IN
Kronos pretraining (upper bound, not rescored).

STATUS: DONE. Inference seeds 1-4 (GTX1650, heavy_slot, nohup) + seed-2 resume
after a transient CUDA OOM + 4 full-window K2 engine runs + vectorised
placebos. All gates PASS. pytest 4/4.

## Method (as PLAN, shortcut row)

- Inference IDENTICAL except `torch.manual_seed(SEED)`, SEEDS = {1234 frozen,
  1, 2, 3, 4}; window T in [2024-09-01, 2026-09-23] (90,345 rows/seed, 20/20
  groups, zero NaNs). Anchor-2025 fit REUSED from seed-1234 fits.json for all
  seeds (dir +1, q20 0.5872, q80 2.1828); multipliers differ only through the
  clean-year low1. No per-seed refit (disclosed EXTRA row not needed).
- Engine: oc_kronoshidden/run_engine.py tilt path on G2, full window
  [2021-09-24, 2026-09-23), original-K2 years 0-3 (frozen) + seed K2 year 4.
  Gate costs, win_start=5, stop-first inherited.
- Placebo: oc_k2placebo ledger.npz reused read-only (n=22312, clean fills 4772,
  base 0.677229, 0 missing joins); 1000 timing + 1000 block (42-bar) perms,
  seeds 20261011/20261012.

## Gates

- Stage 0: seed-1234 cache reproduces REF 4.648/12.90 (full 16.82) and K2
  4.801/12.10 (full 16.09) to the digit — PASS.
- Prior-path determinism: all 4 new seeds years 0-3 == dev K2 to the digit —
  PASS (clean-year delta is pure seed effect).
- Placebo pipeline: seed-1234 norm 0.751465 / timing 97.20 / block 98.70 ==
  oc_k2placebo exactly — PASS.

## Per-seed clean year (REF 4.648 / 12.90; orig-K2 4.801 / 12.10)

| seed | R %/mo | gain vs REF | DD | full DD | replica norm | timing pct | block pct |
|---|---|---|---|---|---|---|---|
| 1234 (frozen) | 4.801 | +0.153 | 12.10 | 16.09 | 0.751465 | 97.20 | 98.70 |
| 1 | 4.800 | +0.152 | 12.30 | 16.09 | 0.754670 | 98.00 | 98.50 |
| 2 | 4.825 | +0.177 | 12.21 | 16.09 | 0.766780 | 98.90 | 99.30 |
| 3 | 4.797 | +0.149 | 12.31 | 16.09 | 0.747802 | 95.90 | 97.80 |
| 4 | 4.782 | +0.134 | 12.21 | 16.09 | 0.754669 | 97.40 | 98.30 |

Range over 5 seeds: R 4.782..4.825 (span 0.043), DD 12.10..12.31. ALL 5 R >
REF. All timing/block percentiles >= 95 (seed 3 timing 95.90 marginal).
Book/rung/all-win per seed ≈ 0.535-0.539 / 0.648 / 0.627 (orig 0.5344 /
0.6480 / 0.6263).

## Multiplier-change share

- Over 43,785 clean-year decision bars present in ALL 5 seeds: 15.1% have at
  least one seed disagreeing; pairwise vs 1234: 7.40 / 7.30 / 7.39 / 7.40%.
  Sampling noise moves ~7% of bars across a quintile edge per seed, yet the
  portfolio outcome barely moves (R span 0.043) — the tilt is diversified
  across ~4.4k fills and 4 phases.

## Leakage checks

- Feature timing: 400 bars closing <= T on that shift's grid (inherited,
  truncation-tested); join on (sym, shift=phase, T) at the fill's own bar only.
- Label windows: no labels fit here (fit reused frozen: harness rows t_exit <
  2025-09-17, shift-0 only, 7d embargo).
- Fit windows: anchor-2025 fit frozen, never a later anchor; no test-year
  statistic feeds any choice; seed choice {1,2,3,4} fixed pre-registration.
- Fill timing: engine win_start=5 trade-through + stop-first; replica live
  16..238 strict trade-through (inherited).

## Vietnamese verdict

K2 hơn G2 ở cả 5 seed (+0,13..+0,18 %/tháng, percentile timing/block đều ≥95%),
nhiễu sampling chỉ đổi ~7% bars và R dao động 0,04 — gain ỔN ĐỊNH qua seed.
Nhưng mọi seed vẫn DƯỚI cổng 5 %/tháng (cao nhất 4,825) nên không đổi kết luận.
Kết luận: STABLE nhưng vẫn REJECT — giữ nguyên oc_kronoshidden, không đưa Kronos tilt vào G2.
