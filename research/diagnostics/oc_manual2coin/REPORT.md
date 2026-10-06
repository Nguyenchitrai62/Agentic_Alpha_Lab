# oc_manual2coin REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup
Exact oc_manualcap M5_human harness (M5 = v367, 15-min reaction, night bar
skipped, agents ON per-phase R2 tables, 5 research years 2021-09-24..2026-09-23,
reset metric per year + v388.mix full-path DD). Rows: (a) M5_human reference,
(b) dip brackets ONLY on SOL+XRP (book unchanged on all five), (c) same as (b)
with bracket size x5/2 = 2.5 on SOL+XRP, same gross limits (budget 0.26 /
vol-cap / governor unchanged, no sleeve_gross_cap hook). Pool(1) sequential
via heavy_slot tag oc_manual2coin. Repro: this folder (PLAN.md,
oc_manual2coin.py, results.json).

Wiring check: (a) M5_human R5 3.728 / maxDD 17.94 / fullDD 17.79 / book win
.6482 / rung fills 6417 reproduces oc_manualcap M5_human (3.73 / 17.9 / 17.8 /
.648 / 6417) exactly. Direction proceeds per PLAN.md.

## Primary table (reset metric; R in %/month, DD in %)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | y4 R/DD | R5 | W | maxDD | fullDD (1m/4h) | book win pool (n) | rung win pool (n) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) M5_human | 0.85/16.5 | 1.59/17.9 | 4.41/17.4 | 7.95/8.2 | 3.99/11.7 | 3.73 | 0.85 | 17.9 | 17.8 (17.79/16.79) | .648 (3744) | .701 (6417) |
| (b) 2coin x1.0 | 0.86/11.7 | 2.71/15.3 | 2.66/15.8 | 6.47/6.0 | 3.58/7.7 | 3.24 | 0.86 | 15.8 | 17.1 (17.11/15.88) | .651 (3808) | .740 (2495) |
| (c) 2coin x2.5 | 0.27/18.1 | 0.96/20.2 | 3.92/15.8 | 7.50/7.7 | 4.45/9.2 | 3.39 | 0.27 | 20.2 | 24.3 (24.30/23.99) | .642 (3595) | .732 (2041) |

Book win by year: (a) .643/.626/.640/.640/.684; (b) .653/.640/.621/.643/.689;
(c) .647/.592/.624/.637/.686. Dip win by year: (a)
.632/.690/.768/.737/.670; (b) .654/.764/.777/.783/.715; (c)
.634/.746/.797/.763/.715. Rdev4/Rlast: (a) 3.66/3.99; (b) 3.15/3.58;
(c) 3.12/4.45. win_all: .682/.686/.674. No losing year anywhere.

## Human load (mean over 4 phases; one clock = one human; 1825 days, 9120 active bars)
- Book limit placements (empirical `order_issue`): (a) 1.22/d, (b) 1.25/d,
  (c) 1.19/d — unchanged, as designed (book untouched).
- Dip bracket placements (theoretical, every active bar places full ladder =
  active x coins x 2 rungs / day): (a) 50.0/d (5 coins), (b)/(c) 20.0/d
  (2 coins) — ratio 0.40, the intended load cut.
- Dip fills (empirical `rung_fill`): (a) 0.88/d, (b) 0.34/d, (c) 0.28/d.
- Total human placements per day (book + dip brackets): (a) ~51/d,
  (b)/(c) ~21/d. The concentration thesis delivers the load saving; it does
  not deliver return.

## Minimum-notional feasibility at 5,000 USDT (E = 1250/phase, oc_lots rules, no network)
- Book (5-coin on ALL rows, BTC bottleneck stays): placeable share (a) 94.6%,
  (b) 94.7%, (c) 94.3%; per-coin BTC ~72-74%, ETH/SOL/BNB/XRP 100%.
- Dip: (a) 99.2% overall (BTC 97.2 / ETH 99.0 / SOL 99.9 / BNB 100 / XRP 100);
  (b) 99.4% on SOL 99.2 / XRP 99.6 (BTC/ETH/BNB absent by construction);
  (c) 100% (2.5x notionals clear the 5 USDT floor everywhere, n=2040).
- Reading: at 5000 USDT the 2-coin dip ladder is fully placeable, but the
  BOOK still leaves ~5-6% of orders (all BTC) unplaceable — same as the
  reference. Feasibility does not block (b)/(c) dips; it does not fix books.

## Verdict vs the MANUAL floor (R5 >= 5, fullDD < 20, pooled book win >= 55 %)
- (a) M5_human: NO (3.73 / 17.8 PASS / .648 PASS) — return shortfall only.
- (b) M5_human_2coin: NO (3.24 / 17.1 PASS / .651 PASS) — return WORSE than
  the reference by ~0.5pp; yearly DD max improves (17.9 -> 15.8) but
  full-path DD barely moves (17.8 -> 17.1). Dip win rises (.701 -> .740) but
  rung count collapses (6417 -> 2495): the removed BTC/ETH/BNB rungs carried
  P&L, and SOL/XRP alone do not replace it.
- (c) M5_human_2coin_x25: NO (3.39 / 24.3 FAIL / .642 PASS) — return still
  ~1.6pp short AND DD fails outright (yearly max 20.2 in 2022, full-path
  24.3). Re-spreading 2.5x into two coins concentrates the crash tail instead
  of diversifying it — the opposite of the fill-rate thesis.
- No row reaches the MANUAL floor. Plain conclusion: fixed two-coin bracket
  focus does not close the ~1.3pp return gap; the x2.5 re-spread buys tail
  risk, not return. This is the second-to-last MANUAL attempt: one shot left;
  it must add entry edge, not reshuffle coins or size.

## Caveats / log
- Post-hoc fix logged: `geom5_from_reset_R` first divided a 4-year product by
  60 months instead of 48 (Rdev4 printed 2.92/2.52/2.49); corrected to
  1/(12*n) and results.json Rdev4 patched to 3.66/3.15/3.12 WITHOUT rerunning
  the engine (yearly R untouched; R5/fullDD/wins/load/feasibility unaffected;
  script fixed for audit). Rdev4 3.66 now matches oc_manualcap exactly.
- Dip placements are theoretical (full ladder every active bar); fills are
  empirical. Feasibility uses live-window `order_issue`/`rung_fill` notionals
  pooled over phases at E=1250 (oc_lots method); FIFO P&L attribution not
  repeated (see oc_lots for the method reference).
- All five years are research data (assignment override); nothing here is
  prospective evidence.
