# vf W9: independent blind audit of the hidden-year evaluation (read OPENCODE_VF_COMMON.md first)
Goal: reproduce ONE result from its specification alone, before reading the leader's code.
Do NOT open `src/agentic_alpha_lab/research_vf.py`, `src/agentic_alpha_lab/vf_families.py`,
`src/agentic_alpha_lab/backtest/portfolio.py`, `scripts/vf_lab.py`,
`scripts/replay_hidden_year.py` or `artifacts/research/vf/` until A is saved.
Write only under `research/vf_audit/` and `tests/test_vf_audit.py`.

Specification (Binance USD-M BTCUSDT 4h bars and 1d bars, `data/raw/ma_ribbon_20260924/`):
- Book T (trend): daily ribbon d = +1 if last CLOSED daily close > SMA50 > SMA200
  (daily bar joined as-of the 4h bar close), -1 if close < SMA50 < SMA200, else 0.
  4h condition L = close > EMA20 > EMA200 (pandas ewm span, adjust=False, min_periods=span).
  A long starts on the bar where L turns true, only if d != -1 at that bar; it is
  held while L stays true; else 0.
- Book D (Donchian long/short): long when close > max(high of previous 55 bars);
  exit when close <= min(low of previous 10 bars). When flat from the long book,
  short when close < min(low of previous 55 bars) and d == -1; exit when
  close >= max(high of previous 10 bars); a short never overlaps a long.
- Target = 0.65 * (0.5*T + 0.5*D) as signed fraction of equity; decided at 4h
  close t, traded at open t+1; quantity fixed while target unchanged; fee 0.0002
  on traded notional (stress: 0.0006 fee plus 0.0005 adverse slippage on each
  trade); long pays 0.0001 per funding event (fundingTime in [open_t, open_t+1))
  on long notional; shorts pay 0.
- Window: decisions on bars with open_time in [2025-09-24, 2026-09-23 20:00 UTC];
  start flat; liquidate at the final close.
A. Save `research/vf_audit/replication.json`: net %, fees, funding, number of
   target changes, max drawdown on 4h closes and intrabar (long marks at low,
   short at high) for normal and stress, plus the list of target-change times.
B. Then read the leader files and `artifacts/research/vf/replay/*combo*` and
   write `research/vf_audit/COMPARISON.md`: every difference > 0.3 pp or any
   target-change mismatch with its root cause, proven by a minimal example.
   Also audit `research_vf.run` for any look-ahead in parameter/scale selection.
Do not change leader files.
