"""Forward (prospective) paper trading of the v205 pipeline on data that did not exist when it was frozen.

Research only - no orders. Uses exactly the engine_user rules (AGENTS.md, 2026-09-27): book targets from the logged
prospective v151 advisor rows (directional weight = perp + spot, book = weight / (0.8 * logged scale)), limit entries,
SL/TP on every position, the v204-aligned dip-sleeve ladder with the stop-risk budget, maker 0.02% / taker 0.055%,
adverse funding, vol target 0.25 and the 20% drawdown governor; 1m-marked drawdown with intrabar peaks.
Holding bars that start at or after FREEZE are traded; earlier bars only warm up the vol target (research v205 books).
Market data: Binance USD-M public REST (4h and 1m klines). Output: artifacts/research/advisor_shadow/forward_v205.json.

  python scripts/forward_v205.py                  # prospective, from FREEZE
  python scripts/forward_v205.py --from 2026-09-10 --research-books   # consistency check on already-known data
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
FREEZE = pd.Timestamp("2026-09-27T00:00:00Z")  # first traded holding bar (v205 rules frozen on 2026-09-26)
OUT = ROOT / "artifacts/research/advisor_shadow/forward_v205.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
KW = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12,
          size_mult=1.5, align=(1.5, 0.5))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def research_books(eu):
    cols = SYMS
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    A, B = (mem.xs(k, axis=1, level=0)[cols] for k in ("A", "B"))
    Aq, Bq = (mq.xs(k, axis=1, level=0)[cols] for k in ("A", "B"))
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    return 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2


def research_books_t3(eu):
    """v233 T3 research books (TradingView indicator features in all four members), same units as research_books."""
    cols, C = SYMS, eu.er.CACHE
    m = {k: pd.read_parquet(C / f)[cols] for k, f in (("A", "member_A_tv_annual.parquet"), ("Aq", "member_Aq_tv.parquet"),
                                                       ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    idx = m["A"].index.union(m["Aq"].index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    return 0.5 * (f(m["A"]) + f(m["B"])) / 2 + 0.5 * (f(m["Aq"]) + f(m["Bq"])) / 2


def research_books_w2(eu):
    """v236 W2 research books (T3 + whale-flow features in the A members), same units as research_books."""
    cols, C = SYMS, eu.er.CACHE
    m = {k: pd.read_parquet(C / f)[cols] for k, f in (("A", "member_A_whale.parquet"), ("Aq", "member_Aq_whale.parquet"),
                                                       ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    idx = m["A"].index.union(m["Aq"].index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    return 0.5 * (f(m["A"]) + f(m["B"])) / 2 + 0.5 * (f(m["Aq"]) + f(m["Bq"])) / 2


def research_books_o1(eu):
    """v240 O1 research books (T3 + order-level whale flow in the A members), same units as research_books."""
    cols, C = SYMS, eu.er.CACHE
    m = {k: pd.read_parquet(C / f)[cols] for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
                                                       ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    idx = m["A"].index.union(m["Aq"].index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    return 0.5 * (f(m["A"]) + f(m["B"])) / 2 + 0.5 * (f(m["Aq"]) + f(m["Bq"])) / 2


def live_books(candidate="v151_deploy_v4"):
    rows = [json.loads(l) for l in open(ROOT / "artifacts/research/advisor_shadow/shadow.jsonl", encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("candidate") == candidate and r.get("mode") == "prospective"]
    out = {}
    for r in rows:
        t = pd.Timestamp(r["decision_bar_close"]) + pd.Timedelta(milliseconds=1) - pd.Timedelta(hours=4)
        sc = float(r.get("portfolio_scale") or 1.0)
        out[t] = {s: (r["perp_weight"].get(s, 0.0) + r["spot_weight"].get(s, 0.0)) / (0.8 * sc) for s in SYMS}
    return pd.DataFrame.from_dict(out, orient="index")[SYMS].sort_index() if out else pd.DataFrame(columns=SYMS)


def market(start, now):
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    import requests
    sess = requests.Session()
    k4, k1 = {}, {}
    for s in SYMS:
        a = fetch_klines(s, "4h", (start - pd.Timedelta(days=100)).to_pydatetime(), now.to_pydatetime(), session=sess)
        a["open_time"] = pd.to_datetime(a["open_time"], utc=True)
        k4[s] = a.set_index("open_time")["open"].astype(float)
        m = fetch_klines(s, "1m", (start - pd.Timedelta(hours=4)).to_pydatetime(), now.to_pydatetime(), session=sess)
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        k1[s] = m.drop_duplicates("open_time").set_index("open_time")[["open", "high", "low", "close"]].astype(float)
    return pd.DataFrame(k4), k1


def build_prep(opens, k1, idx):
    n, na = len(idx), len(SYMS)
    cube = {k: np.full((n, 240, na), np.nan) for k in ("open", "high", "low", "close")}
    for j, s in enumerate(SYMS):
        m = k1[s]
        for i, t in enumerate(idx):
            T = t + pd.Timedelta(hours=4)
            seg = m[(m.index >= T) & (m.index < T + pd.Timedelta(hours=4))]
            if seg.empty:
                continue
            off = ((seg.index - T).total_seconds() // 60).astype(int)
            for k in cube:
                cube[k][i, off, j] = seg[k].to_numpy()
    for k in cube:
        X = cube[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm, :])
            X[:, mm, :][miss] = X[:, mm - 1, :][miss]
    o = opens.reindex(idx)[SYMS]
    sig4 = o.pct_change().rolling(360, min_periods=120).std().to_numpy()
    settle = np.isin((idx + pd.Timedelta(hours=8)).hour, (0, 8, 16))
    return dict(idx=idx, cols=SYMS, O=cube["open"], H=cube["high"], L=cube["low"], C=cube["close"], sig4=sig4,
                o1=o.shift(-1).to_numpy(), o2=o.shift(-2).to_numpy(), settle=settle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=None, help="first traded holding bar (default FREEZE)")
    ap.add_argument("--research-books", action="store_true", help="use research books only (consistency check)")
    args = ap.parse_args()
    start = pd.Timestamp(args.start, tz="UTC") if args.start else FREEZE
    now = pd.Timestamp(datetime.now(timezone.utc))
    eu = _load("engine_user_fwd", RD / "engine_user/engine_user.py")
    books = research_books(eu)
    if not args.research_books:
        lb = live_books()
        books = pd.concat([books[books.index < lb.index.min()] if len(lb) else books, lb]).sort_index()
    opens, k1 = market(start, now)
    last_t = now.floor("4h") - pd.Timedelta(hours=8)  # the holding bar of t (t+4h .. t+8h) must be complete
    grid = pd.date_range(start - pd.Timedelta(days=90), last_t, freq="4h")
    books = books.reindex(grid).ffill().fillna(0.0)
    if last_t < start - pd.Timedelta(hours=4):
        OUT.write_text(json.dumps({"status": "no completed forward bar yet", "freeze": str(FREEZE)}, indent=1))
        print("forward v205: no completed bar yet since", start)
        return
    prep = build_prep(opens, k1, grid)
    eu.v110.START, eu.v110.END = start - pd.Timedelta(hours=4), pd.Timestamp("2100-01-01", tz="UTC")
    cap = {}

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(net=net, eq=eq, eq_min=eq_min, eq_max=eq_max, stats=stats, g=g)
        return {}
    eu.summarize = grab
    eu.simulate(books, opens.reindex(grid), prep, **KW)
    live = np.asarray(grid >= start - pd.Timedelta(hours=4))
    e = cap["eq"][live]
    em, ex = cap["eq_min"][live], cap["eq_max"][live]
    peak = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
    dd = float(np.max(1 - np.minimum(e, em) / peak)) if len(e) else 0.0
    days = len(e) / 6
    ret = float(e[-1] - 1) if len(e) else 0.0
    out = {"pipeline": "v205", "freeze": str(start), "scored_until": str(last_t + pd.Timedelta(hours=8)), "bars": int(len(e)),
           "days": round(days, 2), "net_return_pct": round(100 * ret, 3),
           "monthly_equiv_pct": round(100 * ((1 + ret) ** (30 / days) - 1), 2) if days >= 1 else None,
           "max_dd_1m_pct": round(100 * dd, 2), "stats": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()},
           "books_source": "research books (check)" if args.research_books else "prospective v151 advisor rows",
           "equity_curve": [(str(t), round(float(v), 6)) for t, v in zip(grid[live], e)]}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"forward v205 since {start}: {out['bars']} bars ({out['days']} days), net {out['net_return_pct']}%, "
          f"max DD (1m) {out['max_dd_1m_pct']}%, book fills {cap['stats']['fills']}, sleeve rungs {cap['stats']['rungs']}")


if __name__ == "__main__":
    main()
