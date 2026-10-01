"""v303: five-seed test of the flush-breadth agents (registry v303) - is the v302 H1 drawdown gain real or seed noise?

Why: v302 H1 (both dip agents see the flush breadth) kept dev4 6.527 and cut the dev DD 17.33 -> 16.49 but lowered the worst dev year 3.618 ->
3.346 (just outside the pre-registered tolerance). The agents are stochastic learners: sklearn HistGradientBoosting turns early stopping on for
> 10 000 rows (the 2022+ anchors train on 12-32k rows) with a RANDOM validation split, so a single fit can differ from its neighbours by more than
the effect (rule since v259: every stochastic learner must report >= 5 seeds before any claim). Here G2 (7 features) and H1 (10 features, v302
breadth) are each fitted with 5 seeds (random_state base + 1000 x seed; seed 0 = the v301 / v302 fits exactly) and run through the engine.
Everything else = v302 / v301 G2 (35-coin pooled experience, replica, features at minute f-1, fits on fills exited before anchor - 7 days, size rule
S1, X4 take-profit rule, C4 rules, dip budget 0.26).
SELECTION (registered; dev years only, medians over the 5 seeds): H1 replaces G2 iff
  median dev DD(H1) <= median dev DD(G2) - 0.4,  median dev4(H1) >= median dev4(G2) - 0.15,  median worst dev year(H1) >= median worst(G2) - 0.2,
  and in EVERY H1 seed: no losing dev year and dev DD <= 20.
The most recent year is scored once, for all five H1 seeds together (median reported), only if H1 is selected. G2 seed 0 must reproduce dev4 6.527.

  python research/parallel/rounds/parallel-20260906-r2/v303/v303_breadth_seeds.py
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
SEEDS = (0, 1, 2, 3, 4)
BUDGET = 0.26


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v302 = _load("v302_s", RD / "v302/v302_flush_breadth.py")
v301, v296, v294, v293 = v302.v301, v302.v296, v302.v294, v302.v293


def hgb(seed):
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                         random_state=seed)


def prepare(eu):
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    b_mean, b_min, flush = v302.breadth_arrays(assets)
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            parts.append(d)
        del A
    allf = pd.concat(parts, ignore_index=True)
    kk = (allf["j"].to_numpy() * 240 + allf["f"].to_numpy() - 1).astype(int)
    allf["x7"], allf["x8"], allf["x9"] = b_mean[kk], b_min[kk], flush[allf["j"].to_numpy(), allf["f"].to_numpy() - 1].astype(float)
    return dict(assets=assets, btc=btc, b_mean=b_mean, b_min=b_min, flush=flush, allf=allf)


def make_hooks(eu, idx, cols, ex, cols_used, seed):
    allf, assets, btc = ex["allf"], ex["assets"], ex["btc"]
    Xall = allf[[f"x{q}" for q in range(10)]].to_numpy(float)[:, cols_used]
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        base = 1000 * seed + 10 * jj
        size_m[jj] = [hgb(base + h).fit(Xall[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[hgb(base + h + 3 * c).fit(Xall[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                    for h in (0, 1)]
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)
    b0 = v293.ACTIONS.index(1.0)

    def state(i, a, r, f):
        T = idx[i] + pd.Timedelta(hours=4)
        jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
        if jj is None or T not in pos.index:
            return None, None
        A, j = assets[cols[a]], int(pos[T])
        k = j * 240 + f - 1
        sg = A.sig[j]
        x = np.array([[A.sp30(k), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(k),
                       np.log(A.C[k] / A.hmax24[k]) / sg if A.hmax24[k] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24,
                       ex["b_mean"][k], ex["b_min"][k], float(ex["flush"][j, f - 1])]])
        return jj, x[:, cols_used]

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
        if ba == bb and ba != b0 and pa[ba] - pa[b0] > 0.0010 and pb[bb] - pb[b0] > 0.0010:
            return v293.ACTIONS[ba]
        return 1.0
    return size, tp


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_s3", RD / "v286/v286_coinbase_member_upgrade.py")
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
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    ex = prepare(eu)
    sets = {"G2": list(range(7)), "H1": list(range(10))}
    out = {"version": "v303", "seeds": list(SEEDS), "rows": {}, "trades": {}}
    for name, cu in sets.items():
        for sd in SEEDS:
            size, tp = make_hooks(eu, idx, cols, ex, cu, sd)
            ev = []
            r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp,
                            **dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=BUDGET)))
            r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
            r["dev_dd"] = v286.dev_dd(r)
            r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
            key = f"{name}_s{sd}"
            out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
            print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
                  "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
                  "dev trade win", out["trades"][key]["dev"]["win_rate"], flush=True)
            if key == "G2_s0":
                assert abs(r["monthly_dev4"] - 6.527) < 0.002 and abs(r["dev_dd"] - 17.33) < 0.02
    med = lambda nm, f: float(np.median([out["rows"][f"{nm}_s{s}"][f] for s in SEEDS]))
    summ = {nm: {f: round(med(nm, f), 3) for f in ("monthly_dev4", "worst_dev_month_pct", "dev_dd")} for nm in sets}
    for nm in sets:
        summ[nm]["dev_dd_range"] = [min(out["rows"][f"{nm}_s{s}"]["dev_dd"] for s in SEEDS), max(out["rows"][f"{nm}_s{s}"]["dev_dd"] for s in SEEDS)]
        summ[nm]["worst_range"] = [min(out["rows"][f"{nm}_s{s}"]["worst_dev_month_pct"] for s in SEEDS),
                                   max(out["rows"][f"{nm}_s{s}"]["worst_dev_month_pct"] for s in SEEDS)]
    out["summary"] = summ
    print("SUMMARY", json.dumps(summ), flush=True)
    h, g = summ["H1"], summ["G2"]
    each = all(out["rows"][f"H1_s{s}"]["dev_dd"] <= 20 and all(y["net_pct"] >= 0 for y in out["rows"][f"H1_s{s}"]["yearly"][:4]) for s in SEEDS)
    sel = (h["dev_dd"] <= g["dev_dd"] - 0.4 and h["monthly_dev4"] >= g["monthly_dev4"] - 0.15
           and h["worst_dev_month_pct"] >= g["worst_dev_month_pct"] - 0.2 and each)
    out["selected"] = "H1" if sel else None
    if sel:
        fin = []
        for s in SEEDS:
            r = out["rows"][f"H1_s{s}"]
            fin.append({"seed": s, "monthly_5y": r["monthly_5y"], "monthly_last_year": r["monthly_last_year"], "gate_dd": r["gate_dd"],
                        "losing_years": r["losing_years"], "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"]]})
        out["final_score_selected"] = {"per_seed": fin, "median_5y": float(np.median([f["monthly_5y"] for f in fin])),
                                       "median_last_year": float(np.median([f["monthly_last_year"] for f in fin])),
                                       "median_gate_dd": float(np.median([f["gate_dd"] for f in fin]))}
    else:
        out["final_score_selected"] = "H1 not selected (median rule) - G2 stays; nothing scored on the most recent year"
    for k in out["trades"]:
        if not (sel and k.startswith("H1")):
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if not (sel and k.startswith("H1")):
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", out["selected"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v303_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
