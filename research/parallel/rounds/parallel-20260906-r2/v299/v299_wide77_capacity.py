"""v299: the J1 dip agents with the WHOLE 2020 perp market as experience and more model capacity (registry v299).

Why (user goal 2026-09-30: DD ~15%, 6-7 %/month, win ~60%; "more data, more model capacity"): the learned dip decisions improved every
time the experience grew (take-profit agent worst dev year 2.50 -> 2.85 -> 2.93 with 5 -> 11 -> 35 coins; the size agent built on the
35-coin pool is the first learned layer to beat the rules; J1 = size + take-profit). The next step is all of the market that existed on
2021-01-01: every non-major USD-M USDT perp listed for >= 28 days in December 2020 (72 perps, later-delisted ones included; data/raw/
um_universe_20260930 + data/raw/alts2020_intraday_20260930 + data/raw/alts_intraday_20260926; scripts/fetch_alts2020_1m.py with the full
list) - about twice the 35-coin experience. With more rows a larger model can learn more structure without overfitting.
Everything else = v296 J1 (standalone dip-rung replica + fidelity check, seven state features at minute f-1, TP actions {0.5, 1, 1.5},
S1 size rule, X4 take-profit rule with margin 0.0010, cross-fitted halves, fits on fills exited before anchor - 7 days, C4 rules).
Fixed before running:
  K1_wide77        77-coin pool (5 majors + 72 alts), J1 models (HGB depth 3, lr 0.05, 200 iter, min leaf 200, l2 1.0)
  K2_wide77_big    77-coin pool, larger models (HGB depth 6, lr 0.03, 600 iter, min leaf 100, l2 1.0)
Reference: J1_ref (35-coin pool, must reproduce dev4 6.268). SELECTION = v286.dev_select among K1, K2; replaces J1 only if dev_select
prefers it over J1_ref; the most recent year is scored once for the selected row. Dev book-trade and dip-rung win rates reported.

  python research/parallel/rounds/parallel-20260906-r2/v299/v299_wide77_capacity.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v297 = _load("v297_k", RD / "v297/v297_risk_realloc.py")
v296, v294, v293 = v297.v296, v297.v294, v297.v293


def universe_all():
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    v = v[(v.days >= 28) & ~v.symbol.isin(v293.MAJORS)].sort_values("quote_volume_usd", ascending=False)
    return tuple(v.symbol)


def small(seed):
    return v296.hgb(seed)


def big(seed):
    return HistGradientBoostingRegressor(max_depth=6, learning_rate=0.03, max_iter=600, min_samples_leaf=100, l2_regularization=1.0,
                                         random_state=seed)


def pooled_data(eu, universe):
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + tuple(universe):
        try:
            A = assets[s] if s in assets else v293.Asset(s)
        except ValueError:  # no 1m file for this symbol
            continue
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            parts.append(d)
        del A
    return assets, btc, pd.concat(parts, ignore_index=True)


def hooks(eu, idx, cols, assets, btc, allf, make):
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        size_m[jj] = [make(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[make(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                    for h in (0, 1)]
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)
    base = v293.ACTIONS.index(1.0)

    def state(i, a, r, f):
        T = idx[i] + pd.Timedelta(hours=4)
        jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
        if jj is None or T not in pos.index:
            return None, None
        A, j = assets[cols[a]], int(pos[T])
        kk = j * 240 + f - 1
        sg = A.sig[j]
        return jj, np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                              np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]])

    def size(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
        mu = mus[jj]
        return 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)

    def tp(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa = np.array([mm.predict(x)[0] for mm in tp_m[jj][0]])
        pb = np.array([mm.predict(x)[0] for mm in tp_m[jj][1]])
        ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
        if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
            return v293.ACTIONS[ba]
        return 1.0
    return size, tp


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_k", RD / "v286/v286_coinbase_member_upgrade.py")
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
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    assets, btc, pool35 = pooled_data(eu, v294.universe())
    _, _, pool77 = pooled_data(eu, universe_all())
    out = {"version": "v299", "fills": {"pool35": int(len(pool35)), "pool77": int(len(pool77)),
                                        "assets77": int(pool77.sym.nunique())}, "rows": {}, "trades": {}}
    print("fills", out["fills"], flush=True)
    runs = {"J1_ref": (pool35, small), "K1_wide77": (pool77, small), "K2_wide77_big": (pool77, big)}
    for key, (pool, make) in runs.items():
        size, tp = hooks(eu, idx, cols, assets, btc, pool, make)
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], flush=True)
        if key == "J1_ref":
            assert abs(r["monthly_dev4"] - 6.268) < 0.002
    sel = v286.dev_select({k: out["rows"][k] for k in ("K1_wide77", "K2_wide77_big")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_j1"] = v286.dev_select({k: out["rows"][k] for k in ("J1_ref", sel)}, v204.worst_month) == sel
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
    print("SELECTED", sel, "replaces J1:", out["replaces_j1"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v299_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
