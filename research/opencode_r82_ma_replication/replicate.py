"""R82 blind replication of MA-ribbon protocol (daily SMA50/SMA200).

Implements ONLY from configs/ma_ribbon_r1_protocol.json + assignment text.
No leader code was opened.

Execution model (documented assumptions):
- Decision at close(t) using closes <= t. SMA50(t)=mean(close[t-49..t]),
  SMA200(t)=mean(close[t-199..t]). If fewer than 50/200 bars, SMA=NaN -> flat
  (buy_hold stays long).
- Targets:
  buy_hold=1 always; H1=1 if SMA50>SMA200 else 0;
  H2=+1 if SMA50>SMA200, -1 if SMA50<SMA200 else 0;
  H3=1 if close>SMA50 and SMA50>SMA200 else 0;
  H4=1 if close>SMA50 and SMA50>SMA200, -1 if close<SMA50 and SMA50<SMA200 else 0.
  Equality -> flat.
- Fill at open(t+1). Holding bars = bars with date in (d0, d1+1d].
  Position during holding bar h = target(h - 1 day).
- Sizing 1x of current equity, compounded from 100.
- Costs: normal cost_per_fill=0.0002; stress=0.0006+0.0005=0.0011.
  Position change at a bar open: flat<->pos = 1 fill, long<->short = 2 fills.
  equity_open_post = equity_open_pre * (1 - n_fills*cost).
  Final liquidation at close of last holding bar costs 1 fill if pos != 0.
- Funding (both normal+stress, fixed assumption): long pays 0.0001 per 8h
  event, short 0. Events counted from funding.parquet rows whose fundingTime
  falls in [open(h), open(h+1)) for intermediate bars and [open(h), close(h)]
  for the final bar (i.e. the 00/08/16 UTC prints of that calendar date).
  funding_k = equity_open_post_fee * 0.0001 * n_events if pos==+1 else 0.
- Per-bar equity:
  ret_oc = close/open - 1; ret_oo = next_open/open - 1.
  equity_close_k = equity_open_post*(1+pos*ret_oc) - funding_k
  equity_open_next_pre = equity_open_post*(1+pos*ret_oo) - funding_k
  (gap return applied to post-fee equity; funding fully accrued by close).
- Intrabar worst mark: long -> bar low, short -> bar high, flat -> close path.
  equity_worst_k = equity_open_post*(1+pos*(worst/open-1)) - funding_k.
  intrabar_max_dd = max peak-to-trough over
  [open_post, worst, close, next_open_pre, next_open_post, ...].
  close_dd uses closes (+ open_pre/post fee points for correctness) only.
- Fees/funding reported as cumulative absolute deductions in equity points
  (starting capital 100). net_pct = (final/100-1)*100 after all costs.
- Trades: one entry per continuous non-zero position segment; reversal closes
  old and opens new at same open price. Final segment exits at close.
"""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "raw" / "ma_ribbon_20260924"
OUT_DIR = ROOT / "research" / "opencode_r82_ma_replication"

DEV = ("2019-09-08", "2025-09-13")
HOLD = ("2025-09-24", "2026-09-22")
ROWS = ["buy_hold", "H1_cross_long", "H2_cross_long_short", "H3_ribbon_long", "H4_ribbon_long_short"]
COSTS = {"normal": 0.0002, "stress": 0.0011}
FUND_RATE = 0.0001


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load():
    kl = pd.read_parquet(DATA_DIR / "klines_1d.parquet").sort_values("open_time").reset_index(drop=True)
    fu = pd.read_parquet(DATA_DIR / "funding.parquet").sort_values("fundingTime").reset_index(drop=True)
    kl["date_str"] = kl["open_time"].dt.strftime("%Y-%m-%d")
    kl["close_d"] = pd.to_datetime(kl["date_str"])
    kl["SMA50"] = kl["close"].rolling(50).mean()
    kl["SMA200"] = kl["close"].rolling(200).mean()
    return kl, fu


def target(row, name):
    c, s50, s200 = row["close"], row["SMA50"], row["SMA200"]
    if name == "buy_hold":
        return 1
    if pd.isna(s50) or pd.isna(s200):
        return 0
    cross_up = s50 > s200
    cross_dn = s50 < s200
    if name == "H1_cross_long":
        return 1 if cross_up else 0
    if name == "H2_cross_long_short":
        return 1 if cross_up else (-1 if cross_dn else 0)
    if name == "H3_ribbon_long":
        return 1 if (c > s50 and cross_up) else 0
    if name == "H4_ribbon_long_short":
        if c > s50 and cross_up:
            return 1
        if c < s50 and cross_dn:
            return -1
        return 0
    raise ValueError(name)


