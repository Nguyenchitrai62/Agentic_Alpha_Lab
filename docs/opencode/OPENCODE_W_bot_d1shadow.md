# OpenCode task bot_d1shadow - live prospective D1 (downside-share) feed so a paper runner can test D1 (model-free, like chronos_shadow)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `scripts/d1_shadow.py`, `tests/test_d1_shadow.py`,
`docs/opencode/D1SHADOW_20261008.md` and `research/tournament/bot_d1shadow/` (scratch, parity outputs). Do NOT edit bot/, other shadow scripts,
research/tournament/oc_downshare/ (read-only) or any running loop / runner. Print progress every 10 minutes. CPU only (no model).

## Spec
1. scripts/d1_shadow.py mirrors scripts/chronos_shadow.py (read it fully): same CLI (--once, --dry-run, --backfill-hours, --out, --now), same
   public Binance USD-M 1h klines -> per-shift 4h bars, prospective / backfill labelling, idempotent per (sym, shift, T), API-error robust, never
   places orders. Feature EXACTLY as research/tournament/oc_downshare (D1: trailing-6d downside-RV share; read build_downshare.py for the exact
   definition and data granularity - if it uses 1m returns, fetch the needed 1m klines publicly, or prove that 1h aggregation gives the same value).
2. Multiplier: the D1 rule with a per-anchor fit for anchor 2026-09-24 computed exactly like oc_downshare/make_fits.py (harness rows t_exit <
   2026-09-24 - 7 d) - save as research/tournament/bot_d1shadow/fit_2026.json and freeze it in the script (asserted at runtime). Write it in
   BOTH columns d1_mult and k2_mult (the bot's --k2-tilt reads k2_mult). Default out artifacts/research/d1_shadow/d1_features_live.parquet.
3. Parity: backfill 2026-09-01 .. 2026-09-23 into your folder and join with oc_downshare's feature file on (sym, shift, T): feature max abs diff,
   multiplier (anchor-2025 fit) agreement - must be exact or explained.
4. Tests on pure helpers (no network). 5. D1SHADOW_20261008.md: loop and paper-runner commands (tag d17bfg2d1); do not start them yourself.
Vietnamese 3-line summary.
