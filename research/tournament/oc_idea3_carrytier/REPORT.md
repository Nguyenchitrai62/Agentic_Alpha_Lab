# oc_idea3_carrytier REPORT — tiered carry sizing by locked basis (IDEAS_20261007 §3)

PRE-REGISTRATION (frozen BEFORE any run; no other variants):
- T1 tiered per-coin f by locked ann. basis: 4-6% -> 0.125, 6-10% -> 0.25, >10% -> 0.375.
- T2 = T1 capped at f=0.25 per coin (account-check per oc_utamargin: f=0.25 is the largest cleared additive f).
- Selection ONLY on dev years 2021-2024 (robust criterion: DD<=20 + no losing dev year; prefer dev4 mean>=5, then highest dev4 WORST year). Most recent year 2025-09-24..2026-09-23 scored ONCE for the chosen variant only. All years POST-HOC (reuses frozen oc_cashcarry/oc_carrycompound trades that already saw all years).
- Baseline gate: reproduce G2 (5.41) and G2+carry f=0.25 compound (5.634 / DD 16.75 / full 16.66) exactly first, else STOP.

## Method (sleeve accounting like oc_cashcarry, no engine)

Verbatim oc_carrycompound ONE-account compounding: A(t)=A(t-1)*(1+r_bot(t))+dU(t),
r_bot from stored 4-phase G2 mix R2B1D17BFG2 (UTA: BOT sizes on TOTAL equity),
carry notional N_k=f_k x A at each entry, held to delivery; causal hourly marks
(last CLOSED hourly bar strictly before t, 0 before entry-close, locked to frozen
ret_alloc); spanning carry rebased to 0 at each anchor; per-year reset to 1.0 =
reset_metric.year_reset arithmetic; full-path DD continuous from grid start with
the v421 formula (max of marked/close DD). 33 frozen oc_cashcarry trades reused
verbatim (entry rule/threshold/fees/deliveries untouched; basis annualised from
<=entry closes only; 2 incomplete contracts excluded, no P&L imputed; rate buckets
pre-frozen: b<0.06->0.125, b<=0.10->0.25, else 0.375). Tier census: T1 = 8x0.125 /
10x0.25 / 15x0.375; T2 = 8x0.125 / 25x0.25. Repro:
`research/tournament/oc_idea3_carrytier/analyze_carrytier.py` (hourly 4h+1h grid
~44k rows, no 1m, no engine reruns) + `tests/test_oc_idea3_carrytier.py`.
Gate costs: BOOK legs inside the stored G2 path already carry gate costs (maker
0.02% / taker 0.055%, longs pay 0.01%/8h); carry leg keeps the frozen fee drag
0.00275/alloc (spot 0.001/side + fut 0.00055 entry + 0.0002 delivery); delivery
quarterlies pay NO funding, so the perp-funding gate rule is irrelevant here
(same statement as oc_cashcarry). Not a book idea: no 4-phase engine re-run needed;
book legs are the frozen v421 4-phase path, judged never by vectorised screen.

## Baseline gate: PASSED (else would have stopped)

- f=0 reproduces v421_result G2 TO THE DIGIT: R 5.41 / W 2.588 / DD 16.91 /
  full-path 16.82 (marked 16.82 / close 16.05), years 2.588/3.282/6.045/10.677/4.648.
- flat f=0.25 reproduces oc_carrycompound TO THE DIGIT: R 5.634 / W 2.778 /
  DD 16.75 / full-path 16.66 (marked 16.66 / close 15.90), carry add +0.224pp.

## Dev years 2021-2024 ONLY (selection ground; POST-HOC)

