# mj W17 audit: blind replication vs leader TSMOM portfolio (Part B)

## A. Blind number (saved BEFORE reading leader code)
`research/mj_audit/replication.json`: **net +188.56%, max DD -21.47% (4h equity),
turnover 0.538/day**, window holding bars `[2023-09-24 00:00, 2024-09-22 20:00 UTC]`
(2190 bars = 365.0 days), start flat, equity compounds from 1.0 to 2.885598.

## B. Leader reference (read only after A was saved)
`artifacts/research/mj/tsmom_portfolio/BTC_ETH_SOL_BNB_XRP.json`, anchor `2023-09-24`
selected `{horizons:(7,30), shorts:false, target_vol:0.3, max_gross:3.0, band:0.05,
dd_cut:null}` (= the spec config), forward `normal`:
**net +192.2%, monthly 9.38%, sharpe 2.64, DD 21.5%, turnover 0.53/day**.

## C. Rerunning the leader code (`scripts/mj_tsmom_portfolio.py` weights+simulate)
| window | n | net% | DD% | turnover/day | equity end |
|---|---|---|---|---|---|
| leader fwd `[2023-09-24 00:00, +364d = 2024-09-22 00:00]` | 2185 | 192.2 | 21.5 | 0.53 | 2.921978 |
| spec text end `2024-09-22 20:00` | 2190 | 188.6 | 21.5 | 0.54 | 2.885598 |

Leader-on-leader-window reproduces the artifact **exactly** (192.2/21.5/0.53/sharpe
2.64/monthly 9.38). Leader-on-spec-window reproduces the blind number **exactly**
(equity 2.885598 both, period net series equal to 1.4e-14, turnover 0.5380 both).

## D. Difference > 1 pp: root cause
**Gap = 192.2 - 188.6 = 3.6 pp, root cause is window-end convention only.**
Leader forward = `[anchor, anchor+364 days]` = ends 2024-09-22 00:00 (2185 bars);
spec text window ends 2024-09-22 20:00 (2190 bars). The 5 extra bars
(00:00->20:00 on 2024-09-22) drag equity 2.922 -> 2.886 (~-1.2% relative).
All economics (signal, vol, scale, cap, band, cost, funding) replicate exactly,
proven by the 1e-14 period agreement. No methodological difference remains.
Secondary (0 pp impact): leader indexes equity by decision bar `t`, blind by holding
bar `h=t+1` -- a pure 1-bar label shift of the identical return series.

## E. Look-ahead audit of leader code (all clear)
- Signal (`lc - lc.shift(h*6)`, h in (7,30)): past closes only. Causal.
- Vol (`r.rolling(180).std()*sqrt(6*365)`, ddof=1) and `raw=sig/vol` (fillna 0):
  trailing window ending at t. Causal.
- Portfolio scale (`port_r=raw.shift(1)*r`, `pvol` trailing 180/min 60,
  `scale=min(0.3/pvol,10)`, gross cap 3): all backward-looking; NaN pvol ->
  scale NaN -> weights fillna(0). Causal.
- Daily ribbon join (`rib` indexed by daily close_time, `reindex(4h close_time,
  ffill)`): last daily with close_time <= 4h close_time = last CLOSED daily.
  `rib==-1` iff `close<SMA50<SMA200`, and long-only gating zeroes exactly those
  longs -- identical to the spec filter. Causal. (`btc_gate` absent in 2023 config.)
- Funding (floored to 4h, grouped, `shift(-1)` in simulate): weight t pays rates
  inside bar t+1, as specified. Causal.
- Execution (`o.shift(-2)/o.shift(-1)-1`): decision t earns bar t+1; 1-bar delay
  per AGENTS.md rule 2. Union alignment gives missing assets weight/return 0.
  Cost 0.0002*sum|dw|, band strict `> 0.05`. As specified.
- `weights()` runs over full history but every operator is trailing-only, so no
  forward data enters any decision.

## F. Non-blocking observations
- Selected 2023 config reports train DD 23.7% > the code's 20% MAX_TRAIN_DD
  constraint (argmax over all-penalized grid); forward year unaffected.
- Leader `net_pct`/`turnover_per_day` are rounded (1/2 dp); blind keeps full precision.
- BTC bars/funding identical across both sources (`load_bars` reads the same
  `ma_ribbon_20260924` file; XS vs ma_ribbon BTC funding diff is 0.0).
