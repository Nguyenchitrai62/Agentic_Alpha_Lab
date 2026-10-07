"""oc_expiry: Deribit options-expiry calendar vs dip fills + book P&L.

Per PLAN.md (pre-registered): pure-calendar windows (last Friday 08:00 UTC),
dip y1.0 inside-vs-outside spreads per anchor year, vectorised gross book P&L
inside-vs-outside, LOYO stability, default decision rule on the WEEK spread.
Light: fills + two 4h frames, one process, no 1m data.

  python research/tournament/oc_expiry/analyze_expiry.py
"""

from __future__ import annotations

import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAJORS = set(SYMS)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")
MIN_IN = 30  # min inside fills for a valid spread


def expiry(y: int, m: int) -> pd.Timestamp:
    """Last Friday of month m, 08:00 UTC (Deribit monthly expiry)."""
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7  # Friday == 4
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


def expiries() -> pd.DataFrame:
    rows = []
    for y in range(2021, 2027):
        for m in range(1, 13):
            e = expiry(y, m)
            if e < pd.Timestamp("2021-01-01", tz="UTC") or e >= DEV_END + pd.Timedelta(days=1):
                continue
            rows.append(dict(E=e, quarterly=m in (3, 6, 9, 12)))
    return pd.DataFrame(rows)


def window_flags(t: pd.Series, exp: pd.DataFrame) -> pd.DataFrame:
    """Vectorised inside-window flags for WEEK / PRE24 / POST24 (+ quarterly week)."""
    t = pd.to_datetime(t, utc=True)
    ti = t.astype("int64").to_numpy()
    H = np.int64(3_600_000_000_000)
    week = np.zeros(len(t), bool)
    pre = np.zeros(len(t), bool)
    post = np.zeros(len(t), bool)
    qweek = np.zeros(len(t), bool)
    for r in exp.itertuples():
        e = np.int64(r.E.value)
        ws = e - np.int64(104) * H  # Mon 00:00 = E - 4d8h
        week |= (ti >= ws) & (ti < e)
        pre |= (ti >= e - np.int64(24) * H) & (ti < e)
        post |= (ti >= e) & (ti < e + np.int64(24) * H)
        if r.quarterly:
            qweek |= (ti >= ws) & (ti < e)
    return pd.DataFrame({"week": week, "pre24": pre, "post24": post, "qweek": qweek}, index=t.index)


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def year_rows(df: pd.DataFrame, a0: pd.Timestamp) -> pd.DataFrame:
    return df[(df["T"] >= a0) & (df["T"] < a0 + YEAR_LEN)]


def spread_stats(v_in: np.ndarray, v_out: np.ndarray):
    v_in = np.asarray(v_in, float)
    v_out = np.asarray(v_out, float)
    if len(v_in) < MIN_IN or len(v_out) < MIN_IN:
        return None
    return dict(mean_in=float(v_in.mean()), mean_out=float(v_out.mean()),
                spread=float(v_in.mean() - v_out.mean()),
                n_in=int(len(v_in)), n_out=int(len(v_out)))