def max_dd(equities):
    peak = equities[0]
    mdd = 0.0
    for e in equities[1:]:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def simulate(kl, fu, d0, d1, row_name, cost):
    by_date = {d: i for i, d in enumerate(kl["date_str"])}
    i0, i1 = by_date[d0], by_date[d1]
    # holding bars: (i0+1 .. i1+1)
    h_idx = list(range(i0 + 1, i1 + 2))
    assert h_idx[-1] < len(kl), "missing bar after last decision"
    fu_times = pd.to_datetime(fu["fundingTime"], utc=True)
    equity = 100.0
    pos = 0
    fees = 0.0
    funding_paid = 0.0
    fills = 0
    curve_all = []
    curve_close = []
    trades = []
    open_trade = None  # dict side, entry_date, entry_price
    n_entries = 0

    # funding count helper per holding bar k
    opens = kl["open_time"]
    closes = kl["close_time"]
    for k, hi in enumerate(h_idx):
        h = kl.iloc[hi]
        dec = kl.iloc[hi - 1]
        tgt = target(dec, row_name)
        # arrival at open
        eq_pre = equity
        if k == 0:
            curve_all.append(eq_pre)
        else:
            # eq_pre already set from previous iteration as post-fee open
            pass
        nfill = 0
        if tgt != pos:
            if pos != 0 and tgt != 0:
                nfill = 2  # close + open
            else:
                nfill = 1
            fee = eq_pre * nfill * cost
            fees += fee
            fills += nfill
            equity = eq_pre - fee
            # close previous trade at this open
            if pos != 0 and open_trade is not None:
                open_trade["exit_date"] = str(h["date_str"])
                open_trade["exit_price"] = float(h["open"])
                trades.append(open_trade)
                open_trade = None
            # open new trade
            if tgt != 0:
                open_trade = {
                    "side": "long" if tgt == 1 else "short",
                    "entry_date": str(h["date_str"]),
                    "entry_price": float(h["open"]),
                    "exit_date": None,
                    "exit_price": None,
                }
                n_entries += 1
            pos = tgt
        eq_post = equity
        if k > 0 or nfill > 0 or True:
            # record post-fee open (for k==0 pre==post when no trade and buy_hold has trade)
            curve_all.append(eq_post)
        # funding events for this bar
        o = opens.iloc[hi]
        if k < len(h_idx) - 1:
            o_next = opens.iloc[h_idx[k + 1]]
            mask = (fu_times >= o) & (fu_times < o_next)
        else:
            c = closes.iloc[hi]
            mask = (fu_times >= o) & (fu_times <= c)
        nev = int(mask.sum())
        fund = eq_post * FUND_RATE * nev if pos == 1 else 0.0
        # price moves
        op, cl = float(h["open"]), float(h["close"])
        ret_oc = cl / op - 1.0
        eq_close = eq_post * (1.0 + pos * ret_oc) - fund
        funding_paid += fund
        # intrabar worst
        if pos == 1:
            worst = float(h["low"])
        elif pos == -1:
            worst = float(h["high"])
        else:
            worst = cl
        eq_worst = eq_post * (1.0 + pos * (worst / op - 1.0)) - fund
        curve_all += [eq_worst, eq_close]
        curve_close.append(eq_close)
        if k < len(h_idx) - 1:
            h_next = kl.iloc[h_idx[k + 1]]
            op_next = float(h_next["open"])
            ret_oo = op_next / op - 1.0
            eq_next_pre = eq_post * (1.0 + pos * ret_oo) - fund
            curve_all.append(eq_next_pre)
            equity = eq_next_pre
        else:
            equity = eq_close
    # final liquidation at close
    if pos != 0:
        fee = equity * cost
        fees += fee
        fills += 1
        equity = equity - fee
        curve_all.append(equity)
        curve_close.append(equity)
        if open_trade is not None:
            h = kl.iloc[h_idx[-1]]
            open_trade["exit_date"] = str(h["date_str"])
            open_trade["exit_price"] = float(h["close"])
            trades.append(open_trade)
            open_trade = None
    net_pct = (equity / 100.0 - 1.0) * 100.0
    return {
        "net_pct": net_pct,
        "final_equity": equity,
        "fees": fees,
        "funding": funding_paid,
        "fills": fills,
        "trades": n_entries,
        "intrabar_max_dd": max_dd(curve_all),
        "close_max_dd": max_dd([100.0] + curve_close),
        "trade_list": trades,
    }


def main():
    kl, fu = load()
    out = {
        "protocol": "configs/ma_ribbon_r1_protocol.json",
        "windows": {"development_decisions": list(DEV), "holdout_decisions": list(HOLD)},
        "costs": {"normal_per_fill": COSTS["normal"], "stress_per_fill": COSTS["stress"],
                  "stress_split": {"fee": 0.0006, "slippage": 0.0005},
                  "funding_per_8h_long": FUND_RATE, "funding_short": 0.0},
        "data": {
            "klines_1d": {"rows": len(kl), "sha256": sha256_file(DATA_DIR / "klines_1d.parquet")},
            "funding": {"rows": len(fu), "sha256": sha256_file(DATA_DIR / "funding.parquet")},
        },
        "assumptions": "see replicate.py docstring",
        "results": {},
        "holdout_trades": {},
    }
    for row in ROWS:
        out["results"][row] = {}
        for wname, (d0, d1) in (("development", DEV), ("holdout", HOLD)):
            out["results"][row][wname] = {}
            for cmode, cost in COSTS.items():
                r = simulate(kl, fu, d0, d1, row, cost)
                tl = r.pop("trade_list")
                out["results"][row][wname][cmode] = r
                if wname == "holdout":
                    out["holdout_trades"].setdefault(row, {})[cmode] = tl
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    # console summary
    for row in ROWS:
        for w in ("development", "holdout"):
            n = out["results"][row][w]["normal"]
            s = out["results"][row][w]["stress"]
            print(f"{row:22s} {w:11s} normal net={n['net_pct']:+.2f}% dd={n['intrabar_max_dd']:.3f} tr={n['trades']} | stress net={s['net_pct']:+.2f}% dd={s['intrabar_max_dd']:.3f}")


if __name__ == "__main__":
    main()
