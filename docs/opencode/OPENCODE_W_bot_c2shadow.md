# OpenCode task bot_c2shadow - live prospective Chronos C2 feed (like scripts/kronos_shadow.py) so a paper runner can test C2
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/chronos_shadow.py`, `tests/test_chronos_shadow.py`,
`docs/opencode/CHRONOSSHADOW_20261008.md` and `research/tournament/bot_c2shadow/` (scratch, parity outputs). Do NOT edit bot/, scripts/kronos_shadow.py,
research/tournament/oc_chronos/ (read-only, incl. its pylib) or any running loop/runner. Print progress every 10 minutes. Light GPU via heavy_slot.

## Why
research/tournament/oc_chronos: C2 (Chronos-Bolt-small dip-size tilt, x1.25 / x0.75 on the outer quintiles of risk = -ch_q10) is the dev4 robust
pick and improved the post-release year. The leader wants prospective evidence: a paper runner reading a live C2 multiplier.

## Spec
1. scripts/chronos_shadow.py mirrors scripts/kronos_shadow.py (read it fully): same CLI (--once, --dry-run, --backfill-hours, --out, --now), same
   public Binance USD-M 1h klines -> per-shift 4h bars, same prospective / backfill labelling, idempotent per (sym, shift, T), API-error robust,
   never places orders. Features EXACTLY as research/tournament/oc_chronos/run_chronos_4shift.py (context = last 512 closes, log prices,
   horizon 1, quantiles; ch_q10 / ch_q50 / ch_q90 = (q - log C0) / sigma, sigma as Kronos). Import chronos from oc_chronos/pylib exactly as
   the research script does (same package versions). PIN the model: load amazon/chronos-bolt-small at the exact HF snapshot revision used by the
   research run (find it in the HF cache) and store model_sha per row; fail loudly if the revision is missing.
2. Multiplier: the C2 rule with a per-anchor fit for anchor 2026-09-24 computed EXACTLY like research/tournament/oc_chronos/make_fits.py
   (harness rows with t_exit < 2026-09-24 - 7 d; direction sign of Spearman, q20 / q80) - save it as research/tournament/bot_c2shadow/fit_2026.json
   and freeze it in the script (assert against the file at runtime, like kronos_shadow's FROZEN). Write the multiplier in BOTH columns c2_mult
   and k2_mult (the existing bot flag --k2-tilt reads k2_mult, so the runner needs no code change), plus mode / is_prospective / logged_at like
   kronos_shadow. Default out artifacts/research/chronos_shadow/chronos_features_live.parquet.
3. Parity: run --backfill-hours over 2026-09-01 .. 2026-09-23 into research/tournament/bot_c2shadow/ and join with
   research/tournament/oc_chronos/chronos_features_4shift.parquet on (sym, shift, T): bars, sigma, ch_q10 must match (Chronos-Bolt is
   deterministic: expect ~1e-6; report max abs diff); multiplier recomputed with the anchor-2025 fit must match the research one exactly.
4. Tests (pure helpers, no network/GPU): bar builder, context selection, sigma, multiplier assignment, prospective labelling, idempotency.
5. CHRONOSSHADOW_20261008.md: how the leader runs the loop (every 10 minutes, nohup, heavy_slot) and the paper runner command
   (`python -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25
   --k2-tilt artifacts/research/chronos_shadow/chronos_features_live.parquet --tag d17bfg2ch`). Do not start them yourself.
Vietnamese 3-line summary.
