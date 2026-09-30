"""v294: the v293 take-profit agent with a WIDE, CAUSAL training universe - does more experience keep helping? (registry v294)

Why: v293 showed the first clear data effect for a learned trader decision - training the dip-rung take-profit agent on 11 coins instead
of the 5 majors lifted the worst dev year from 2.50 to 2.85 %/month (CB 3.005). The natural next step is more experience. To avoid
survivorship bias (coins that died are exactly the dips that did not revert), the pool is defined with information available on
2021-01-01: the top-30 non-major USD-M perps by December-2020 quote volume listed for >= 28 days of that month
(data/raw/um_universe_20260930/volume_2020_12.csv via scripts/fetch_um_universe_2020.py; later-delisted coins included; 1m klines from
data/raw/alts_intraday_20260926 or data/raw/alts2020_intraday_20260930 via scripts/fetch_alts2020_1m.py). The alts are TRAINING DATA
only; only the majors are traded.
Everything else is v293 unchanged: standalone dip-rung replica (same fidelity check), actions TP {0.5, 1.0, 1.5} sigma_4h, the same
seven state features known at minute f-1, per-action HGB on clipped net returns, even / odd cross-fitting, fits on fills that exited
before anchor - 7 days, engine hook sleeve_tp on CB with C4 rules.
Fixed before running:
  X3_wide          pool = 5 majors + U2020 (30 alts), deviation margin 0.0005 (as v293)
  X4_wide_strict   same pool, margin 0.0010 (v293's agents moved ~29% of the rungs, mostly to 1.5 sigma; a stricter margin keeps only
                   the most confident deviations)
Reference: CB_ref (must reproduce dev4 5.864). SELECTION = v286.dev_select among X3, X4; replaces CB only if dev_select prefers it over
CB_ref; the most recent year is scored once for the selected row. v293 X2 (11 coins) is reproduced as a labelled comparison row
(dev years only).

  python research/parallel/rounds/parallel-20260906-r2/v294/v294_wide_pool_exit_agent.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
DIRS = (Path("data/raw/alts_intraday_20260926"), Path("data/raw/alts2020_intraday_20260930"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v293 = _load("v293_w", RD / "v293/v293_pooled_exit_agent.py")
_load_major = v293.load_1m


def load_1m(s):
    if s in v293.MAJORS:
        return _load_major(s)
    files = sorted(f for d in DIRS for f in d.glob(f"{s}_1m_20*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= v293.START) & (m.index < v293.END)]
    return m.reindex(pd.date_range(v293.START, v293.END - pd.Timedelta(minutes=1), freq="1min"))


v293.load_1m = load_1m


def universe():
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    v = v[(v.days >= 28) & ~v.symbol.isin(v293.MAJORS)].sort_values("quote_volume_usd", ascending=False)
    return tuple(v.symbol.head(30))


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_w", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    kw = dict(v221.KW, **v293.C4R)
    U = universe()
    have = [s for s in U if any(f for d in DIRS for f in d.glob(f"{s}_1m_20*.parquet"))]
    print("U2020", len(U), "with 1m data", len(have), "missing", sorted(set(U) - set(have)), flush=True)
    names = v293.MAJORS + tuple(have) + tuple(s for s in v293.ALTS if s not in have)
    assets = {s: v293.Asset(s) for s in v293.MAJORS}           # kept (the agent reads the majors' state at trade time)
    btc = assets["BTCUSDT"]
    data = {}
    for s in names:                                             # alts: build, extract the fills, free the memory
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            data[s] = d
        del A
    print("fills per asset", {s: len(d) for s, d in data.items()}, flush=True)

    ev = []
    ref = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    assert abs(ref["monthly_dev4"] - 5.864) < 0.002
    pend, eng = {}, []
    for e in ev:
        if e["kind"] == "rung_fill":
            pend[e["symbol"]] = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in pend:
            f0 = pend.pop(e["symbol"])
            eng.append((e["symbol"], f0["t"], f0["rung"], float(e["ret"])))
    eng = [e for e in eng if e[1] >= idx[0] + pd.Timedelta(days=60)]
    look = {(s, t, v293.RUNGS[int(r)]): y for s, d in data.items() if s in v293.MAJORS for t, r, y in zip(d.t_fill, d.r, d["y1.0"])}
    diffs = np.array([abs(look[(s, t, rg)] - ret) if (s, t, rg) in look else np.inf for s, t, rg, ret in eng])
    share, mad = float((diffs < 1e-4).mean()), float(diffs[np.isfinite(diffs)].mean())
    print(f"fidelity: engine rungs {len(eng)}, within 1e-4 {share:.4f}, mean |diff| {mad:.2e}", flush=True)
    assert share >= 0.97 and mad < 2e-4

    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    allf = pd.concat(data.values(), ignore_index=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    half = (allf["j"] % 2).to_numpy()
    dev = np.asarray((allf.t_fill >= anchors[0]) & (allf.t_fill < anchors[4]))
    pools = {"X2_11coins_ref": v293.MAJORS + v293.ALTS, "X3_wide": v293.MAJORS + tuple(have), "X4_wide_strict": v293.MAJORS + tuple(have)}
    margins = {"X2_11coins_ref": 0.0005, "X3_wide": 0.0005, "X4_wide_strict": 0.0010}
    out = {"version": "v294", "universe": list(U), "universe_with_data": have, "fidelity_share_1e-4": round(share, 4),
           "fills": {s: len(d) for s, d in data.items()},
           "dev_mean_net_by_action_pct": {g: {str(mu): round(100 * float(Y[dev & allf.sym.isin(S).to_numpy(), c].mean()), 4)
                                              for c, mu in enumerate(v293.ACTIONS)} for g, S in (("majors", v293.MAJORS), ("U2020", tuple(have)))},
           "train": {}, "rows": {}, "trades": {}}
    print("dev mean net by action %", out["dev_mean_net_by_action_pct"], flush=True)

    def fit(pool, tag):
        models = {}
        for jj, a0 in enumerate(anchors):
            keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO) & allf.sym.isin(pool).to_numpy()
            pair = []
            for h in (0, 1):
                sel = keep & (half == h)
                pair.append([HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200,
                                                           l2_regularization=1.0, random_state=10 * jj + h + 3 * c).fit(X[sel], Y[sel, c])
                             for c in range(len(v293.ACTIONS))])
            models[jj] = pair
            out["train"].setdefault(str(a0.date()), {})[tag] = int(keep.sum())
        return models

    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)

    def agent(models, margin):
        stats = {"asked": 0, "changed": {str(mu): 0 for mu in v293.ACTIONS}}
        base = v293.ACTIONS.index(1.0)

        def pol(i, a, r, f):
            T = idx[i] + pd.Timedelta(hours=4)
            jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
            if jj is None or T not in pos.index:
                return 1.0
            A, j = assets[cols[a]], int(pos[T])
            kk = j * 240 + f - 1
            sg = A.sig[j]
            x = np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                           np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]])
            pa = np.array([mm.predict(x)[0] for mm in models[jj][0]])
            pb = np.array([mm.predict(x)[0] for mm in models[jj][1]])
            ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
            stats["asked"] += 1
            if ba == bb and ba != base and pa[ba] - pa[base] > margin and pb[bb] - pb[base] > margin:
                stats["changed"][str(v293.ACTIONS[ba])] += 1
                return v293.ACTIONS[ba]
            return 1.0
        pol.stats = stats
        return pol

    ref["worst_dev_month_pct"] = round(v204.worst_month(ref), 3)
    ref["dev_dd"] = v286.dev_dd(ref)
    out["rows"]["CB_ref"], out["trades"]["CB_ref"] = ref, v213.trade_stats(ev)
    fitted = {}
    for key, pool in pools.items():
        pk = tuple(sorted(pool))
        if pk not in fitted:
            fitted[pk] = fit(pool, key)
        hook = agent(fitted[pk], margins[key])
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_tp=hook, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["agent"] = dict(hook.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "agent", r["agent"], flush=True)
    sel = v286.dev_select({k: out["rows"][k] for k in ("X3_wide", "X4_wide_strict")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = v286.dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v294_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
