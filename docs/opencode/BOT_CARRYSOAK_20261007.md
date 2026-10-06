# BOT carry soak (bot_carrysoak): quote-fed replay to 2025-12-26 delivery

Harness `tests/carry_soak.py` drives `bot/carry.py` decide/note_exec/guard_carry
per cycle (bot/ NOT edited; findings are file:line reports only). Fast pytest:
`tests/test_bot_carry_soak.py` (6 tests, ~1 s, < 60 s budget).
Quotes: REAL 1m spot closes (BTC `data/raw/btc_intraday_20260924`, ETH
`data/raw/majors_intraday_20260924`, full 2025 local) + synthetic inverse
quarterly quotes F=S*exp(basis*DTE/365), entry ~5.5 %/yr (bybitq 2025 levels),
decaying into delivery. Window: T-9d entry arc -> delivery+80 min (grace path
needs delivery+60 min). Full: 601 cycles; fast: 28 cycles, same faults.
Faults, all triggered: F1 BTC fut entry leg rejected -> hedge retry, unhedged
1 cycle; F2 ETH spot entry in 2 partials (VWAP); F3 basis 2 %/yr on ETH retry
-> `carry_abandon`; F4 JSON restart mid-window (bucket 2), no refire; F5 BTC
bucket-4 slice dropped (downtime), remainder covers it; F6 ETH fut safety Buy
auto-settled by exchange -> grace finalise from slice VWAP.
Invariants (checked every cycle + at end): never unhedged > 2 cycles
(`bot/carry.py:49,736`) max seen 1, no `carry_close`; sold==filled per coin
(`bot/carry.py:1007`); no slice outside [delivery-30min, delivery)
(`bot/carry.py:639`); settlement P&L == independent `realised_pnl_pair`
recompute incl. 0.275 % drag (`bot/carry.py:156`); majors/quarterly only.
Result: full AND fast: 0 violations; BTC+ETH both `delivered`
(BTC remainder path, ETH `slices_vwap_autosettle`); 12 decided slices.
Sim assumptions (stated): markets fill same-cycle at quote; entry IOCs fill on
cross; F1/F3-miss/F5/F6 are scripted exchange faults; equity fixed 10000/f 0.25.
Not covered: live dated-quote feed, real latency/partial market fills, dust
min-notional on slices (qtys here ~0.028 BTC / 0.86 ETH, above floors).
