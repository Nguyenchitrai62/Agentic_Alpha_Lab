# oc_k2seeds — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Diagnostic only: is the Kronos K2 clean-year gain robust to the model's SAMPLING seed?
Program rule (v259): every stochastic learner must report >= 5 seeds before any claim.
K2 (post-release +0.15 %/month, timing placebo pct 97-99, audited) was run with ONE seed.
Nothing here selects or changes anything. The post-release year 2025-09-24 .. 2026-09-23
was already scored once by oc_kronoshidden; dev years are IN Kronos pretraining (upper bound).

## Pre-registered variants (ONLY these 5, fixed)

- SEEDS = {1234 (original, frozen), 1, 2, 3, 4}. No other variant. No tuning.
- Verdict question (fixed): is the gain stable across seeds (all 5 clean-year R > REF)?

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (4h OHLCV, 5 majors x 4 shifts).
- `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (seed-1234 reference).
- `research/tournament/oc_kronoshidden/fits.json` (anchor-2025 fit: dir +1, q20 0.5872, q80 2.1828).
- `research/tournament/oc_kronoshidden/ctrl.json`, `run_engine.py`, `tilt_rule.py` (mechanism).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json` (G2 REF).
- `research/tournament/oc_k2placebo/compute_k2placebo.py` + `tmp/ledger.npz` (dip replica ledger, reuse read-only).
- `research/tournament/kronos/{model/,kronos_fast.py}` weights (Kronos-small + Tokenizer-base, HF cache, no re-download).

## Fixed inference settings (IDENTICAL except torch seed)

- Kronos-small + Tokenizer-base, context 400 x 4h bars, pred_len 6, S = 64 paths,
  T = 1.0, top_p = 0.9, top_k = 0, fp32, per-window z-normalisation + clip 5.
- Forecast for bar open T uses ONLY the 400 bars closing <= T on that shift's grid.
- `torch.manual_seed(SEED)` once at start; same group order (sym,shift sorted) and batch order (B=32) for all seeds.
- Window (fixed): T in [2024-09-01, 2026-09-23] (post-release year + 1y buffer), all 4 shifts, 5 majors.
  Bars before 2024-09-01 are context only, never scored.
- SHORTCUT (disclosed, pre-registered): the anchor-2025 fit is REUSED from the original
  seed-1234 `fits.json` for ALL seeds (no per-seed refit). Rationale: per-seed refit would need
  shift-0 features over 2020-10 .. 2025-09 per seed (4x full inference, ~8-12h GPU). The K2
  multipliers on the clean year then differ ONLY through the clean-year low1 features.
  If time permits, a per-seed refit is added as a disclosed EXTRA row only; the shortcut row stays.
- Outputs: `kronos_features_seed{S}.parquet` per new seed (sym,shift,T,low1[,sigma,C0,others]).

## Fixed K2 rule (as oc_kronoshidden, anchor-2025 fit only)

- risk = -low1. Direction +1, q20/q80 from fits.json["2025-09-24"]. K2: 1.25 favourable
  outer quintile (r >= q80) / 0.75 unfavourable (r <= q20) / 1 else; missing/NaN -> 1.
- Applied to all 4 shifts in the post-release year 2025-09-24 .. 2026-09-23 only.

## Fixed engine row (4-phase, as oc_kronoshidden, post-release year only)

- Mechanism = copy of `oc_kronoshidden/run_engine.py` tilt path on G2
  (rule="inv", k=1.0, kd=1.7, bear=True, G=2.0 = v421 R2B1D17BFG2); budget unchanged.
- Two-stage validation: (1) seed-1234 rerun (or cache reuse) must reproduce clean-year
  REF 4.648 / 12.90 and K2 4.801 / 12.10 to the digit, else STOP; (2) per new seed,
  full-window simulation [2021-09-24, 2026-09-23) with tilt = original-K2 in years 0-3
  (frozen) and new-seed K2 in year 4 — OR equivalently a last-year-only simulation if it
  reproduces the seed-1234 K2 last-year R within 0.02 (disclosed which path was used).
  The prior path is identical across seeds, so the clean-year delta is pure seed effect.
- Costs (gate): maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0.
  Limits fill only on 1m trade-through, nothing in first 5 min after a 4h close (win_start=5);
  stop-first in shared 1m bar (engine handles).
- Score per seed (4-phase reset metric `year_reset` y=4 + yearly DD + full-path DD via v388.mix,
  book/rung wins, fills, sized mean). REF is NOT rescored (frozen 4.648 / 12.90).

## Fixed placebo (vectorised, as oc_k2placebo, clean year only)

- Reuse `oc_k2placebo/tmp/ledger.npz` read-only (gate: n=22312, base_sum5y=7.718304 +/-0.002 not rescored).
- Per seed: join clean-year fills (sym,shift=phase,T) to that seed's low1, K2 mult as above;
  per-year w*y 4-phase-mean base/k2/realised_mean/norm (norm = k2/realised_mean, denominator = actual).
- Timing placebo: 1000 uniform bar-level permutations of the seed's clean-year decision-bar
  multiset within the year (seed 20261007+4); block placebo: 1000 perms in 42-bar blocks per
  (sym,shift) (seed 20261008+4). Percentile = 100*(1+#{perm<=actual})/1001. Vectorised numpy
  (no per-perm Python engine). Report per-seed actual_norm, p5/p50/p95, percentile (both placebos).
- Multiplier-change share (fixed): over clean-year decision bars (sym,shift,T present in ALL 5 seeds),
  fraction where NOT all 5 K2 mults agree; plus pairwise vs 1234 per new seed. Report both.

## What is NOT done

- No dev-year scoring, no variant selection, no threshold/edge tuning, no G2 change.
- No use of forward returns beyond the replica's mechanical D0 exits and the engine's own fills.
- If anything changes after seeing an outcome, the original row stays and the change is an extra disclosed row.

## Outputs

- `research/tournament/oc_k2seeds/results.json` (per-seed R/DD/norm/percentiles/change-share + config + gates).
- `REPORT.md` (per-seed table vs REF 4.648/12.90, gain/placebo/change-share, leakage checks, 3-line Vietnamese verdict).
- `tests/test_oc_k2seeds.py` (>=1 causality/truncation test + >=1 hand-checked synthetic case; pytest -q).
- Scratch only under `research/tournament/oc_k2seeds/tmp/`. GPU + heavy engine steps via heavy_slot
  (`--tag oc_k2seeds`, never `--leader`); progress print >= every 10 min. Import torch before pandas in GPU scripts.

## Leakage statement (to be confirmed in REPORT)

- Feature timing: 400 bars closing <= T (inherited); join on (sym,shift,T) at the fill's own bar only.
- Label windows: no labels fit here (fit reused frozen: harness rows t_exit < 2025-09-17, shift-0 only, 7d embargo).
- Fit windows: anchor-2025 fit frozen, never a later anchor, no test-year statistic feeds any choice.
- Fill timing: engine win_start=5 trade-through + stop-first; replica live 16..238 strict trade-through (inherited).