| variant | 21-22 | 22-23 | 23-24 | 24-25 | dev4 mean / WORST / maxDD / losing |
|---|---|---|---|---|---|
| flat f=0.25 (ref) | 2.778/10.86 | 3.353/16.75 | 6.590/15.69 | 10.956/8.20 | 5.870 / 2.778 / 16.75 / 0 |
| T1 tiered | 2.836/10.86 | 3.345/16.75 | 6.835/15.63 | 10.947/8.20 | 5.941 / 2.836 / 16.75 / 0 |
| T2 capped 0.25 | 2.776/10.86 | 3.345/16.75 | 6.577/15.69 | 10.897/8.20 | 5.850 / 2.776 / 16.75 / 0 |

Robust criterion: both T1 and T2 satisfy DD<=20 + no losing dev year, both dev4
means >= 5 -> pick highest dev4 WORST year: T1 (2.836 > 2.776). Winner on dev
only: T1. T1 vs flat on dev4: +0.071pp; T2 vs flat on dev4: -0.020pp (capping
surrenders the high-basis lift). 2025 rows for the loser are NOT scored (blank by design).

## Most recent year 2025-09-24..2026-09-23: scored ONCE, winner T1 only (POST-HOC)

- T1 2025: R 4.694 / DD 12.66 (flat f=0.25 ref 4.698/12.66 — tiering adds nothing
  in 2025: only 1 low-basis trade entered, f=0.125 vs 0.25 shrinks it).
- T1 5y (POST-HOC, winner only): R 5.691 / W 2.836 / DD 16.75 / losing 0 /
  full-path DD marked 16.66 / close 15.90 / full 16.66. Lift over flat f=0.25:
  +0.057pp/mo at identical DD (within the pre-registered +0.03-0.08 expectation).

## Account-check per oc_utamargin (max simultaneous open pairs, indexed spot cost)

- flat f=0.25: 4 pairs / 1.00 (cleared envelope: 0 blocked hrs, spot peak 95.8% Eq).
- T2: 4 pairs / 1.00 — inside the cleared envelope, additive OK on one UTA.
- T1: 4 pairs / 1.50 — indexed spot cost 150% of equity at peak overlap: the USDT
  wallet MUST borrow (same structural failure as f=0.50 at 179.9% and the stacked
  top-up at 1.15). T1 is NOT additive-safe on one account; above 0.25 means SPLIT
  CAPITAL ONLY (unmodelled borrow interest, same caveat as oc_utamargin f=0.50).

## Leak audit

Features at t use only <=t closes (oc_cashcarry resample: last 1h bar with open_time
< spot close_time; hourly marks last CLOSED bar strictly before t); labels/returns
locked to frozen ret_alloc net of fees; no statistic of any test year feeds any
choice (buckets pre-frozen, trades frozen); fills at t+1-style timing inherited
from oc_carrycompound (entry at live A after entry-close, no look-ahead). All five
years were already seen by the reused frozen inputs -> every row labelled POST-HOC;
a prospective paper log is the only clean evidence left.

## Verdict

REJECT as an adoptable change: the dev-selected T1 adds only +0.06-0.07pp/mo at
flat DD (5.691 vs 5.634, DD 16.75/16.66 unchanged — still ~2.3pp short of the 8%
BOT goal and above the DD<15 stretch), and T1 breaches the UTA cash envelope
(indexed 1.50, must borrow) while the envelope-safe T2 is neutral-to-negative vs
flat on dev4 (-0.02pp). Direction closed: no further sizing/threshold work on this
sleeve; keep the flat f=0.25 carry overlay + grow prospective paper evidence.

## Nhan xet tieng Viet (3 dong)
TU CHOI ap dung: T1 duoc chon tren dev4 (+0,07 diem %/thang, DD khong doi) nhung tran von UTA (chi phi spot 150% von, phai vay) nen khong chay cong them duoc.
T2 an toan (tran 0,25) nhung khong hon baseline flat (-0,02pp dev4); hieu ung qua nho (+0,06pp, van kem xa muc 8%/thang).
Toan bo la POST-HOC (tai su dung trade dong bang da thay ca 5 nam); can bang giay prospective neu muon tiep tuc, khong mo them bien the.
