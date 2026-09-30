"""v289: a second, independent return engine - a 12h dip-reversal sub-account next to CB (registry v289).

Why: the largest gain in this project came from a new RETURN STREAM (the 4h dip sleeve, v171: +8..65%/yr, corr ~0 with the book),
not from better signals. Dev-only diagnostics (research/diagnostics/daily_dip, never loading data after 2025-09-24):
  - daily_dip_dev: a resting bid 4 sigma_12h below the 12h open, filled on a 1m trade-through from minute 5, exit at TP +1 sigma
    or the next 12h open, is positive in EVERY dev year (mean 1.34 / 0.86 / 1.11 / 1.06 % per fill, t 4.3 / 3.3 / 5.4 / 5.1, win
    75-87%); the 1d scale fails in 2022, the hourly ladder failed before (v229/v275: hourly dips continue).
  - overlap_dev: its daily PnL is ~uncorrelated with CB (corr with CB total 0.05 / 0.01 / 0.12 / -0.08).
Design (fixed before running; executable under the user's trade rules):
  Sub-account (separate capital, e.g. a Bybit sub-account), five majors, periods aligned at 00:00 / 12:00 UTC (both are 4h closes).
  sigma = std of the last 30 12h close-to-close log returns (only closed periods; >= 20 required).
  At minute 5 of each period: resting limit bids at L = O x exp(-k sigma), k in (3.0, 3.5, 4.0), O = the period's minute-0 open;
  valid until minute 704 (cancelled after); filled only on a 1m trade-through (low < L), maker 0.0002.
  Size: every rung risks R = 3% of the sub-account equity at placement at its stop: notional = R x E / (3 sigma). All positions of the
  previous period are closed at minute 0, so the placement equity is realised cash (no look-ahead).
  Every position carries a stop-loss (market, taker 0.00055) at L x exp(-3 sigma) - touch on the 1m low, a gap below it fills at that
  minute's open, the fill minute itself is checked (stop-first) - and a take-profit limit at L x exp(+1 sigma) (maker, 1m high above
  it, never in the fill minute; stop-first if both in one minute); otherwise market exit at the next period's minute-0 open (taker).
  Funding (gate rule): 0.0001 x notional at every 00 / 08 / 16 UTC settlement with the position open (exit at the settlement minute
  pays). Equity is marked every minute (open positions on the 1m LOW for the minimum); liquidation check: 1m-low-marked equity <=
  1% of the open notional -> the sub-account is liquidated (reported).
Combination with CB (v285 D2, engine_user, C4 rules): two accounts, capital split rebalanced to (1-x, x) at every month start
(internal transfers, no cost); combined 4h equity = sum; combined 1m-marked minimum per bar = sum of the two minima (conservative).
Metrics via engine_user.summarize (same yearly / dev4 / DD definitions as every version).
  S1_x15   x = 0.15
  S2_x25   x = 0.25
Reference: CB_ref (must reproduce dev4 5.864). SELECTION: v286.dev_select (robust criterion, DD filter on 2021-2024 only) among S1, S2;
the selected row replaces CB only if dev_select prefers it over CB_ref. The most recent year is scored once, for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v289/v289_dip12h_account.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
D1M = Path("data/raw/majors_intraday_20260924")
BTC1M = Path("data/raw/btc_intraday_20260924")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
P, WIN0, WIN1 = 720, 5, 704
KS, R_RISK, M_STOP, M_TP = (3.0, 3.5, 4.0), 0.03, 3.0, 1.0
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
START, END = pd.Timestamp("2021-06-01", tz="UTC"), pd.Timestamp("2026-09-24", tz="UTC")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_1m(s):
    parts = []
    for y in range(2021, 2027):
        f = (BTC1M / f"klines_1m_{y}.parquet") if s == "BTCUSDT" else (D1M / f"{s}_1m_{y}.parquet")
        if f.exists():
            parts.append(pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]))
    m = pd.concat(parts).drop_duplicates("open_time")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m.open_time >= START) & (m.open_time < END)].set_index("open_time").sort_index()
    m = m.reindex(pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min"))
    m["close"] = m["close"].ffill()
    for c in ("open", "high", "low"):
        m[c] = m[c].fillna(m["close"])
    return m


def simulate_account(data):
    """Sequential 12h ladder sub-account. data = {sym: 1m frame on the common grid}. Returns per-minute cash / unrealised arrays."""
    grid = data[SYMS[0]].index
    nm = len(grid)
    npd = nm // P
    O = {s: data[s]["open"].to_numpy(float) for s in SYMS}
    H = {s: data[s]["high"].to_numpy(float) for s in SYMS}
    L_ = {s: data[s]["low"].to_numpy(float) for s in SYMS}
    Cl = {s: data[s]["close"].to_numpy(float) for s in SYMS}
    sig = {}
    for s in SYMS:
        pc = Cl[s][P - 1: npd * P: P]                     # close of each period
        r = np.diff(np.log(pc), prepend=np.nan)
        sig[s] = pd.Series(r).rolling(30, min_periods=20).std().shift(1).to_numpy()  # periods strictly before p
    hours = grid.hour.to_numpy()
    mins = grid.minute.to_numpy()
    fund_min = (mins == 0) & np.isin(hours, (0, 8, 16))
    fund_cum = np.cumsum(fund_min)
    realized = np.zeros(nm + 1)                            # realised PnL booked at the exit minute (index = minute), never reset
    u_low, u_close = np.zeros(nm), np.zeros(nm)
    notional = np.zeros(nm)
    cash = 1.0
    trades, liquidated = [], None
    for p in range(npd):
        s0 = p * P
        if p > 0:
            cash += realized[s0 - P + 1: s0 + 1].sum()    # everything from the previous period is closed by minute s0
        if liquidated is not None or cash <= 0:
            break
        E = cash
        for s in SYMS:
            sg = sig[s][p]
            if not np.isfinite(sg) or sg <= 0:
                continue
            o0 = O[s][s0]
            for k in KS:
                lim = o0 * np.exp(-k * sg)
                lows = L_[s][s0 + WIN0: s0 + WIN1]
                hit = np.flatnonzero(lows < lim)
                if not len(hit):
                    continue
                f = s0 + WIN0 + int(hit[0])
                N = R_RISK * E / (M_STOP * sg)
                q = N / lim
                stop, tp = lim * np.exp(-M_STOP * sg), lim * np.exp(M_TP * sg)
                end = s0 + P                               # exit minute (next period's open) if nothing hit
                ex_j, ex_px, kind = end, (O[s][end] if end < nm else Cl[s][nm - 1]), "time"
                for j in range(f, min(end, nm)):
                    if j > f and O[s][j] <= stop:
                        ex_j, ex_px, kind = j, O[s][j], "stop"
                        break
                    if L_[s][j] <= stop:
                        ex_j, ex_px, kind = j, stop, "stop"
                        break
                    if j > f and H[s][j] > tp:
                        ex_j, ex_px, kind = j, tp, "tp"
                        break
                fee = N * MAKER + q * ex_px * (MAKER if kind == "tp" else TAKER)
                nf = fund_cum[min(ex_j, nm - 1)] - fund_cum[f]  # fills are never at minute 0  # settlements after the fill minute up to the exit minute
                pnl = q * (ex_px - lim) - fee - FUND * N * nf
                last = min(ex_j, nm)                          # minutes f .. ex_j-1 are held (the exit minute books the PnL)
                seg = slice(f, last)
                u_low[seg] += q * (L_[s][seg] - lim) - N * MAKER
                u_close[seg] += q * (Cl[s][seg] - lim) - N * MAKER
                notional[seg] += N
                realized[min(ex_j, nm)] += pnl
                trades.append(dict(t=grid[f], sym=s, k=k, kind=kind, pnl_frac=pnl / E, ret=pnl / N))
        # liquidation check inside the period (1m-low-marked equity vs 1% of open notional)
        seg = slice(s0, min(s0 + P, nm))
        run_cash = cash + np.concatenate([[0.0], np.cumsum(realized[s0 + 1: min(s0 + P, nm)])])
        eq_low = run_cash + u_low[seg]
        bad = np.flatnonzero(eq_low <= 0.01 * notional[seg])
        if len(bad) and notional[seg][bad[0]] > 0:
            liquidated = grid[s0 + int(bad[0])]
    cash_path = 1.0 + np.cumsum(realized[:nm])  # booked when exited
    return dict(grid=grid, cash=cash_path, u_low=u_low, u_close=u_close, trades=pd.DataFrame(trades), liquidated=liquidated)


def per_bar(acc, idx):
    """Sub-account equity at each 4h bar's end and its 1m-low-marked minimum inside the bar, for the engine's bar index."""
    grid = acc["grid"]
    eq_close = acc["cash"] + acc["u_close"]
    eq_low = acc["cash"] + acc["u_low"]
    pos = grid.get_indexer(idx)
    e_end, e_min = np.full(len(idx), np.nan), np.full(len(idx), np.nan)
    for i, a in enumerate(pos):
        if a < 0 or a + 240 > len(grid):
            continue
        e_end[i] = eq_close[a + 239]
        e_min[i] = min(eq_low[a: a + 240].min(), eq_close[a: a + 240].min())
    return pd.Series(e_end, idx).ffill().fillna(1.0).to_numpy(), pd.Series(e_min, idx).ffill().fillna(1.0).to_numpy()


def combine(idx, eq_cb, min_cb, eq_s, min_s, x):
    """Two accounts, split reset to (1-x, x) at every month start; returns combined equity and 1m-marked minimum per bar."""
    n = len(idx)
    eq, emin = np.ones(n), np.ones(n)
    month = pd.DatetimeIndex(idx).to_period("M")
    V = 1.0
    a = b = 0.0
    for i in range(n):
        if i == 0 or month[i] != month[i - 1]:
            V = eq[i - 1] if i > 0 else 1.0
            ref_cb = eq_cb[i - 1] if i > 0 else eq_cb[0]
            ref_s = eq_s[i - 1] if i > 0 else eq_s[0]
            a, b = (1 - x) * V / ref_cb, x * V / ref_s          # units held in each account
        eq[i] = a * eq_cb[i] + b * eq_s[i]
        emin[i] = a * min_cb[i] + b * min_s[i]
    return eq, emin


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_s", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204 = v221.eu, v221.v216, v221.v204
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    Dq = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (D + Dq) / 2
    path = {}
    ref = eu.simulate(cb, opens, eu.prepare(books154, opens), trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)),
                      win_start=5, path_out=path, **dict(v221.KW, **C4R))
    assert abs(ref["monthly_dev4"] - 5.864) < 0.002
    t = pd.DatetimeIndex(path["t"])
    acc = simulate_account({s: load_1m(s) for s in SYMS})
    tr = acc["trades"]
    print("sub-account trades", len(tr), "liquidated", acc["liquidated"], flush=True)
    eq_s, min_s = per_bar(acc, t)
    ones = np.ones(len(t))
    out = {"version": "v289", "rows": {}, "account": {}}
    ref["worst_dev_month_pct"] = round(v204.worst_month(ref), 3)
    ref["dev_dd"] = v286.dev_dd(ref)
    out["rows"]["CB_ref"] = ref
    alone = eu.summarize(t, np.r_[0.0, eq_s[1:] / eq_s[:-1] - 1], eq_s, np.minimum(min_s, eq_s), ones, {})
    dev_tr = tr[tr.t < pd.Timestamp("2025-09-24", tz="UTC")]
    out["account"] = {"dev_years": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in alone["yearly"][:4]],
                      "dev_trades": int(len(dev_tr)), "dev_win_rate": round(float((dev_tr.ret > 0).mean()), 3),
                      "dev_kinds": dev_tr.kind.value_counts().to_dict(), "liquidated": str(acc["liquidated"])}
    print("account alone (dev)", out["account"], flush=True)
    for key, x in (("S1_x15", 0.15), ("S2_x25", 0.25)):
        eq, emin = combine(t, path["eq"], path["eq_min"], eq_s, min_s, x)
        r = eu.summarize(t, np.r_[0.0, eq[1:] / eq[:-1] - 1], eq, np.minimum(emin, eq), ones, {})
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
    sel = v286.dev_select({k: out["rows"][k] for k in ("S1_x15", "S2_x25")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = v286.dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    hid = tr[tr.t >= pd.Timestamp("2025-09-24", tz="UTC")]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "account_hidden_trades": int(len(hid)), "account_hidden_win_rate": round(float((hid.ret > 0).mean()), 3) if len(hid) else None}
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v289_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
