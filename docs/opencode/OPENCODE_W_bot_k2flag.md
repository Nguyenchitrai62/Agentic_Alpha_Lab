# OpenCode task bot_k2flag - optional Kronos K2 dip-size tilt in the bot (default OFF) for a dedicated PAPER runner
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (leader-assigned implementation): you may edit `bot/run.py` (and
`bot/mirror.py` only if strictly needed) and create `tests/test_bot_k2flag.py` and `docs/opencode/BOT_K2FLAG_20261007.md`. Never touch
artifacts/bot/* state or running processes; do not start runners (the leader does). Paper / mock only.

## Why
research/tournament/oc_kronoshidden + oc_k2placebo: the Kronos-small K2 dip tilt shows significant timing skill on the post-release year
(timing-placebo percentile 97.2, block 98.7; +0.15 %/month vs G2 and its exposure control in the engine). Not deployed (dev worst year lower).
The leader wants a dedicated paper runner with K2 to collect direct prospective evidence. scripts/kronos_shadow.py already logs live features
every hour: artifacts/research/kronos_shadow/kronos_features_live.parquet (sym, shift, T, ..., k2_mult, mode in {prospective, late,
backfill}, logged_at).

## Implement (default behaviour must be bit-identical when the flag is absent)
- New CLI flag `--k2-tilt PATH` (default None). When set, for every NEW dip entry order of phase s (clock shift) for coin c whose holding bar
  opens at T: look up the row (sym = c + 'USDT', shift = s, T) in the parquet (re-read the file at most once per cycle; tolerate it missing /
  locked -> multiplier 1.0 and log op=k2_missing once per bar); use k2_mult only if the row exists and mode is 'prospective' or 'late' (both are
  computed from bars closed <= T); else 1.0. Multiply the dip rung entry quantity by k2_mult BEFORE the existing budget / gross-cap / lot
  rounding logic (so caps still bind); protection orders follow the filled quantity as today.
- Log op=k2_mult per (coin, phase, bar) once with the multiplier used. No change to the book, carry, exits or any other path.
- Tests (tests/test_bot_k2flag.py, mock exchange / existing test fixtures): flag absent -> identical orders to the current code on a fixture
  cycle; flag set with 1.25 / 0.75 / missing rows -> entry qty scaled accordingly, caps still applied, lot minimum respected (a scaled
  quantity below the minimum is skipped as dust like any other), parquet missing -> 1.0. Run `.venv/Scripts/python.exe -m pytest tests -q -k bot`
  - everything must pass.
- Doc (<= 30 lines): the exact runner command the leader should use (same flags as paper_d17bfg2 + `--k2-tilt
  artifacts/research/kronos_shadow/kronos_features_live.parquet --tag d17bfg2k2`), and what to compare after 8+ weeks.
