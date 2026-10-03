# SYSTEM AUDIT 1 - fills replay vs raw 1m (M5=v367, R2=v321)
Method: independent checker (replay_checker.py, no engine import) over raw Binance
1m klines; Part A replication.json saved BEFORE engine_user.py was read.
1. Bar alignment: 500+500 random (bar,symbol) opens == raw 1m open: 0 mismatches.
2. Book entries: v367 1032 fills/1829 orders, v321 1333/1647: 0 too-early, 0
no-touch fills, 0 late, 0 missed. (Engine default win_start=2 vs rule 5 min in
issue bar: no fill observed in minutes 2-4, so zero effect here.)
3. Book exits: 367 (M5) + 246 (R2) stops/tps: 0 price, 0 late, 0 tie violations.
4. Dip fills: 1898 (M5) + 5459 (R2): 0 price (open*(1-k*sig4)), 0 window, 0
first-touch violations.
5. Rung exits: ret/timeout-price flags are 100% a KNOWN CONVENTION, not a bug:
engine stores NET exit prices (price=fill*(1+ret), ret net of maker+taker,
+0.0001 funding at 00/08/16 timeouts; fingerprints 0.0004/0.00075/0.00085
exact), while the assignment subtracts fees again (double count). Timing flags
in Part A were checker artifacts (sorted pairing; TP limit=true exit+2*maker*
fill): exhaustive per-(bar,symbol) bijection search gives 1371/1371 (M5) and
2233/2233 (R2) groups fully consistent, incl. crash bars. Zero engine timing
violations.
6. Fill minute already through stop/backstop: 1 (M5) + 5 (R2), reported only
(engine checks exits from the minute after the fill).
Classification: (i) engine bugs: NONE. (ii) rule ambiguity: ret/timeout-price
convention. (iii) my-bug: Part-A pairing/TP-level artifacts, resolved.
Estimated real PnL effect: 0.00 (replication.json pnl_effect -0.31/-0.41 is the
phantom double-count, not a misstatement; engine compounds the net ret).
Files: replay_checker.py, forensics_partb.py, matcher_partb.py,
mismatches_{v367,v321}.csv, mismatches.csv, replication.json.
