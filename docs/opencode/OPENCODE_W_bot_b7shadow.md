# OpenCode task bot_b7shadow - live prospective cascade-boost feeds (B7 and B7 x C2) for paper runners, no bot code change
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/cascade_shadow.py`, `tests/test_cascade_shadow.py`,
`docs/opencode/B7SHADOW_20261008.md` and `research/tournament/bot_b7shadow/` (scratch, parity outputs). Do NOT edit bot/, other shadow scripts,
research folders of other tasks (read-only) or any running loop / runner. CPU only. Print progress every 10 minutes. Never read folders outside
the workspace (auto-rejected).

## Why
research/tournament/oc_cascadeboost: B7 = dip budget x1.5 for 7 days after a cascade bar (oc_cascadedelay definition, > 4 sigma 4h move);
oc_b7c2: B7 x C2 keeps Bybit full-path DD at 17.4. The bot's --k2-tilt flag (bot/run.py `_k2_scaled_plan`, read it) multiplies each dip rung's
size_frac by k2_mult of (coin, shift, bar open) from a parquet - a per-rung 1.5 inside the window equals B7's budget x1.5.

## Spec
1. scripts/cascade_shadow.py mirrors scripts/chronos_shadow.py (CLI --once / --dry-run / --backfill-hours / --out / --now, public Binance USD-M
   1h klines -> per-shift 4h bars, prospective / backfill labelling, idempotent per (sym, shift, T), API-robust, never places orders). It flags
   cascade bars EXACTLY as research/tournament/oc_cascadedelay / oc_cascadeboost (read their code: which coins trigger, sigma window, union
   across coins / shifts, the bar-close timing) and writes, per (sym, shift, T): b7_mult (1.5 inside a 7-day window after a cascade bar close,
   else 1.0), and - reading artifacts/research/chronos_shadow/chronos_features_live.parquet read-only - b7c2_mult = b7_mult x c2_mult (1.0 where
   the C2 row is missing). Two outputs: artifacts/research/cascade_shadow/b7_live.parquet (k2_mult = b7_mult) and
   artifacts/research/cascade_shadow/b7c2_live.parquet (k2_mult = b7c2_mult), same columns as the chronos feed.
2. Verify in bot/run.py (read-only) that the dip gross cap (--dip-gross-cap) and every other limit are applied AFTER the k2 scaling; report
   with code citations. If they are not, stop and report (do not edit bot/).
3. Parity: backfill 2026-09-01 .. 2026-09-23 and compare b7_mult with oc_cascadeboost's frozen boost parquet on (sym, shift, T) - must match.
4. Tests on pure helpers (no network). 5. B7SHADOW_20261008.md: loop command and the two paper-runner commands (tags d17bfg2b7, d17bfg2b7c2,
   flags exactly as d17bfg2 + --k2-tilt <feed>). Do not start them yourself. Vietnamese 3-line summary.