def main() -> None:
    exp = expiries()

    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills = fills[fills.t_fill < DEV_END].copy()
    fills["T"] = fills.t_fill - pd.to_timedelta(fills.f, unit="min")
    d = fills[fills.sym.isin(MAJORS) & fills.x1.isin(R2)].copy().reset_index(drop=True)
    d["y_bps"] = d["y1.0"] * 1e4
    fl = window_flags(d["T"], exp)
    for c in fl.columns:
        d[c] = fl[c].to_numpy()

    # Book vectorised gross P&L
    books = research_books_d2()
    opens = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS]
    grid = books.index.intersection(opens.index).sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)
    fwd = opens.shift(-1) / opens - 1.0
    u = (books * fwd).sum(axis=1).dropna() * 1e4  # gross bps per 4h bar
    bdf = pd.DataFrame({"T": u.index, "u_bps": u.to_numpy()})
    bl = window_flags(bdf["T"], exp)
    for c in bl.columns:
        bdf[c] = bl[c].to_numpy()

    out: dict = {"universe_rows": int(len(d)),
                 "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
                 "n_expiries": int(len(exp)), "n_quarterly": int(exp.quarterly.sum()),
                 "years": {}, "book": {}, "loyo": {}, "quarterly_split": {}}
    spreads = {}
    for a0 in ANCHORS:
        y = str(a0.date())
        yd = year_rows(d, a0)
        yb = bdf[(bdf["T"] >= a0) & (bdf["T"] < a0 + YEAR_LEN)]
        yres: dict = {"n": int(len(yd))}
        for w in ("week", "pre24", "post24"):
            s = spread_stats(yd.loc[yd[w].to_numpy(), "y_bps"],
                             yd.loc[(~yd[w]).to_numpy(), "y_bps"])
            yres[w] = s
            if w == "week":
                spreads[y] = None if s is None else s["spread"]
        # worst days (descriptive): sums over inside / outside fills by day
        wd = {}
        for w in ("week", "pre24", "post24"):
            for lab, m in (("in", yd[w].to_numpy()), ("out", (~yd[w]).to_numpy())):
                g = yd.loc[m].groupby(yd.loc[m, "T"].dt.floor("D"))["y_bps"].sum()
                wd[f"{w}_{lab}"] = round(float(g.min()), 2) if len(g) else None
        yres["worst_day_bps"] = wd
        out["years"][y] = yres
        bres: dict = {"n_bars": int(len(yb))}
        for w in ("week", "pre24", "post24"):
            s = spread_stats(yb.loc[yb[w].to_numpy(), "u_bps"],
                             yb.loc[(~yb[w]).to_numpy(), "u_bps"])
            if s is not None:
                s["sum_in"] = round(float(yb.loc[yb[w].to_numpy(), "u_bps"].sum()), 2)
                s["sum_out"] = round(float(yb.loc[(~yb[w]).to_numpy(), "u_bps"].sum()), 2)
            bres[w] = s
        out["book"][y] = bres

    # LOYO on WEEK dip spread
    loyo_pass, signs = {}, {}
    for i, a0 in enumerate(ANCHORS):
        y = str(a0.date())
        tr = pd.concat([year_rows(d, a) for j, a in enumerate(ANCHORS) if j != i])
        s_tr = spread_stats(tr.loc[tr.week.to_numpy(), "y_bps"],
                            tr.loc[(~tr.week).to_numpy(), "y_bps"])
        s_h = out["years"][y]["week"]
        ok = (s_tr is not None and s_h is not None
              and np.sign(s_tr["spread"]) == np.sign(s_h["spread"])
              and s_tr["spread"] != 0)
        loyo_pass[y] = bool(ok)
        signs[y] = None if s_h is None else int(np.sign(s_h["spread"]))
    out["loyo"] = loyo_pass
    n_sign = sum(1 for v in signs.values() if v == 1) + sum(1 for v in signs.values() if v == -1)
    dom = None
    for cand in (1, -1):
        if sum(1 for v in signs.values() if v == cand) >= 4:
            dom = cand
    out["sign_consistent_4of5"] = dom is not None
    out["loyo_pass_4of5"] = sum(loyo_pass.values()) >= 4
    out["verdict"] = "PROMISING" if (dom is not None and sum(loyo_pass.values()) >= 4) else "NOT_PROMISING"

    # quarterly vs monthly WEEK split, pooled 5y (descriptive)
    ymask = (d["T"] >= ANCHORS[0]) & (d["T"] < ANCHORS[-1] + YEAR_LEN)
    dp = d[ymask]
    mq = spread_stats(dp.loc[dp.qweek.to_numpy(), "y_bps"],
                      dp.loc[(~dp.qweek).to_numpy(), "y_bps"])
    m_only = dp[dp.week & ~dp.qweek]
    mo = spread_stats(m_only["y_bps"], dp.loc[(~dp.week).to_numpy(), "y_bps"])
    out["quarterly_split"] = {"qweek_vs_rest_bps": mq, "mweek_vs_rest_bps": mo}

    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:3000])
    print("VERDICT:", out["verdict"])


if __name__ == "__main__":
    main()
