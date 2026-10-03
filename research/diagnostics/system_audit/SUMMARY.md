# System audit 2026-10-03 (engine realism, leakage, live/research parity)

1. Trade-level replay vs raw Binance 1m (OpenCode, blind; fills_opencode/): M5 13,553 + R2 20,434 events. Bar alignment, book entry fills
   (strict trade-through, minute-5 rule), stops / take-profits (price, timing, stop-first ties), dip fills and exits, fees, funding:
   0 engine violations. Known convention: dip rungs are checked for exits from the minute AFTER the fill (F1: 1 M5 / 5 R2 fills whose
   fill minute already crossed the stop).
2. Leakage (OpenCode; leak_opencode/): book vs future-return correlations max 0.061 (< 0.10), no off-by-one; truncation test of the
   TradingView and order-flow feature builders 20/20 identical; walk-forward fit windows end before anchor - embargo (embargo >= horizon,
   file:line evidence). PASS.
3. Live vs research parity (parity/): feature code bit-identical (<= 1e-11), REST klines / order rebuild / Coinbase inputs / execution prep
   identical, live vs research books corr 0.98-0.99 (model-vintage noise floor). ONE DATA BUG: the live flow stores counted
   2026-09-01 .. 09-29 20:00 twice (pre-fix append of the September monthly zip, ~2026-10-02); live books moved by <= 0.0014 since
   2026-10-02 05 UTC. Repaired 2026-10-03 (orders store: 09-01..09-27 from the 09-29 snapshot, 09-28..29 halved; fill store halved;
   backup artifacts/research/system_audit/flow_backup_20261003). Post-repair volume check pending. Open: source_complete() checks
   presence only, not size; the 1m flow store still holds both daily and monthly files for 09-28 / 09-29.
4. Execution stress (engine_stress/, default-neutral engine_user hooks, base rows reproduce every reference):
   monthly 5y / dev4 / most recent year / gate DD
   - F1 fill-minute stop: +0.01 (no effect). FUND actual signed funding: +0.1..+0.26 (the flat adverse rule is conservative).
   - T2 limit fills need 2 bps extra trade-through: M5 5.48 / 5.59 / 5.02 / 19.9; T5: M5 4.78 / 4.87 / 4.42 / 21.4 (largest sensitivity).
   - S50 stops slip half into the minute wick: M5 5.66 / 5.80 / 5.13 / 18.9, BOOK WIN dev 0.648 -> 0.586; R2 DD 21.1 (S100 23.6).
   - L10 MANUAL timed-out dips closed 10 min late: M5 -0.37. R2 bot latency L5: DD 31.0 (L1: 18.6) -> the R2 bot must close timed-out
     rungs at the bar boundary.
   - PESS (F1+T2+S50+L10; R2 L5): M5 4.80 / 4.81 / 4.76 / 21.3; M4 5.25 / 5.38 / 4.72 / 20.2; M3 5.03 / 5.20 / 4.38 / 22.6;
     M2 4.29 / 4.50 / 3.47 / 16.0; M1 2.83 / 2.71 / 3.32 / 17.1; R2 5.55 / 5.64 / 5.16 / 31.9 (PESS with L1: DD 27.4).
Reading: no engine bug and no leakage; the numbers are honest under the user's cost rules, but they depend on fills at the limit price
(queue / venue basis) and on stops filling at the stop level. Under the combined pessimistic row only M4 keeps >= 5 %/month 5y with
DD ~20; M5's book win stays >= 0.55 but its DD passes 20; R2 is fragile to bot latency and stop slippage.
