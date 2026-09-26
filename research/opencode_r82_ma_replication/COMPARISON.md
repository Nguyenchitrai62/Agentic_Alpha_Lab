# R82 Comparison: blind replication vs leader `ma_ribbon_r1/report.json`

Blind replication saved first at `research/opencode_r82_ma_replication/replication.json`
(own code only: `replicate.py`). Only then was
`artifacts/research/ma_ribbon_r1/report.json` opened. Numbers below were NOT
adjusted to match.

## 0. Inputs agree; signals agree

- Data hashes identical: `klines_1d` `b1beaf1c…`, `funding` `3faeef4a…`.
- SMA50/SMA200 logic identical: every holdout trade (side, entry/exit date,
  entry/exit price) matches the leader `trade_log` exactly for all five rows
  (buy_hold 1 trade; H1 2; H2 3; H3 4; H4 14). **No trade-list mismatches.**
- Trade counts match everywhere (dev: 1/6/12/32/59; holdout: 1/2/3/4/14).

So all >0.5pp differences are equity-accounting differences, not signal bugs.

## 1. Net % differences (rep − leader, pp)

| row | dev normal | dev stress | holdout normal | holdout stress |
|---|---|---|---|---|
| buy_hold | 477.68 − 744.91 = **−267.23** | 476.64 − 743.14 = **−266.50** | −33.26 − (−33.30) = +0.04 | −33.38 − (−33.42) = +0.05 |
| H1_cross_long | 443.70 − 444.34 = **−0.64** | 437.86 − 438.30 = −0.44 | −12.40 − (−12.64) = +0.24 | −12.71 − (−12.95) = +0.24 |
| H2_cross_long_short | 22.54 − 9.31 = **+13.22** | 19.91 − 6.28 = **+13.63** | −10.85 − 1.97 = **−12.82** | −11.33 − 1.46 = **−12.79** |
| H3_ribbon_long | 736.69 − 750.31 = **−13.62** | 689.82 − 702.54 = **−12.71** | 2.88 − 2.86 = +0.02 | 2.15 − 2.13 = +0.02 |
| H4_ribbon_long_short | 367.02 − 486.81 = **−119.79** | 319.93 − 426.88 = **−106.95** | 23.56 − 31.26 = **−7.70** | 20.48 − 28.07 = **−7.59** |

Intrabar max-DD diffs (rep − leader, pp): buy_hold dev **−10.83**,
holdout −1.88; H1 dev −1.90, holdout −0.22; H2 dev −2.89, holdout **+3.01**;
H3 dev −0.29, holdout −0.05; H4 dev **+5.79**, holdout **+3.94**.
Fees/funding levels differ accordingly (e.g. buy_hold dev funding: rep
178.7 vs leader 271.4 equity points; implied gross 656 vs 1016.5).

## 2. Root cause (mine wrong, leader correct)

**R1 — position sizing / compounding (dominant).**
Protocol: "fixed 1x of current equity **at entry**, compounded".
Leader (`ma_ribbon.py::backtest`): at entry sets `qty = equity/px` once;
while the trade is open equity is `cash + pos*qty*(price − entry)`; funding
is paid from cash but `qty` never changes until exit. Cross-trade compounding
only.
Mine (`replicate.py`): re-anchored notional to current equity on **every**
bar (`equity_open_next = equity_open_post*(1+pos*ret_oo) − funding`). That is
daily-rebalanced constant leverage, not fixed-at-entry.

Consequences, proven by minimal examples:

- Longs: without intermediate cash flows both telescope identically, but with
  0.0003/day funding over a 6-year bull market the paths diverge badly:
  mine pays funding out of exposure (future gains accrue on reduced equity),
  leader pays out of cash (future gains accrue on full `qty`). Hence buy_hold
  dev gross 656 vs 1016.5 and funding 178.7 vs 271.4. Over the 1-year holdout
  the same effect is only 0.04pp — consistent, not a separate bug.
- Shorts: `(1 − ret)` does NOT telescope, so daily rebalancing adds volatility
  drag on top. Minimal proof: price 100 → 50 → 100. Fixed-qty short
  (entry 100, exit 100): PnL 0, final 100. Daily-rebalanced short:
  100·(1+0.5) = 150, then 150·(1−1.0) = **0** (−100%). This is exactly why H2
  holdout flips sign (−10.85 vs +1.97) despite identical trade lists, and why
  H4 gaps (±100pp dev, 7.7pp holdout) dwarf the long-only gaps.

**R2 — funding base (minor, mine wrong).**
Mine: `funding = equity_open_post · 0.0001 · count` (open notional).
Leader: `f = 0.0001 · count · qty · close` (close notional).
Same event counts (file-based `[open, next_open)`), different intrabar mark.
Explains part of the residual on long-only rows (e.g. H1 dev −0.64pp).

**R3 — slippage/fee mechanics (minor, equivalent by design).**
Mine folds stress slippage into the per-fill rate (0.0011 on equity).
Leader shifts execution prices (`open·(1±slip)`) and charges exit fees on exit
notional. Same direction, second-order size; not the driver.

**R4 — intrabar-DD peak definition (minor, definitional).**
Mine takes peak-to-trough over all sampled points (open/worst/close).
Leader (`summarize`/`max_drawdown`) takes troughs from `worst` but peaks from
`equity` closes only. Same inputs, different peak set; contributes fractions
of a pp on long-only rows and more wherever R1 already moved the curve (H4
dev +5.79pp, H2 holdout +3.01pp).

## 3. Leader-engine audit (no change made)

`moving_average`, `ribbon_target` (SMA, `cross`/`ribbon`, warm-up → flat),
`funding_per_bar` (`[open_i, open_{i+1})` assignment), fill-at-next-open,
2-fill reversals, liquidation at close of `end+1`, normal-vs-actual funding
modes all read correct against the protocol. One known approximation (shared
by mine): early bars before the first `fundingTime` accrue zero funding rather
than a scheduled 3/day — worth ~0.06pp, not material. No leader bug found
that explains any >0.5pp gap; every large gap traces to R1 in my file.

## 4. Verdict

- Signals reproduce exactly; engine does not. My `replication.json` net/DD
  values for multi-trade and especially short-inclusive rows are biased by
  daily rebalancing and must NOT be cited as protocol results.
- Leader `report.json` stands for H1–H4/buy_hold normal+stress. Per the
  assignment the replication numbers are left as-is.
