# oc_m_breakeven REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #2 (docs/opencode/IDEAS9_20261008.md): one-move break-even on ALL
brackets (book + dip) of the MANUAL product. Pre-registered rows only:
M5_human (deployed MANUAL reference), V1_BE075 (+0.75sg to entry),
V2_BE050 (+0.50sg to entry). Selection V1 vs V2 ONLY on dev 2021-2024;
the most recent year 2025-09-24..2026-09-23 is POST-RELEASE, scored once
for the pick + M5_human, never used to choose.

## 1. Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00 over 4 phases) and equals R5 3.728 / W 0.847 / maxDD 17.94 /
  fullDD 17.79 / book_win .6482 (Rdev4 3.661 / Rlast 3.994).
- Harness: MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 /
  sleeve_start=16, night bar skipped, agents ON with per-phase R2 tables);
  gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first on same-bar SL+TP touch; dip timeout at next 4h open.
- Disclosure: M5_human already carries the engine book BE at +2.0sg
  (off 0.001) inherited from v216.GRID via pof.pipe_setup (M5 be_moves
  1201 pooled). V1/V2 override ONLY be_k/be_off to 0.75/0.0 and 0.50/0.0
  (earlier, to exactly entry); the dip BE (none in M5) is added by the
  patched touch exit. Everything else is exactly M5_human.

## 2. Method (BE rule only; entries/stops/timeouts/fees unchanged)

- Book: trade dict = v367 trade + be_k=BE_K + be_off=0.0; trigger =
  entry*(1+side*BE_K*sdv), sdv = sigma_d at entry; touch detection
  (long high>=trig / short low<=trig), causal, only in position (never
  before entry fills); amend SL -> exactly entry once (T[be] flag, never
  loosened); TP 10.0sg unchanged; priority stop, TP, scale, partial, BE.
- Dip (make_be_simulate, audited inspect.getsource pattern cf.
  oc_manualsplit): per taken long rung lv/sg/m0/sl unchanged (m0 from the
  bar-open R2 table, sl 8.0sg touch); be_trig = lv*(1+BE_K*sg),
  be_stop = lv; tb = first high>=be_trig in f+1..end-1; ks/kt = first
  base stop/TP in the same window (stop touch <=sl, TP strict >tp); BE
  arms IFF tb exists and tb<ks and tb<kt (tie -> base, trigger minute
  uses sl); if armed, BE-stop (low<=be_stop, taker, min(be_stop,open))
  vs TP (strict, maker), stop-first, else timeout (taker+funding); one
  amend per rung; budget 0.26 counted once at the initial stop.
  BE-stop exits emit rung_sl with be=True (labelled); stats be_armed /
  be_exits / be_moves.
- Bybit: resting GTC limits + attached OCO TP/SL at placement + single
  reduce-only SL amend; no re-pegging. M5_human uses unpatched eu.simulate.

## 3. Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | V1_BE075 R | V2_BE050 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.783 | 1.167 | 16.54 | 13.46 | 12.47 |
| 2022-09-24 | 1.585 | 2.253 | 2.279 | 17.94 | 17.71 | 16.91 |
| 2023-09-24 | 4.413 | 3.791 | 3.359 | 17.36 | 17.74 | 16.36 |
| 2024-09-24 | 7.948 | 6.947 | 6.161 | 8.24 | 7.84 | 7.16 |
| 2025-09-24 (POST-RELEASE) | 3.994 | 3.125 | 3.403 | 11.69 | 11.98 | 9.29 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| V1_BE075 | 3.360 | 0.783 | 17.74 | 17.70 | 3.418 | 0.783 | 17.74 | 3.125 |
| V2_BE050 | 3.261 | 1.167 | 16.91 | 16.83 | 3.225 | 1.167 | 16.91 | 3.403 |

Trades/wins (pooled 4 phases; book via v213.trade_stats, rung via ret>0):
- book: M5 3744 @.6482, V1 5370 @.4082, V2 6571 @.3144.
- yearly book win M5 .6429/.6264/.6395/.6402/.6837; V1
  .4549/.3944/.3476/.4269/.4319; V2 .3721/.2909/.2569/.3224/.3458.
