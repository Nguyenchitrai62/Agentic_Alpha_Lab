# oc_fundclock REPORT — IDEAS5 §5 funding-clock flatten (2026-10-08; pytest 4/4)

Rule (frozen PLAN.md): predicted funding proxy P(S,sym) = 60m premium-1m TWAP ending
1h before settlement S (bars [Sf-120m,Sf-60m), >=30 bars else NaN; settled history
alone has no predicted series, so the premium leg from the IDEAS5-named folder
`data/raw/binance_premium_20260928` is the operationalised predicted input
(same substitution `oc_idea4` disclosed pre-run; timestamped S-1h, causal).
Per-anchor-coin q90 over settlements in [A-97d,A-7d) (90d + 7d embargo, >=50 else
never flag); flag iff P(S) > q90. W1/W2: flagged settlement's coin book LONG x0.5
at bar T=S (after exact v421 bear filter, before ffill; shorts untouched). W1 adds
dip tilt 0 on holding bars starting at flagged S (causal post-leg of the +-30min
window; the pre-settlement half needs intrabar cancel the per-bar engine cannot
express — disclosed approximation; exits unchanged). W2 dip untouched. Re-enter next
signal (engine limit/maker). CLOSED rows read: `oc_bookfunding` (7d LEVEL tilt,
NOT PROMISING) and `oc_idea4` (funding-SURPRISE dip filter, NOT PROMISING) — both
level/surprise tilts; this is settlement-CLOCK timing, so kept.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82, asserted in-script).
Stage dev (12 sims: REF/W1/W2 x4) + stage last (8 sims: REF+W2 ONCE) complete.

## Gates (causal; rows < 2021-09-24 never gated; no anchor-year skip needed, pools 255-270)

q90 premium-TWAP per anchor (BTC/ETH/SOL/BNB/XRP): 2021 (+69/+81/+101/+98/+94 bps,
bull-regime premium) then 2022-2025 mostly negative (-33..-16 bps, BNB positive) —
frozen trailing-90d thresholds do not transfer (same non-stationarity as
`oc_bookfunding`/`oc_idea4`). Flagged (T,sym) cells per year: 170 / 1332 / 2557 /
1390 / 80 (IDEAS5 expected ~30-60 events/yr; realized 3%/24%/47%/25%/2% of settlement
cells; 2025 gate nearly off — funding feed ends 2026-08-31). Total 7540/36525 (20.6%).
Book gated long rows 8572 (all phases). Dip exact-start gated share of sized fills per
dev year: 0.5% / 4.4% / 8.2% / 4.6% (dip fires only on phase-0 bars by clock
construction — shifted-phase bars never start exactly at a settlement; disclosed).

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| W1 | 2.562/10.82 | 3.019/15.05 | 7.199/14.42 | 10.340/10.87 | 5.732 | 2.562 | 15.06 | 15.06 |
| W2 | 2.590/10.82 | 3.345/15.10 | 8.215/14.02 | 10.711/10.82 | 6.162 | 2.590 | 15.19 | 15.19 |

Book win (dev): REF .503/.516/.519/.508; W1 .492/.512/.518/.507; W2 .492/.510/.521/.509.
All-win: REF .613/.658/.697/.671; W1 .610/.653/.695/.661; W2 .610/.657/.697/.664.
W2 beats REF on dev4 mean (+0.56), WORST (+0.002) and DDmax (-1.72); W1 trails W2 on
mean (-0.43) and WORST (-0.028) — the dip-cancel leg costs return for no DD buy
(dev DD 15.06 vs 15.19).

Robust pick on dev4 ONLY among W1/W2 (DD <= 20, no losing, prefer mean >= 5, highest
WORST): W2 (2.590 > 2.562; both mean >= 5).

## Most-recent-year verdict (clean; scored ONCE for the dev4 pick W2 + REF, labelled)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 | 0.6267 |
| W2 (pick) | 4.488 (-0.160) | 13.02 | 15.19 | 5.825 | 0.5351 | 0.6260 |

W2 trails REF by -0.16 in the clean year (gate nearly off: only 80 flagged cells) and
its 5y (+0.415) comes entirely from dev years 2022-2023 where the frozen thresholds
let half the settlement grid through. Gate check for W2: (a) 5y 5.825 >= 5 YES;
(b) most-recent-year 4.488 >= 5 NO; (c) no losing year YES; DD 15.19 <= 20 YES —
FAILS (b). No losing year anywhere; DD <= 20 everywhere. W1 unscored in the clean
year per protocol (only pick + REF).

## Leakage statement

Feature timing: premium bars ending <= S-60m only (P(S) timestamped S-1h; gate at T=S
uses data <= S-1h < T; truncation-tested in tests/test_oc_fundclock.py). Label
windows: none (unsupervised quantiles only). Fit windows: q90 from [A-97d,A-7d) per
anchor-coin, frozen per year, 7d embargo; no statistic from any test year feeds any
choice. Fill timing: win_start=5 + 1m trade-through + stop-first inside the engine.
Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h).

## Caveats / post-hoc log

1. TWAP half-open bound clarified to [Sf-120m,Sf-60m) (same 60 bars as PLAN) before
   any outcome (unit-test fix, no threshold/variant change).
2. One code-only plumbing fix before any SCORED outcome: run_engine dip leg indexed
   the gate array in the wrong coin order (gate_grid vs books column order); fixed to
   name-mapped indexing. Intermediate per-shift eq prints were seen, then the full dev
   stage was re-run from scratch; gates/thresholds/variants unchanged. Original buggy
   shift-0 W1 eq (12.91) replaced by fixed (14.72); scored tables are all post-fix.
3. No post-hoc change to definitions, thresholds, variants, or the decision rule.
4. All five years were available when scored; findings need prospective validation.

## Vietnamese verdict

REJECT adopt — W2 hơn REF ở dev4 (+0,56 mean, DD −1,7) nhưng năm sạch scored-once thua
REF −0,16 (4,49% so với 4,65%, không đạt mốc 5%) và cửa sổ p90 đông cứng trôi mạnh theo
chế độ (2023 flag 47% lưới, 2025 chỉ 2%): timing theo-clock không mang alpha bền.
W1 (kèm hủy dip) còn tệ hơn W2 ở cả mean và WORST nên dip-cancel không có giá trị;
đóng hướng này lại, giữ W2 làm bằng chứng prospective nếu cần.