- rung: M5 6417 @.7013, V1 6507 @.5921, V2 6569 @.4859.
- yearly rung win M5 .6322/.6903/.7679/.7365/.6701; V1
  .5199/.6102/.6400/.6087/.5755; V2 .4208/.4920/.5287/.4973/.4824.
- all-trade win: M5 .6817, V1 .5090, V2 .4002.
- BE diagnostics pooled: dip armed M5 0 / V1 3417 / V2 4449; dip BE exits
  0 / 1144 / 2261; book BE moves (sl_move break-even) 1201 (M5 at 2.0sg)
  / 3544 / 5049; engine be_moves 1201 / 3541 / 5048.
- MANUAL gate (R5>=5, fullDD<20, book win>=55%): M5 fails R5 only;
  V1/V2 fail R5 AND book win (fullDD passes all).

Deltas vs M5 (dev4, the only selection ground):
- V1: Rdev4 -0.243, Wdev4 -0.064, DDdev4 -0.20, fullDD -0.09, Rlast -0.869.
- V2: Rdev4 -0.436, Wdev4 +0.320, DDdev4 -1.03, fullDD -0.96, Rlast -0.591.

Selection (dev4 only): both V1/V2 satisfy DD<=20 with no losing dev year;
neither reaches mean>=5, so the pool is both; highest Wdev4 is V2 (1.167
vs 0.783). PICK = V2_BE050.
MANUAL gap to 5 %/month (M5 R5 3.728, gap 1.272pp): V1 R5 3.360 closes
-0.368pp (widens to 1.640pp); V2 R5 3.261 closes -0.467pp (widens to
1.739pp). The pick does NOT close the gap.

## 4. Leakage audit

- feature timing: BE levels use only entry + sigma known at the bar
  open/decision (book sigma_d, dip sigma_4h, R2 size/TP tables bar-open
  keyed); the trigger mark uses only 1m high/low <= the amend minute
  (patched code uses Ha/La up to the current minute; tb strictly before
  ks/kt; trigger minute uses sl; search after tb starts at tb+1);
  causality test bans fill-minute/future markers; synthetic tests check
  strict-before arming, the tie-to-base rule and the trigger-minute rule;
  no 1m data enters any placement decision.
- label windows: no new labels; no outcome enters any sizing or amend rule.
- fit windows: no fits/thresholds/quantiles; BE_K/BE_OFF frozen ex-ante
  (0.75/0.50/0.0); coin set, sigma/TP distances, schedule frozen (M5);
  no test-year statistic feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open; BE never arms before its fill and never re-arms.

## 5. Notes (why it failed)

- Same failure mode as CLOSED oc_dipbe (BOT dip BE, sum 0/5): the early
  trigger fires on most brackets (V1 3417 armed / 1144 BE exits; V2 4449
  / 2261; book BE moves 3544/5049 vs M5 1201) and converts runners into
  scratches that net -fees (book win .6482 -> .4082/.3144; rung win
  .7013 -> .5921/.4859; all win .6817 -> .5090/.4002). The tail improves
  only -0.2/-1.0pp DD while the mean loses -0.24/-0.44pp dev4.
- The only green cell is V2 Wdev4 +0.32pp (worst year 0.847 -> 1.167),
  bought with -0.44pp mean and -33pp book win: not a trade a human would
  take, and the clean year is worse (-0.87/-0.59pp vs M5).
- No post-hoc change to BE_K/BE_OFF, prices, windows, budgets or the
  dev4-only rule. All five years ran in one pass (oc_manualcap precedent);
  the last year is POST-RELEASE context only.

## Verdict

V2_BE050 (pick) R5 3.261 closes -0.467pp of the 1.272pp MANUAL gap (gap
widens to 1.739pp); V1 closes -0.368pp. Earlier break-even protects the
tail (-1.0pp DD) but whipsaws runners (book win -33pp): reject the
one-move-BE direction for MANUAL, keep M5_human.

Break-even som dua SL ve entry chi bao duoc duoi nhe (-1,0pp DD) nhung cat cu dan chay nen win sup manh va loi nhu an giam: loai.
MANUAL van thieu ~1,74 diem %/thang so voi san 5 %, giu M5_human, dong huong BE mot lan.
Can bang chung prospective cung khong doi duoc ket luan nay: khong dua V1/V2 vao san xuat.
